from datetime import datetime, timedelta
import logging
import secrets
import asyncio
import pytz
import re
import base64
import hashlib
import os
import uuid
from DB import (
    Conversation,
    ConversationShare,
    ConversationParticipant,
    Agent,
    Message,
    MessageReaction,
    DiscardedContext,
    Memory,
    User,
    UserCompany,
    get_session,
)
from Globals import getenv, DEFAULT_USER
from sqlalchemy.sql import func, or_, and_, case, exists
from MagicalAuth import convert_time, get_user_id, get_user_timezone
from SharedCache import shared_cache

# Module-level timezone constants to avoid repeated pytz.timezone() calls
_GMT = pytz.timezone("GMT")
_tz_cache = {}


def _make_time_converter(user_id):
    """Create a fast timezone converter closure for a user. Caches pytz timezone objects."""
    user_timezone = get_user_timezone(user_id)
    if user_timezone not in _tz_cache:
        _tz_cache[user_timezone] = pytz.timezone(user_timezone)
    local_tz = _tz_cache[user_timezone]
    gmt = _GMT

    def _convert(utc_time):
        if utc_time is None:
            return None
        if utc_time.tzinfo is None:
            return gmt.localize(utc_time).astimezone(local_tz)
        return utc_time.astimezone(local_tz)

    return _convert


def _get_user_company_ids(user_id: str) -> list:
    """Get user's company IDs with SharedCache (10s TTL)."""
    cache_key = f"user_company_ids:{user_id}"
    cached = shared_cache.get(cache_key)
    if cached is not None:
        return cached
    session = get_session()
    try:
        ids = [
            str(uc[0])
            for uc in session.query(UserCompany.company_id)
            .filter(UserCompany.user_id == user_id)
            .all()
        ]
        shared_cache.set(cache_key, ids, ttl=10)
        return ids
    finally:
        session.close()


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)

# Cache TTL for conversation ID lookups (uses SharedCache)
_conversation_id_cache_ttl = 30  # 30 seconds


def _find_markdown_data_urls(message: str):
    """
    Find all markdown data URL references in a message using imperative O(n)
    parsing. Returns list of (start, end, is_image, alt_text, data_url) tuples.

    This avoids regex backtracking entirely — Python's re module does not
    optimize [^\\]]*\\] patterns, causing O(n²) on strings with many '[' but
    no ']' (CodeQL: polynomial regular expression).
    """
    results = []
    pos = 0
    msg_len = len(message)
    while pos < msg_len:
        # Find the next '[' character
        bracket_start = message.find("[", pos)
        if bracket_start == -1:
            break

        # Check for '!' prefix (image syntax)
        is_image = bracket_start > 0 and message[bracket_start - 1] == "!"
        match_start = bracket_start - 1 if is_image else bracket_start

        # Find the closing ']'
        bracket_end = message.find("]", bracket_start + 1)
        if bracket_end == -1:
            break  # No more ']' in the string, stop scanning

        # Check for '(' immediately after ']'
        if bracket_end + 1 >= msg_len or message[bracket_end + 1] != "(":
            pos = bracket_end + 1
            continue

        # Check if the URL starts with 'data:'
        url_start = bracket_end + 2
        if not message[url_start : url_start + 5] == "data:":
            pos = bracket_end + 1
            continue

        # Find the closing ')'
        paren_end = message.find(")", url_start)
        if paren_end == -1:
            break  # No more ')' in the string, stop scanning

        alt_text = message[bracket_start + 1 : bracket_end]
        data_url = message[url_start:paren_end]

        results.append((match_start, paren_end + 1, is_image, alt_text, data_url))
        pos = paren_end + 1

    return results


# Minimum size threshold for extracting data URLs to workspace (10KB)
# Smaller data URLs (like tiny icons) are left inline
_DATA_URL_SIZE_THRESHOLD = 10 * 1024
_RE_BASE64_CHARS = re.compile(r"[A-Za-z0-9+/=\s]+")

# MIME type to file extension mapping
_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/aac": ".aac",
    "application/pdf": ".pdf",
    "application/octet-stream": ".bin",
}


def _safe_join_path(base_dir: str, *parts: str) -> str:
    """Join path components and verify the result stays under *base_dir*.

    Uses ``os.path.realpath`` + ``str.startswith`` so static-analysis
    tools (CodeQL ``py/path-injection``) recognise the guard as a
    path-traversal sanitizer.

    Raises ``ValueError`` if the resolved path escapes *base_dir*.
    """
    resolved_base = os.path.realpath(base_dir)
    resolved = os.path.realpath(os.path.join(base_dir, *parts))
    # startswith(base + sep) handles the "base_dir_extra" false-positive;
    # the equality check covers the edge case where resolved == base.
    if not (resolved.startswith(resolved_base + os.sep) or resolved == resolved_base):
        raise ValueError(
            f"Path escapes base directory: {resolved!r} is not under {resolved_base!r}"
        )
    return resolved


def _sanitize_filename(name: str, default_ext: str) -> str:
    """
    Sanitize a user-controlled filename so it is safe to use on disk.
    Strips directory components, rejects traversal tokens, and falls
    back to a random name when invalid.
    """
    base = os.path.basename(str(name).strip())
    if not base or base in (".", "..") or os.path.isabs(base):
        return f"{uuid.uuid4().hex[:12]}{default_ext}"
    if "/" in base or "\\" in base or ".." in base:
        return f"{uuid.uuid4().hex[:12]}{default_ext}"
    return base


def extract_data_urls_to_workspace(
    message: str, agent_id: str, conversation_id: str
) -> str:
    """
    Extract base64 data URLs from markdown message content and save them as
    workspace files. Returns the message with data URLs replaced by /outputs/ URLs.

    This prevents massive base64 strings from being stored in the database and
    rendered in the DOM, which causes performance issues especially for video/audio.

    Args:
        message: The message content potentially containing base64 data URLs
        agent_id: The agent ID for workspace path
        conversation_id: The conversation ID for workspace path

    Returns:
        The message with base64 data URLs replaced by /outputs/ URLs
    """
    if not message or "data:" not in message or "base64," not in message:
        return message

    agixt_uri = getenv("AGIXT_URI")
    # Use os.getcwd()/WORKSPACE to match the Workspace manager's path
    # (not WORKING_DIRECTORY env which may point to a different location)
    working_directory = os.path.join(os.getcwd(), "WORKSPACE")

    # Hash agent_id to match workspace directory pattern
    agent_hash = hashlib.sha256(str(agent_id).encode()).hexdigest()[:16]
    agent_folder = f"agent_{agent_hash}"

    def _process_data_url(is_image, alt_text, data_url):
        """Process a single data URL match and return the replacement string."""
        try:
            # Parse MIME type and base64 payload from the data URL
            if ";base64," not in data_url:
                return None
            mime_part, base64_data = data_url.split(";base64,", 1)
            mime_type = mime_part[5:]  # Strip "data:" prefix
            base64_data = base64_data.strip()

            # Validate base64 data contains only valid characters
            if not base64_data or not _RE_BASE64_CHARS.fullmatch(base64_data):
                return None

            # Check size threshold - only extract large data URLs
            data_size = len(base64_data) * 3 // 4  # Approximate decoded size
            if data_size < _DATA_URL_SIZE_THRESHOLD:
                return None  # Leave small data URLs inline

            # Decode the base64 data
            file_data = base64.b64decode(base64_data)

            # Strip MIME type parameters for extension lookup
            # e.g., "audio/webm;codecs=opus" -> "audio/webm"
            base_mime = mime_type.split(";")[0].strip()

            # Determine file extension from MIME type
            ext = _MIME_TO_EXT.get(base_mime, "")
            if not ext:
                # Try to extract from base MIME type
                parts = base_mime.split("/")
                if len(parts) == 2:
                    ext = f".{parts[1]}"
                else:
                    ext = ".bin"

            # Use alt text as filename if it has an extension, otherwise generate one
            if alt_text and "." in alt_text:
                filename = _sanitize_filename(alt_text, ext)
            else:
                filename = _sanitize_filename(f"{uuid.uuid4().hex[:12]}{ext}", ext)

            # Build the workspace file path
            # Sanitize conversation_id to prevent path traversal
            safe_conv_id = os.path.basename(str(conversation_id))
            if not safe_conv_id or safe_conv_id in (".", ".."):
                safe_conv_id = "unknown_conversation"
            if os.path.isabs(safe_conv_id) or ".." in safe_conv_id:
                logging.warning(
                    "Rejected unsafe conversation_id for workspace path; "
                    "falling back to generated directory name."
                )
                safe_conv_id = uuid.uuid4().hex[:12]

            workspace_root = os.path.realpath(
                os.path.join(working_directory, agent_folder)
            )
            # _safe_join_path uses realpath+startswith (CodeQL-recognised
            # sanitizer) so the taint chain is broken for downstream uses.
            try:
                workspace_dir = _safe_join_path(workspace_root, safe_conv_id)
            except ValueError:
                logging.warning(
                    "Rejected unsafe workspace_dir; falling back to generated directory name."
                )
                workspace_dir = _safe_join_path(workspace_root, uuid.uuid4().hex[:12])
            os.makedirs(workspace_dir, exist_ok=True)

            # Construct the final file path with fully sanitized filename
            filename = _sanitize_filename(filename, ext)
            try:
                file_path = _safe_join_path(workspace_dir, filename)
            except ValueError:
                filename = _sanitize_filename(f"{uuid.uuid4().hex[:12]}{ext}", ext)
                file_path = _safe_join_path(workspace_dir, filename)

            # Handle filename collisions (e.g., multiple "recording.webm" files)
            if os.path.exists(file_path):
                name_part, ext_part = os.path.splitext(filename)
                filename = _sanitize_filename(
                    f"{name_part}_{uuid.uuid4().hex[:8]}{ext_part}",
                    ext_part or ext,
                )
                try:
                    file_path = _safe_join_path(workspace_dir, filename)
                except ValueError:
                    filename = _sanitize_filename(f"{uuid.uuid4().hex[:12]}{ext}", ext)
                    file_path = _safe_join_path(workspace_dir, filename)

            # Write the file
            with open(file_path, "wb") as f:
                f.write(file_data)

            # Build the /outputs/ URL
            # Use the raw agent_id (not the hashed folder name) because
            # the serve_file endpoint hashes agent_id via _get_local_cache_path
            output_url = f"{agixt_uri}/outputs/{agent_id}/{conversation_id}/{filename}"

            # Determine if it should be an image (!) or link markdown
            if is_image:
                return f"![{alt_text}]({output_url})"
            else:
                return f"[{alt_text}]({output_url})"

        except Exception as e:
            logging.warning(f"Failed to extract data URL to workspace: {e}")
            return None  # Return None to keep original on failure

    # Use imperative O(n) parser instead of regex to avoid polynomial
    # backtracking (CodeQL: polynomial regular expression on uncontrolled data)
    matches = _find_markdown_data_urls(message)
    if not matches:
        return message

    # Build result by splicing original string with replacements
    parts = []
    last_end = 0
    for start, end, is_img, alt, data_url in matches:
        replacement = _process_data_url(is_img, alt, data_url)
        if replacement is not None:
            parts.append(message[last_end:start])
            parts.append(replacement)
            last_end = end
    parts.append(message[last_end:])
    return "".join(parts)


def _get_conversation_cache_key(conversation_name: str, user_id: str) -> str:
    return f"conversation_id:{user_id}:{conversation_name}"


def invalidate_conversation_cache(user_id: str = None, conversation_name: str = None):
    """Invalidate conversation cache entries (uses SharedCache)."""
    if user_id is None:
        shared_cache.delete_pattern("conversation_id:*")
    elif conversation_name:
        cache_key = _get_conversation_cache_key(conversation_name, str(user_id))
        shared_cache.delete(cache_key)
    else:
        # Invalidate all entries for this user
        shared_cache.delete_pattern(f"conversation_id:{user_id}:*")


def mark_conversation_updated(conversation_id: str):
    """Mark a conversation as updated in SharedCache for poll-skip optimization.

    The WebSocket poll loop checks this timestamp before hitting the DB.
    If the cached timestamp hasn't changed since the last poll, all DB
    queries are skipped entirely — turning a 5-8 query poll cycle into
    a microsecond cache lookup.
    """
    try:
        shared_cache.set(
            f"conv_updated:{conversation_id}",
            datetime.now().isoformat(),
            ttl=120,  # 2 min TTL — polls run every 0.5-3s so this is plenty
        )
    except Exception:
        pass  # Cache miss is fine — poll will just hit DB as before


async def broadcast_message_to_conversation(
    conversation_id: str, event_type: str, message_data: dict
) -> int:
    """
    Broadcast a message event to all WebSocket listeners for a conversation.

    This is an async function that should be called from extensions that want to
    send real-time updates to connected WebSocket clients.

    Args:
        conversation_id: The conversation ID to broadcast to
        event_type: Either 'message_added' or 'message_updated'
        message_data: The message data to send (should include id, role, message, etc.)

    Returns:
        Number of WebSocket connections that received the broadcast
    """
    try:
        # Import here to avoid circular imports
        from endpoints.Conversation import conversation_message_broadcaster

        # Mark conversation updated in SharedCache so poll loops can skip DB queries
        mark_conversation_updated(conversation_id)

        return await conversation_message_broadcaster.broadcast_message_event(
            conversation_id, event_type, message_data
        )
    except Exception as e:
        logging.warning(
            f"Failed to broadcast message to conversation {conversation_id}: {e}"
        )
        return 0


def broadcast_message_sync(conversation_id: str, event_type: str, message_data: dict):
    """
    Synchronous wrapper for broadcast_message_to_conversation.

    Use this from synchronous code (like extensions) to broadcast messages.
    Uses Redis pub/sub for cross-worker distribution when available.
    """
    logging.debug(
        f"broadcast_message_sync called: conv={conversation_id}, type={event_type}, msg_id={message_data.get('id')}"
    )
    # Mark conversation updated in SharedCache so poll loops can skip DB queries
    mark_conversation_updated(conversation_id)
    try:
        # Import broadcaster to use Redis pub/sub
        from endpoints.Conversation import conversation_message_broadcaster

        # Try Redis pub/sub first - this is synchronous and works from any thread
        if conversation_message_broadcaster.publish_to_redis(
            conversation_id, event_type, message_data
        ):
            logging.debug(f"broadcast_message_sync: published to Redis")
            return

        # Fallback to main event loop scheduling if Redis not available
        main_loop = conversation_message_broadcaster.get_main_loop()

        if main_loop is not None:
            # Use the broadcaster's main event loop for cross-thread safety
            future = asyncio.run_coroutine_threadsafe(
                broadcast_message_to_conversation(
                    conversation_id, event_type, message_data
                ),
                main_loop,
            )
            # Don't wait - fire and forget for streaming performance
            logging.debug(
                f"broadcast_message_sync: scheduled on main loop (loop={id(main_loop)})"
            )
        else:
            logging.warning(f"broadcast_message_sync: main loop not available yet")
    except Exception as e:
        logging.warning(f"broadcast_message_sync error: {e}")


def get_conversation_id_by_name(conversation_name, user_id, create_if_missing=True):
    """Get the conversation ID by name, optionally creating it if it doesn't exist.

    Args:
        conversation_name: The name of the conversation
        user_id: The user ID who owns the conversation
        create_if_missing: If True (default), creates the conversation if it doesn't exist.
                          If False, returns None when conversation doesn't exist.
    """
    user_id = str(user_id)
    cache_key = _get_conversation_cache_key(conversation_name, user_id)

    # Only use cache when create_if_missing=True, because cached IDs might reference
    # deleted conversations and we need to verify existence when not creating
    if create_if_missing:
        cached = shared_cache.get(cache_key)
        if cached is not None:
            return cached

    session = get_session()
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.name == conversation_name,
            Conversation.user_id == user_id,
        )
        .first()
    )
    if not conversation:
        # Check group conversations accessible via company membership
        company_ids = _get_user_company_ids(user_id)
        if company_ids:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == conversation_name,
                    Conversation.company_id.in_(company_ids),
                    Conversation.conversation_type.in_(
                        ["group", "dm", "thread", "channel"]
                    ),
                )
                .first()
            )
    if not conversation:
        # Fallback: conversations where user is a participant (handles DMs without company_id)
        participant_conv = (
            session.query(ConversationParticipant)
            .join(
                Conversation,
                Conversation.id == ConversationParticipant.conversation_id,
            )
            .filter(
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.participant_type == "user",
                ConversationParticipant.status == "active",
                Conversation.name == conversation_name,
            )
            .first()
        )
        if participant_conv:
            conversation = (
                session.query(Conversation)
                .filter(Conversation.id == participant_conv.conversation_id)
                .first()
            )
    if not conversation:
        if not create_if_missing:
            session.close()
            # Clear any stale cache entry
            shared_cache.delete(cache_key)
            return None
        # Create conversation directly to avoid recursive call to Conversations.__init__
        conversation = Conversation(name=conversation_name, user_id=user_id)
        session.add(conversation)
        session.commit()
        conversation_id = str(conversation.id)
    else:
        conversation_id = str(conversation.id)
    session.close()

    # Cache the result in SharedCache
    shared_cache.set(cache_key, conversation_id, ttl=_conversation_id_cache_ttl)
    return conversation_id


def get_conversation_name_by_id(conversation_id, user_id):
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name("-", user_id)
        return "-"

    # Check cache first (avoids 2-4 DB queries per call)
    cache_key = f"conv_name:{conversation_id}:{user_id}"
    cached = shared_cache.get(cache_key)
    if cached is not None:
        return cached

    session = get_session()
    try:
        # First try: user's own conversation
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            # Second try: group conversations accessible via company membership
            company_ids = _get_user_company_ids(user_id)
            if company_ids:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.id == conversation_id,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                    .first()
                )
        if not conversation:
            # Third try: conversations where user is a participant (handles DMs without company_id)
            participant_conv = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.participant_type == "user",
                    ConversationParticipant.status == "active",
                )
                .first()
            )
            if participant_conv:
                conversation = (
                    session.query(Conversation)
                    .filter(Conversation.id == conversation_id)
                    .first()
                )
        if not conversation:
            return "-"
        conversation_name = conversation.name
        shared_cache.set(cache_key, conversation_name, ttl=30)
        return conversation_name
    finally:
        session.close()


def get_conversation_name_by_message_id(message_id, user_id):
    """Get the conversation name that contains a specific message for a user."""
    session = get_session()
    result = (
        session.query(Conversation.name)
        .join(Message, Message.conversation_id == Conversation.id)
        .filter(
            Message.id == message_id,
            Conversation.user_id == user_id,
        )
        .first()
    )
    session.close()
    return result[0] if result else None


class Conversations:
    def __init__(
        self,
        conversation_name=None,
        user=DEFAULT_USER,
        conversation_id=None,
        create_if_missing=True,
    ):
        self.user = user
        self.conversation_id = conversation_id
        self.conversation_name = conversation_name

        # Cache user_id for this instance to avoid repeated DB lookups
        # get_user_id already uses SharedCache for cross-worker consistency
        self._user_id = get_user_id(user)

        # Resolve missing ID or name from the other
        user_id = self._user_id
        if not self.conversation_id and self.conversation_name:
            self.conversation_id = get_conversation_id_by_name(
                conversation_name=conversation_name,
                user_id=user_id,
                create_if_missing=create_if_missing,
            )
        elif not self.conversation_name and self.conversation_id:
            self.conversation_name = get_conversation_name_by_id(
                conversation_id=conversation_id, user_id=user_id
            )
        elif not self.conversation_name and not self.conversation_id:
            self.conversation_name = "-"
            self.conversation_id = get_conversation_id_by_name(
                conversation_name="-", user_id=user_id
            )

    def get_current_name_from_db(self):
        """
        Get the current conversation name directly from the database.
        This is useful for detecting renames that happened since the object was created.

        Returns:
            str: The current name from the database, or None if not found
        """
        if not self.conversation_id:
            return self.conversation_name

        session = get_session()
        try:
            user_id = self._user_id
            if not user_id:
                return self.conversation_name

            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.id == self.conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )
            if conversation:
                return conversation.name
            return self.conversation_name
        finally:
            session.close()

    def export_conversation(self):
        session = get_session()
        try:
            user_id = self._user_id
            if not self.conversation_name:
                self.conversation_name = "-"
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )
            history = {"interactions": []}
            if not conversation:
                return history
            messages = (
                session.query(Message)
                .filter(Message.conversation_id == conversation.id)
                .all()
            )
            for message in messages:
                interaction = {
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                }
                history["interactions"].append(interaction)
            return history
        finally:
            session.close()

    def get_conversations(self):
        session = get_session()
        user_id = self._user_id

        # Use EXISTS subquery instead of JOIN+DISTINCT for O(1) existence check per row
        conversations = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .filter(exists().where(Message.conversation_id == Conversation.id))
            .order_by(Conversation.updated_at.desc())
            .all()
        )

        conversation_list = [conversation.name for conversation in conversations]
        session.close()
        return conversation_list

    def get_conversations_with_ids(self):
        session = get_session()
        user_id = self._user_id

        # Use EXISTS subquery instead of JOIN+DISTINCT for O(1) existence check per row
        conversations = (
            session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .filter(exists().where(Message.conversation_id == Conversation.id))
            .order_by(Conversation.updated_at.desc())
            .all()
        )

        result = {
            str(conversation.id): conversation.name for conversation in conversations
        }
        session.close()
        return result

    def get_agent_id(self, user_id):
        # Return cached agent_id if available (set by log_interaction or prior calls)
        if hasattr(self, "_cached_agent_id") and self._cached_agent_id:
            return self._cached_agent_id
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            # Get last non-USER agent name in the same session instead of calling
            # get_last_agent_name() which opens a separate session
            last_msg = (
                session.query(Message.role)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.role != "USER",
                    Message.role != "user",
                )
                .order_by(Message.timestamp.desc())
                .first()
            )
            agent_name = last_msg[0] if last_msg else "AGiXT"
            agent = (
                session.query(Agent)
                .filter(Agent.name == agent_name, Agent.user_id == user_id)
                .first()
            )
            try:
                agent_id = str(agent.id)
            except:
                agent_id = None
            if not agent_id:
                agent = session.query(Agent).filter(Agent.user_id == user_id).first()
                try:
                    agent_id = str(agent.id)
                except:
                    agent_id = None
            self._cached_agent_id = agent_id
            return agent_id
        finally:
            session.close()

    def get_conversations_with_detail(self, limit=None, offset=0):
        """
        OPTIMIZED: Single query to get all conversation details with notifications
        and last message timestamps in one batch instead of N+1 queries.
        Also includes DM conversations where the user is a participant (not just owner).

        Args:
            limit: Optional max number of conversations to return. When set, only
                   the top N conversations (by updated_at desc) are processed for
                   expensive batch operations (unread counts, DM names, agent roles).
            offset: Skip this many conversations before applying limit.
        """
        session = get_session()
        user_id = self._user_id
        if not user_id:
            session.close()
            return {}

        # Pre-fetch timezone ONCE for fast inline conversion
        # (avoids opening a new DB session per convert_time call)
        _convert_time_fast = _make_time_converter(user_id)

        # Get default agent_id once (not per conversation - they all share the same user)
        default_agent = session.query(Agent).filter(Agent.user_id == user_id).first()
        default_agent_id = str(default_agent.id) if default_agent else None

        # Get conversation IDs where this user is a participant (for DMs they didn't create)
        participant_conv_ids = (
            session.query(ConversationParticipant.conversation_id)
            .filter(
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.participant_type == "user",
                ConversationParticipant.status == "active",
            )
            .all()
        )
        participant_conv_id_list = [str(row[0]) for row in participant_conv_ids]

        # Get owned conversation IDs to scope the last_message subquery
        owned_conv_ids = (
            session.query(Conversation.id).filter(Conversation.user_id == user_id).all()
        )
        owned_conv_id_list = [str(row[0]) for row in owned_conv_ids]
        all_relevant_conv_ids = list(set(owned_conv_id_list + participant_conv_id_list))

        # Subquery to get max message timestamp per conversation
        # BOUNDED to only user-relevant conversations (avoids full table scan)
        last_message_subq = (
            session.query(
                Message.conversation_id,
                func.max(Message.timestamp).label("last_message_time"),
            )
            .filter(Message.conversation_id.in_(all_relevant_conv_ids))
            .group_by(Message.conversation_id)
            .subquery()
        )

        # Single query: conversations owned by user OR where user is a participant
        # Exclude group channels and threads from DM/conversation list
        ownership_filter = Conversation.user_id == user_id
        participant_filter = (
            Conversation.id.in_(participant_conv_id_list)
            if participant_conv_id_list
            else False
        )

        # Main query: non-group, non-thread conversations
        main_conversations = (
            session.query(
                Conversation,
                last_message_subq.c.last_message_time,
            )
            .outerjoin(
                last_message_subq,
                last_message_subq.c.conversation_id == Conversation.id,
            )
            .filter(or_(ownership_filter, participant_filter))
            # Exclude group channels and threads from DM/conversation list
            .filter(
                or_(
                    Conversation.conversation_type.is_(None),
                    Conversation.conversation_type.notin_(["group", "thread"]),
                )
            )
            # Only include conversations that have at least one message
            .filter(exists().where(Message.conversation_id == Conversation.id))
            .all()
        )

        # Second query: DM/private threads (threads whose parent is a non-group conversation)
        # Get IDs of the user's DM/private conversations to find their threads
        dm_parent_ids = [
            str(c.id)
            for c, _ in main_conversations
            if c.conversation_type in (None, "dm", "private")
        ]
        dm_threads = []
        if dm_parent_ids:
            dm_threads = (
                session.query(
                    Conversation,
                    last_message_subq.c.last_message_time,
                )
                .outerjoin(
                    last_message_subq,
                    last_message_subq.c.conversation_id == Conversation.id,
                )
                .filter(
                    Conversation.conversation_type == "thread",
                    Conversation.parent_id.in_(dm_parent_ids),
                )
                .all()
            )

        conversations = main_conversations + dm_threads

        # Apply early pagination BEFORE expensive batch queries.
        # Sort by last_message_time (or conversation updated_at as fallback) descending,
        # then slice to limit+offset. This avoids computing unread counts, DM names,
        # and agent roles for conversations that won't be returned.
        if limit is not None and limit > 0:
            conversations.sort(
                key=lambda pair: pair[1] or pair[0].updated_at or "",
                reverse=True,
            )
            conversations = conversations[offset : offset + limit]

        # Batch-fetch participant records for this user to get last_read_at
        all_conv_ids = [str(c.id) for c, _ in conversations]
        participant_map = {}
        if all_conv_ids:
            user_participants = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id.in_(all_conv_ids),
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.participant_type == "user",
                    ConversationParticipant.status == "active",
                )
                .all()
            )
            for p in user_participants:
                participant_map[str(p.conversation_id)] = p

        # Build result dict with all data from single query
        # For DM conversations, look up participant names so the frontend
        # can display "DM with <name>" instead of the raw conversation name.
        dm_conv_ids = [
            str(c.id) for c, _ in conversations if c.conversation_type == "dm"
        ]
        dm_participants = {}
        if dm_conv_ids:
            parts = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id.in_(dm_conv_ids),
                    ConversationParticipant.status == "active",
                )
                .all()
            )
            # Group participants by conversation_id
            for p in parts:
                cid = str(p.conversation_id)
                dm_participants.setdefault(cid, []).append(p)

        # Batch load user/agent names for DM participants
        dm_user_ids = set()
        dm_agent_ids = set()
        for plist in dm_participants.values():
            for p in plist:
                if p.participant_type == "user" and p.user_id:
                    dm_user_ids.add(str(p.user_id))
                elif p.participant_type == "agent" and p.agent_id:
                    dm_agent_ids.add(str(p.agent_id))

        user_name_map = {}
        if dm_user_ids:
            users = session.query(User).filter(User.id.in_(list(dm_user_ids))).all()
            for u in users:
                name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email
                user_name_map[str(u.id)] = name

        agent_name_map = {}
        if dm_agent_ids:
            agents = session.query(Agent).filter(Agent.id.in_(list(dm_agent_ids))).all()
            for a in agents:
                agent_name_map[str(a.id)] = a.name

        # Batch-fetch the first agent role for each conversation to identify
        # which agent the conversation is with (for frontend sorting).
        # Uses a window function to efficiently get the first non-USER message per conv.
        conv_agent_role_map = {}
        private_conv_ids = [
            str(c.id)
            for c, _ in conversations
            if c.conversation_type is None or c.conversation_type in ("private", "dm")
        ]
        if private_conv_ids:
            # Get first non-USER, non-ACTIVITY message role per conversation
            # Use a subquery to find the earliest timestamp per conversation,
            # then join back to get only those rows (avoids loading ALL messages).
            min_ts_subq = (
                session.query(
                    Message.conversation_id,
                    func.min(Message.timestamp).label("min_ts"),
                )
                .filter(
                    Message.conversation_id.in_(private_conv_ids),
                    Message.role != "USER",
                    ~Message.content.like("[ACTIVITY]%"),
                    ~Message.content.like("[SUBACTIVITY]%"),
                )
                .group_by(Message.conversation_id)
                .subquery()
            )
            first_agent_msgs = (
                session.query(
                    Message.conversation_id,
                    Message.role,
                )
                .join(
                    min_ts_subq,
                    and_(
                        Message.conversation_id == min_ts_subq.c.conversation_id,
                        Message.timestamp == min_ts_subq.c.min_ts,
                    ),
                )
                .filter(
                    Message.role != "USER",
                    ~Message.content.like("[ACTIVITY]%"),
                    ~Message.content.like("[SUBACTIVITY]%"),
                )
                .all()
            )
            for conv_id_val, role in first_agent_msgs:
                cid = str(conv_id_val)
                if cid not in conv_agent_role_map:
                    conv_agent_role_map[cid] = role

        # --- Batch unread counts (replaces N+1 per-conversation COUNT queries) ---
        unread_count_map = {}  # conv_id -> bool (has unread)
        dm_conv_id_set = set(dm_conv_ids)

        # Build per-conversation baselines from participant data
        with_baseline_dm = {}  # conv_id -> baseline datetime (DM conversations)
        with_baseline_other = {}  # conv_id -> baseline datetime (non-DM conversations)
        no_participant_ids = []  # conversations with no participant record

        for conv_id_str in all_conv_ids:
            participant = participant_map.get(conv_id_str)
            if participant:
                baseline = participant.last_read_at or participant.joined_at
                if baseline:
                    if conv_id_str in dm_conv_id_set:
                        with_baseline_dm[conv_id_str] = baseline
                    else:
                        with_baseline_other[conv_id_str] = baseline
                # else: participant exists but no baseline -> 0 unread
            else:
                no_participant_ids.append(conv_id_str)

        # Batch query 1: DM conversations with baselines
        # Count messages from OTHER users after the baseline
        if with_baseline_dm:
            baseline_case = case(
                *[
                    (Message.conversation_id == cid, ts)
                    for cid, ts in with_baseline_dm.items()
                ],
            )
            rows = (
                session.query(
                    Message.conversation_id,
                    func.count().label("cnt"),
                )
                .filter(
                    Message.conversation_id.in_(list(with_baseline_dm.keys())),
                    Message.timestamp > baseline_case,
                    ~Message.content.like("[ACTIVITY]%"),
                    ~Message.content.like("[SUBACTIVITY]%"),
                    or_(
                        Message.sender_user_id != str(user_id),
                        Message.role != "USER",
                    ),
                )
                .group_by(Message.conversation_id)
                .all()
            )
            for row in rows:
                unread_count_map[str(row.conversation_id)] = row.cnt > 0

        # Batch query 2: Non-DM conversations with baselines
        # Count non-USER messages after the baseline
        if with_baseline_other:
            baseline_case = case(
                *[
                    (Message.conversation_id == cid, ts)
                    for cid, ts in with_baseline_other.items()
                ],
            )
            rows = (
                session.query(
                    Message.conversation_id,
                    func.count().label("cnt"),
                )
                .filter(
                    Message.conversation_id.in_(list(with_baseline_other.keys())),
                    Message.timestamp > baseline_case,
                    ~Message.content.like("[ACTIVITY]%"),
                    ~Message.content.like("[SUBACTIVITY]%"),
                    Message.role != "USER",
                )
                .group_by(Message.conversation_id)
                .all()
            )
            for row in rows:
                unread_count_map[str(row.conversation_id)] = row.cnt > 0

        # Batch query 3: No-participant conversations (legacy notify flag)
        if no_participant_ids:
            rows = (
                session.query(
                    Message.conversation_id,
                    func.count().label("cnt"),
                )
                .filter(
                    Message.conversation_id.in_(no_participant_ids),
                    Message.notify == True,
                )
                .group_by(Message.conversation_id)
                .all()
            )
            for row in rows:
                unread_count_map[str(row.conversation_id)] = row.cnt > 0

        result = {}
        for conversation, last_message_time in conversations:
            # Use last message time if available, otherwise use conversation updated_at
            effective_updated_at = last_message_time or conversation.updated_at
            conv_id = str(conversation.id)

            has_notifications = unread_count_map.get(conv_id, False)

            # For DMs, build a display name from the other participants
            display_name = conversation.name
            dm_participant_names = []
            if conversation.conversation_type == "dm" and conv_id in dm_participants:
                for p in dm_participants[conv_id]:
                    pid = (
                        str(p.user_id)
                        if p.participant_type == "user"
                        else str(p.agent_id)
                    )
                    # Skip the current user
                    if p.participant_type == "user" and str(p.user_id) == str(user_id):
                        continue
                    if p.participant_type == "user" and pid in user_name_map:
                        dm_participant_names.append(user_name_map[pid])
                    elif p.participant_type == "agent" and pid in agent_name_map:
                        dm_participant_names.append(agent_name_map[pid])
                if dm_participant_names:
                    display_name = ", ".join(dm_participant_names)

            # For DM agent conversations, use agent participant name as fallback
            dm_agent_name = None
            if conversation.conversation_type == "dm" and conv_id in dm_participants:
                for p in dm_participants[conv_id]:
                    if (
                        p.participant_type == "agent"
                        and str(p.agent_id) in agent_name_map
                    ):
                        dm_agent_name = agent_name_map[str(p.agent_id)]
                        break

            result[conv_id] = {
                "name": conversation.name,
                "display_name": display_name,
                "agent_id": default_agent_id,
                "agent_name": conv_agent_role_map.get(conv_id) or dm_agent_name,
                "conversation_type": conversation.conversation_type,
                "created_at": _convert_time_fast(conversation.created_at),
                "updated_at": _convert_time_fast(effective_updated_at),
                "has_notifications": has_notifications,
                "summary": conversation.summary or None,
                "attachment_count": conversation.attachment_count or 0,
                "pin_order": conversation.pin_order,
                "parent_id": (
                    str(conversation.parent_id) if conversation.parent_id else None
                ),
                "locked": getattr(conversation, "locked", False) or False,
            }

        # Sort by updated_at descending (most recent first)
        result = dict(
            sorted(
                result.items(),
                key=lambda item: item[1]["updated_at"],
                reverse=True,
            )
        )

        session.close()
        return result

    def get_notifications(self):
        session = get_session()
        user_id = self._user_id

        # Pre-fetch timezone ONCE for fast inline conversion
        _convert_time_fast = _make_time_converter(user_id)

        # Get all messages with notify=True for this user's conversations
        notifications = (
            session.query(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id, Message.notify == True)
            .order_by(Message.timestamp.desc())
            .all()
        )

        result = []
        for message, conversation in notifications:
            result.append(
                {
                    "conversation_id": str(conversation.id),
                    "conversation_name": conversation.name,
                    "message_id": str(message.id),
                    "message": message.content,
                    "role": message.role,
                    "timestamp": _convert_time_fast(message.timestamp),
                }
            )

        session.close()
        return result

    def search_messages(
        self,
        query: str,
        conversation_types: list = None,
        company_id: str = None,
        limit: int = 50,
    ):
        """
        Search message content across all conversations the user has access to.

        Args:
            query: Text to search for in message content
            conversation_types: Optional filter list, e.g. ['group', 'dm', 'private', 'thread']
            company_id: Optional company/group ID to restrict search to
            limit: Max results to return (default 50)

        Returns:
            List of search result dicts with message and conversation info.
        """
        session = get_session()
        user_id = self._user_id
        if not user_id or not query or not query.strip():
            session.close()
            return []

        search_term = f"%{query.strip()}%"

        # Get conversation IDs where user is owner
        owned_conv_ids = (
            session.query(Conversation.id).filter(Conversation.user_id == user_id).all()
        )
        owned_ids = [str(row[0]) for row in owned_conv_ids]

        # Get conversation IDs where user is an active participant
        participant_conv_ids = (
            session.query(ConversationParticipant.conversation_id)
            .filter(
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.participant_type == "user",
                ConversationParticipant.status == "active",
            )
            .all()
        )
        participant_ids = [str(row[0]) for row in participant_conv_ids]

        all_accessible_ids = list(set(owned_ids + participant_ids))
        if not all_accessible_ids:
            session.close()
            return []

        # Build message query with filters
        msg_query = (
            session.query(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Message.conversation_id.in_(all_accessible_ids),
                Message.content.ilike(search_term),
                # Exclude activity messages
                ~Message.content.like("[ACTIVITY]%"),
                ~Message.content.like("[SUBACTIVITY]%"),
            )
        )

        if conversation_types:
            msg_query = msg_query.filter(
                Conversation.conversation_type.in_(conversation_types)
            )

        if company_id:
            msg_query = msg_query.filter(Conversation.company_id == company_id)

        messages = msg_query.order_by(Message.timestamp.desc()).limit(limit).all()

        # Batch load sender user names
        sender_ids = set()
        for msg, _ in messages:
            if msg.sender_user_id:
                sender_ids.add(str(msg.sender_user_id))
        sender_name_map = {}
        if sender_ids:
            users = session.query(User).filter(User.id.in_(list(sender_ids))).all()
            for u in users:
                name = (
                    f"{u.first_name} {u.last_name}".strip() if u.first_name else u.email
                )
                sender_name_map[str(u.id)] = name

        # Pre-fetch timezone ONCE for fast inline conversion
        _convert_time_fast = _make_time_converter(user_id)

        results = []
        for message, conversation in messages:
            # Truncate content for preview (strip markdown links for cleaner preview)
            content = message.content
            if len(content) > 200:
                content = content[:200] + "..."

            sender_name = None
            if message.sender_user_id:
                sender_name = sender_name_map.get(str(message.sender_user_id), None)
            elif message.role == "USER":
                sender_name = "You"

            results.append(
                {
                    "message_id": str(message.id),
                    "conversation_id": str(conversation.id),
                    "conversation_name": conversation.name,
                    "conversation_type": conversation.conversation_type or "private",
                    "company_id": (
                        str(conversation.company_id)
                        if conversation.company_id
                        else None
                    ),
                    "content": content,
                    "role": message.role,
                    "sender_name": sender_name,
                    "timestamp": _convert_time_fast(message.timestamp),
                }
            )

        session.close()
        return results

    def get_conversation_changes(self, since_timestamp=None, last_known_ids=None):
        """
        Efficiently get only the changes since the last check.

        Args:
            since_timestamp: Only return messages created/updated after this time
            last_known_ids: Set of message IDs we already have - used to detect deletions

        Returns:
            {
                "new_messages": [...],      # Messages added since last check
                "updated_messages": [...],  # Messages updated since last check
                "deleted_ids": [...],       # IDs of deleted messages
                "current_count": int        # Current total message count
            }
        """
        # SharedCache fast-path: skip DB queries entirely if nothing has changed
        # since our last poll. The broadcast functions set this timestamp whenever
        # a message is added/updated/deleted.
        _empty_result = {
            "new_messages": [],
            "updated_messages": [],
            "deleted_ids": [],
            "current_count": len(last_known_ids) if last_known_ids else 0,
        }
        if self.conversation_id and since_timestamp is not None:
            cache_key = f"conv_updated:{self.conversation_id}"
            cached_ts = shared_cache.get(cache_key)
            if cached_ts is not None:
                try:
                    last_update = datetime.fromisoformat(cached_ts)
                    if last_update <= since_timestamp:
                        # Nothing changed since last poll — skip all DB work
                        return _empty_result
                except (ValueError, TypeError):
                    pass  # Malformed cache entry — fall through to DB
            elif last_known_ids is not None and len(last_known_ids) > 0:
                # No cache entry at all (no broadcasts happened recently).
                # If we already have tracked IDs, it's very likely nothing changed.
                # Fall through to DB to be safe (cache miss).
                pass

        session = get_session()
        try:
            return self._get_conversation_changes_db(
                session, since_timestamp, last_known_ids
            )
        finally:
            session.close()

    def _get_conversation_changes_db(self, session, since_timestamp, last_known_ids):
        """Internal: runs the actual DB queries for get_conversation_changes."""
        user_id = self._user_id

        # Get conversation ID
        if self.conversation_id:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.id == self.conversation_id,
                    Conversation.user_id == user_id,
                )
                .first()
            )
            # Fallback: check group conversations accessible via company membership
            if not conversation:
                company_ids = _get_user_company_ids(user_id)
                if company_ids:
                    conversation = (
                        session.query(Conversation)
                        .filter(
                            Conversation.id == self.conversation_id,
                            Conversation.company_id.in_(company_ids),
                            Conversation.conversation_type.in_(
                                ["group", "dm", "thread", "channel"]
                            ),
                        )
                        .first()
                    )
        else:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )

        if not conversation:
            return {
                "new_messages": [],
                "updated_messages": [],
                "deleted_ids": [],
                "current_count": 0,
            }

        # Get current message count and IDs for deletion detection
        from sqlalchemy import func

        current_count = (
            session.query(func.count(Message.id))
            .filter(Message.conversation_id == conversation.id)
            .scalar()
        )

        # Optimized deletion detection: only fetch all IDs if the count
        # differs from what the client has, avoiding O(messages) per poll cycle
        deleted_ids = []
        if last_known_ids is not None and len(last_known_ids) > 0:
            if current_count != len(last_known_ids):
                # Count changed — something was added or deleted, fetch IDs to diff
                id_query = (
                    session.query(Message.id)
                    .filter(Message.conversation_id == conversation.id)
                    .all()
                )
                current_ids = {str(row[0]) for row in id_query}
                last_known_str = {str(id) for id in last_known_ids}
                deleted_ids = list(last_known_str - current_ids)

        new_messages = []
        updated_messages = []

        if since_timestamp is not None:
            # Pre-fetch timezone ONCE for fast inline conversion
            # (avoids opening a new DB session per convert_time call)
            _convert_time_fast = _make_time_converter(user_id)

            agixt_uri = getenv("AGIXT_URI")

            # Query for new messages (created at or after timestamp)
            new_query = (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation.id,
                    Message.timestamp >= since_timestamp,
                )
                .order_by(Message.timestamp.asc())
                .all()
            )

            for message in new_query:
                msg = {
                    "id": message.id,
                    "role": message.role,
                    "message": str(message.content).replace(
                        "http://localhost:7437", agixt_uri
                    ),
                    "timestamp": _convert_time_fast(message.timestamp),
                    "updated_at": _convert_time_fast(message.updated_at),
                    "updated_by": message.updated_by,
                    "feedback_received": message.feedback_received,
                    "timestamp_utc": message.timestamp,
                    "updated_at_utc": message.updated_at,
                    "sender_user_id": (
                        str(message.sender_user_id) if message.sender_user_id else None
                    ),
                }
                new_messages.append(msg)

            # Pre-fetch sender user info for all new messages
            all_new_sender_ids = {
                str(m.sender_user_id) for m in new_query if m.sender_user_id
            }

            # Query for updated messages - messages that have been edited since last check
            # This includes:
            # 1. Old messages (timestamp <= since_timestamp) that were edited (updated_at > since_timestamp)
            # 2. New messages (timestamp > since_timestamp) that were edited after creation (updated_at > timestamp)
            # The second case catches subactivity messages that are created then rapidly updated
            from sqlalchemy import or_

            updated_query = (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation.id,
                    Message.updated_by != None,  # Only actually edited messages
                    or_(
                        # Case 1: Old messages edited since last check
                        (Message.timestamp <= since_timestamp)
                        & (Message.updated_at > since_timestamp),
                        # Case 2: New messages edited after their creation
                        (Message.timestamp > since_timestamp)
                        & (Message.updated_at > Message.timestamp),
                    ),
                )
                .order_by(Message.timestamp.asc())
                .all()
            )

            # Collect IDs of messages already in new_messages to avoid duplicates
            # Convert to strings for consistent comparison since IDs can be UUIDs
            new_message_ids = {str(msg["id"]) for msg in new_messages}

            for message in updated_query:
                # Skip if this message is already in new_messages (avoid duplicates)
                if str(message.id) in new_message_ids:
                    continue
                msg = {
                    "id": message.id,
                    "role": message.role,
                    "message": str(message.content).replace(
                        "http://localhost:7437", agixt_uri
                    ),
                    "timestamp": _convert_time_fast(message.timestamp),
                    "updated_at": _convert_time_fast(message.updated_at),
                    "updated_by": message.updated_by,
                    "feedback_received": message.feedback_received,
                    "timestamp_utc": message.timestamp,
                    "updated_at_utc": message.updated_at,
                    "sender_user_id": (
                        str(message.sender_user_id) if message.sender_user_id else None
                    ),
                }
                updated_messages.append(msg)

            # Build sender lookup for all messages that have sender_user_id
            all_updated_sender_ids = {
                str(m.sender_user_id) for m in updated_query if m.sender_user_id
            }
            all_sender_ids = all_new_sender_ids | all_updated_sender_ids
            sender_users = {}
            if all_sender_ids:
                users = session.query(User).filter(User.id.in_(all_sender_ids)).all()
                sender_users = {
                    str(u.id): {
                        "id": str(u.id),
                        "email": u.email,
                        "first_name": u.first_name or "",
                        "last_name": u.last_name or "",
                        "avatar_url": getattr(u, "avatar_url", None),
                    }
                    for u in users
                }
            # Inject sender info into messages
            for msg in new_messages:
                if msg.get("sender_user_id"):
                    msg["sender"] = sender_users.get(msg["sender_user_id"])
                else:
                    msg["sender"] = None
            for msg in updated_messages:
                if msg.get("sender_user_id"):
                    msg["sender"] = sender_users.get(msg["sender_user_id"])
                else:
                    msg["sender"] = None

        return {
            "new_messages": new_messages,
            "updated_messages": updated_messages,
            "deleted_ids": deleted_ids,
            "current_count": current_count,
        }

    def get_conversation(self, limit=100, page=1):
        session = get_session()
        user_id = self._user_id
        if not self.conversation_name:
            self.conversation_name = "-"

        # Prefer conversation_id lookup to avoid duplicate name issues
        if self.conversation_id:
            # Single query with OR to check ownership, company membership, or participant status
            company_ids = _get_user_company_ids(user_id)

            participant_conv_ids = session.query(
                ConversationParticipant.conversation_id
            ).filter(
                ConversationParticipant.conversation_id == self.conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.participant_type == "user",
                ConversationParticipant.status == "active",
            )

            access_filters = [
                # Owner
                and_(
                    Conversation.id == self.conversation_id,
                    Conversation.user_id == user_id,
                ),
            ]
            if company_ids:
                access_filters.append(
                    # Company member
                    and_(
                        Conversation.id == self.conversation_id,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                )
            access_filters.append(
                # Participant
                and_(
                    Conversation.id == self.conversation_id,
                    Conversation.id.in_(participant_conv_ids),
                )
            )

            conversation = (
                session.query(Conversation).filter(or_(*access_filters)).first()
            )
        else:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )
        if not conversation:
            # Create the conversation
            conversation = Conversation(name=self.conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        offset = (page - 1) * limit
        # Get total message count for pagination support
        total_messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .count()
        )
        # Query most recent messages first (descending), then reverse to
        # chronological order.  This ensures that the default limit=100
        # returns the LATEST messages rather than the oldest, so the UI
        # shows the tail of the conversation immediately.
        messages = list(
            reversed(
                session.query(Message)
                .filter(Message.conversation_id == conversation.id)
                .order_by(Message.timestamp.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
        )
        if not messages:
            session.close()
            return {
                "interactions": [],
                "total": total_messages,
                "page": page,
                "limit": limit,
            }
        return_messages = []
        # Pre-fetch sender user info for all messages with sender_user_id
        sender_user_ids = {
            str(message.sender_user_id)
            for message in messages
            if message.sender_user_id
        }
        sender_users = {}
        if sender_user_ids:
            users = session.query(User).filter(User.id.in_(sender_user_ids)).all()
            sender_users = {
                str(u.id): {
                    "id": str(u.id),
                    "email": u.email,
                    "first_name": u.first_name or "",
                    "last_name": u.last_name or "",
                    "avatar_url": getattr(u, "avatar_url", None),
                }
                for u in users
            }
        # Pre-fetch all reactions for these messages
        message_ids = [str(m.id) for m in messages]
        reactions_map = {}
        try:
            all_reactions = (
                session.query(MessageReaction)
                .filter(MessageReaction.message_id.in_(message_ids))
                .all()
            )
            # Fetch user info for reaction users
            reaction_user_ids = {str(r.user_id) for r in all_reactions}
            reaction_users = {}
            if reaction_user_ids:
                r_users = (
                    session.query(User).filter(User.id.in_(reaction_user_ids)).all()
                )
                reaction_users = {
                    str(u.id): {
                        "email": u.email,
                        "first_name": u.first_name or "",
                    }
                    for u in r_users
                }
            for r in all_reactions:
                mid = str(r.message_id)
                if mid not in reactions_map:
                    reactions_map[mid] = []
                ru = reaction_users.get(str(r.user_id), {})
                reactions_map[mid].append(
                    {
                        "id": str(r.id),
                        "emoji": r.emoji,
                        "user_id": str(r.user_id),
                        "user_email": ru.get("email"),
                        "user_first_name": ru.get("first_name"),
                        "created_at": str(r.created_at) if r.created_at else None,
                    }
                )
        except Exception as e:
            logging.debug(f"Failed to fetch reactions: {e}")

        # Pre-fetch timezone ONCE for this user instead of per-message
        # (was doing 2 DB queries per message = 200 queries for 100 messages)
        _convert_time_fast = _make_time_converter(user_id)

        agixt_uri = getenv("AGIXT_URI")
        for message in messages:
            msg = {
                "id": message.id,
                "role": message.role,
                "message": str(message.content).replace(
                    "http://localhost:7437", agixt_uri
                ),
                "timestamp": _convert_time_fast(message.timestamp),
                "updated_at": _convert_time_fast(message.updated_at),
                "updated_by": message.updated_by,
                "feedback_received": message.feedback_received,
                # Raw UTC timestamps for WebSocket comparison
                "timestamp_utc": message.timestamp,
                "updated_at_utc": message.updated_at,
                # Group chat: sender user info
                "sender_user_id": (
                    str(message.sender_user_id) if message.sender_user_id else None
                ),
                "sender": (
                    sender_users.get(str(message.sender_user_id))
                    if message.sender_user_id
                    else None
                ),
                "reactions": reactions_map.get(str(message.id), []),
                "pinned": bool(message.pinned) if hasattr(message, "pinned") else False,
                "pinned_at": (
                    str(message.pinned_at)
                    if hasattr(message, "pinned_at") and message.pinned_at
                    else None
                ),
                "pinned_by": (
                    str(message.pinned_by)
                    if hasattr(message, "pinned_by") and message.pinned_by
                    else None
                ),
            }
            return_messages.append(msg)
        # Mark notifications as read AFTER retrieving messages so the UPDATE+COMMIT
        # doesn't block the read path.  This is not critical — if it fails, the user
        # simply sees the unread badge a bit longer.
        try:
            (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation.id,
                    Message.notify == True,
                )
                .update({"notify": False}, synchronize_session=False)
            )
            session.commit()
        except Exception:
            session.rollback()
        session.close()
        return {
            "interactions": return_messages,
            "total": total_messages,
            "page": page,
            "limit": limit,
        }

    def fork_conversation(self, message_id):
        session = get_session()
        user_id = self._user_id

        # Get the original conversation
        original_conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not original_conversation:
            session.close()
            return None

        # Get the target message first to get its timestamp
        target_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == original_conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not target_message:
            session.close()
            return None

        # Get all messages up to and including the specified message using timestamp
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == original_conversation.id,
                Message.timestamp <= target_message.timestamp,
            )
            .order_by(Message.timestamp.asc())
            .all()
        )

        if not messages:
            session.close()
            return None

        try:
            # Create a new conversation
            new_conversation_name = f"{self.conversation_name}_fork_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            new_conversation = Conversation(name=new_conversation_name, user_id=user_id)
            session.add(new_conversation)
            session.flush()  # This will assign an id to new_conversation

            # Copy messages to the new conversation
            for message in messages:
                new_message = Message(
                    role=message.role,
                    content=message.content,
                    conversation_id=new_conversation.id,
                    timestamp=message.timestamp,
                    updated_at=message.updated_at,
                    updated_by=message.updated_by,
                    feedback_received=message.feedback_received,
                    notify=False,
                )
                session.add(new_message)

            # Set notify on the last message
            if messages:
                messages[-1].notify = True

            session.commit()
            forked_conversation_id = str(new_conversation.id)

            return new_conversation_name

        except Exception as e:
            logging.error(f"Error forking conversation: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def get_activities(self, limit=100, page=1):
        session = get_session()
        user_id = self._user_id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return {"activities": []}
        offset = (page - 1) * limit
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content.like("[ACTIVITY]%"),
            )
            .order_by(Message.timestamp.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        if not messages:
            session.close()
            return {"activities": []}
        return_activities = [
            {
                "id": message.id,
                "role": message.role,
                "message": message.content,
                "timestamp": message.timestamp,
            }
            for message in messages
        ]
        session.close()
        return {"activities": return_activities}

    def get_subactivities(self, activity_id):
        session = get_session()
        user_id = self._user_id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return ""
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content.like(f"[SUBACTIVITY][{activity_id}]%"),
            )
            .order_by(Message.timestamp.asc())
            .all()
        )
        if not messages:
            session.close()
            return ""
        return_subactivities = [
            {
                "id": message.id,
                "role": message.role,
                "message": message.content,
                "timestamp": message.timestamp,
            }
            for message in messages
        ]
        session.close()
        # Return it as a string with timestamps per subactivity in markdown format
        subactivities = "\n".join(
            [
                f"#### Activity at {subactivity['timestamp']}\n{subactivity['message']}"
                for subactivity in return_subactivities
            ]
        )
        return f"### Detailed Activities:\n{subactivities}"

    def get_activities_with_subactivities(
        self,
        max_activities: int = 5,
        max_subactivities_per_activity: int = 3,
        summarize: bool = True,
    ):
        """
        Get recent activities with their subactivities, with context compression.

        Args:
            max_activities: Maximum number of activities to return (most recent)
            max_subactivities_per_activity: Max subactivities per activity
            summarize: If True, compress long subactivity content
        """
        session = get_session()
        user_id = self._user_id
        if not self.conversation_name:
            self.conversation_name = "-"
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return ""
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                or_(
                    Message.content.like("[ACTIVITY]%"),
                    Message.content.like("[SUBACTIVITY]%"),
                ),
            )
            .order_by(Message.timestamp.asc())
            .all()
        )
        if not messages:
            session.close()
            return ""
        return_activities = []
        current_activity = None
        for message in messages:
            if message.content.startswith("[ACTIVITY]"):
                if current_activity:
                    return_activities.append(current_activity)
                current_activity = {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                    "subactivities": [],
                }
            elif message.content.startswith("[SUBACTIVITY]"):
                if current_activity:
                    if "subactivities" not in current_activity:
                        current_activity["subactivities"] = []
                    current_activity["subactivities"].append(
                        {
                            "id": message.id,
                            "role": message.role,
                            "message": message.content,
                            "timestamp": message.timestamp,
                        }
                    )
        if current_activity:
            return_activities.append(current_activity)
        session.close()

        # Only keep the most recent activities
        if len(return_activities) > max_activities:
            skipped_count = len(return_activities) - max_activities
            return_activities = return_activities[-max_activities:]
        else:
            skipped_count = 0

        def summarize_content(content: str, max_chars: int = 200) -> str:
            """Summarize long content for context compression."""
            if not summarize or len(content) <= max_chars:
                return content

            # Check if this is discarded content - display nicely
            if "[DISCARDED:" in content:
                # Format: [ACTIVITY] [DISCARDED:id] reason or [SUBACTIVITY][parent_id][TYPE] [DISCARDED:id] reason
                return content  # Keep as-is, it's already summarized

            # For execution outputs, keep first and last parts
            if "[EXECUTION]" in content or "Output:" in content:
                lines = content.split("\n")
                if len(lines) > 6:
                    # Keep first 3 and last 2 lines
                    return (
                        "\n".join(lines[:3])
                        + f"\n... [{len(lines) - 5} lines omitted] ...\n"
                        + "\n".join(lines[-2:])
                    )

            # For other content, truncate with indicator
            truncated = content[:max_chars]
            last_space = truncated.rfind(" ")
            if last_space > max_chars * 0.7:
                truncated = truncated[:last_space]
            return truncated + "..."

        # Return in markdown with compression
        activities_md = []
        for activity in return_activities:
            activity_msg = summarize_content(activity["message"], max_chars=300)
            subactivities = activity.get("subactivities", [])

            # Limit subactivities
            if len(subactivities) > max_subactivities_per_activity:
                skipped_subs = len(subactivities) - max_subactivities_per_activity
                # Keep first and last subactivities
                kept_subs = subactivities[: max_subactivities_per_activity - 1] + [
                    subactivities[-1]
                ]
                sub_text = "\n".join(
                    [
                        f"- {summarize_content(sub['message'], max_chars=150)}"
                        for sub in kept_subs
                    ]
                )
                sub_text += f"\n  *({skipped_subs} additional subactivities omitted)*"
            else:
                sub_text = "\n".join(
                    [
                        f"- {summarize_content(sub['message'], max_chars=150)}"
                        for sub in subactivities
                    ]
                )

            activities_md.append(
                f"**{activity_msg}**\n{sub_text}" if sub_text else f"**{activity_msg}**"
            )

        activities = "\n\n".join(activities_md)

        header = "### Recent Activities"
        if skipped_count > 0:
            header += (
                f" (showing last {max_activities} of {skipped_count + max_activities})"
            )
        header += ":\n"

        return f"{header}{activities}"

    def new_conversation(self, conversation_content=[]):
        session = get_session()
        user_id = self._user_id

        # Create a new conversation
        conversation = Conversation(name=self.conversation_name, user_id=user_id)
        session.add(conversation)
        session.commit()
        conversation_id = conversation.id

        if conversation_content:
            # Sort by timestamp to ensure chronological order
            try:
                from dateutil import parser

                # Try to sort by timestamp if available
                conversation_content = sorted(
                    conversation_content,
                    key=lambda x: (
                        parser.parse(x.get("timestamp", ""))
                        if x.get("timestamp")
                        else parser.parse("2099-01-01")
                    ),
                )
            except Exception as e:
                logging.warning(f"Could not sort by timestamp: {e}")

            # Find agent name from the first non-user message or use default
            agent_name = "XT"  # Default agent name
            for msg in conversation_content:
                if msg.get("role", "").upper() != "USER":
                    agent_name = msg.get("role")
                    break

            # Find the earliest timestamp in the conversation
            earliest_timestamp = None
            try:
                for msg in conversation_content:
                    if msg.get("timestamp"):
                        timestamp = parser.parse(msg.get("timestamp"))
                        if earliest_timestamp is None or timestamp < earliest_timestamp:
                            earliest_timestamp = timestamp

                # If we found timestamps, make the completed activity slightly earlier
                if earliest_timestamp:
                    import datetime

                    # Make it 1 second earlier than the earliest message
                    completed_activity_timestamp = (
                        earliest_timestamp - datetime.timedelta(seconds=1)
                    ).isoformat()
                else:
                    completed_activity_timestamp = None
            except:
                completed_activity_timestamp = None

            # Check if there are any subactivities and if there's already a Completed activities message
            has_subactivities = any(
                msg.get("message", "").startswith("[SUBACTIVITY]")
                for msg in conversation_content
            )

            # Check if a "Completed activities" message already exists in the import
            has_completed_activities = any(
                msg.get("message", "") == "[ACTIVITY] Completed activities."
                for msg in conversation_content
            )

            completed_activity_id = None

            # Create the "Completed activities" message only if needed and not already present
            if has_subactivities and not has_completed_activities:
                completed_activity_id = self.log_interaction(
                    role=agent_name,
                    message="[ACTIVITY] Completed activities.",
                    timestamp=completed_activity_timestamp,
                )

            # Process regular messages
            for interaction in conversation_content:
                message = interaction.get("message", "")

                # Skip subactivities for now
                if message.startswith("[SUBACTIVITY]"):
                    continue

                # If this is a "Completed activities" message from the import, save its ID
                if (
                    message == "[ACTIVITY] Completed activities."
                    and not completed_activity_id
                ):
                    message_id = self.log_interaction(
                        role=interaction["role"],
                        message=message,
                        timestamp=interaction.get("timestamp"),
                    )
                    completed_activity_id = message_id
                elif message != "[ACTIVITY] Completed activities.":
                    # Normal message processing - skip if it's a Completed activities we already have
                    self.log_interaction(
                        role=interaction["role"],
                        message=message,
                        timestamp=interaction.get("timestamp"),
                    )

            # Now process subactivities, attaching to completed_activity_id
            if completed_activity_id:
                for interaction in conversation_content:
                    message = interaction.get("message", "")

                    if message.startswith("[SUBACTIVITY]"):
                        # Extract the content part after the subactivity ID
                        try:
                            # Find where the message type starts (after the second ])
                            parts = message.split("]", 2)
                            if len(parts) >= 3:
                                # Format: [SUBACTIVITY][id][TYPE] content
                                message_type_and_content = parts[2]
                                new_message = f"[SUBACTIVITY][{completed_activity_id}][{message_type_and_content}"
                            else:
                                # Fallback if format is different
                                new_message = f"[SUBACTIVITY][{completed_activity_id}] {message.split(']', 2)[-1]}"

                            self.log_interaction(
                                role=interaction["role"],
                                message=new_message,
                                timestamp=interaction.get("timestamp"),
                            )
                        except Exception as e:
                            logging.error(f"Error processing subactivity: {e}")
                            # If parsing fails, try a simpler approach
                            self.log_interaction(
                                role=interaction["role"],
                                message=f"[SUBACTIVITY][{completed_activity_id}] {message.replace('[SUBACTIVITY]', '').lstrip()}",
                                timestamp=interaction.get("timestamp"),
                            )
            response = conversation.__dict__
            response = {
                key: value for key, value in response.items() if not key.startswith("_")
            }
            if "id" not in response:
                response["id"] = conversation_id
            session.close()
            return response

    def get_thinking_id(self, agent_name):
        import traceback

        session = get_session()
        user_id = self._user_id

        # Use get_conversation_id() to get the stable conversation ID
        # This prevents issues during conversation renames
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            session.close()
            return None

        # Get the most recent thinking activity
        # Use conversation_id directly instead of querying Conversation table first
        current_thinking = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.content == "[ACTIVITY] Thinking.",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        # Get the most recent non-subactivity message (user message, agent response, or non-thinking activity)
        # This represents the last "real" conversation turn
        most_recent_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                ~Message.content.like("[SUBACTIVITY]%"),
                Message.content != "[ACTIVITY] Thinking.",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        # If there's a recent message and it's more recent than the last thinking activity,
        # create a new thinking activity for this new conversation turn
        if most_recent_message:
            if (
                not current_thinking
                or most_recent_message.timestamp > current_thinking.timestamp
            ):
                # Create new thinking activity as we have a new conversation turn
                thinking_id = self.log_interaction(
                    role=agent_name,
                    message="[ACTIVITY] Thinking.",
                )
                session.close()
                return str(thinking_id)

        # If we have a current thinking activity and it's the most recent message,
        # or if there's no other messages at all, reuse the existing thinking ID
        if current_thinking:
            if (
                not most_recent_message
                or current_thinking.timestamp > most_recent_message.timestamp
            ):
                session.close()
                return str(current_thinking.id)

        # If we have no thinking activity at all, create one
        thinking_id = self.log_interaction(
            role=agent_name,
            message="[ACTIVITY] Thinking.",
        )
        session.close()
        return str(thinking_id)

    def log_interaction(self, role, message, timestamp=None, sender_user_id=None):
        message = str(message)
        # Cache conversation_id once at the top (avoids repeated session opens)
        conversation_id = self.get_conversation_id()

        if str(message).startswith("[SUBACTIVITY] "):
            try:
                last_activity_id = self.get_last_activity_id()
            except:
                last_activity_id = self.get_thinking_id(role)
            if last_activity_id:
                message = message.replace(
                    "[SUBACTIVITY] ", f"[SUBACTIVITY][{last_activity_id}] "
                )
            else:
                message = message.replace("[SUBACTIVITY] ", "[ACTIVITY] ")

        # Extract base64 data URLs from message and save to workspace
        # This prevents massive base64 strings from bloating the DB and DOM
        if "data:" in message and "base64," in message:
            try:
                # Cache agent_id per instance to avoid repeated DB lookups
                if not hasattr(self, "_cached_agent_id"):
                    self._cached_agent_id = (
                        self.get_agent_id(self._user_id) or "default"
                    )
                message = extract_data_urls_to_workspace(
                    message, self._cached_agent_id, conversation_id
                )
            except Exception as e:
                logging.warning(f"Failed to extract data URLs from message: {e}")

        session = get_session()
        user_id = self._user_id
        # Look up by ID instead of name to handle renames during a request
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )
        # Fallback: check group/dm/thread conversations accessible via company membership
        # This is needed for DM conversations where the non-creator user sends a message
        # (DM user_id is set to the creator, not the other participant)
        if not conversation:
            # Cache company_ids per instance to avoid repeated queries during multi-message logging
            company_ids = _get_user_company_ids(user_id)
            if company_ids:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.id == conversation_id,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                    .first()
                )
        notify = False
        if role.lower() == "user":
            role = "USER"
        else:
            if not message.startswith("[ACTIVITY]") and not message.startswith(
                "[SUBACTIVITY]"
            ):
                notify = True
        if not conversation:
            conversation = self.new_conversation()
            session.close()
            session = get_session()
            # Get the new conversation_id after creating
            conversation_id = self.get_conversation_id()
        else:
            conversation = conversation.__dict__
            conversation = {
                key: value
                for key, value in conversation.items()
                if not key.startswith("_")
            }
        if message.endswith("\n"):
            message = message[:-1]
        if message.endswith("\n"):
            message = message[:-1]
        try:
            # For USER messages, auto-set sender_user_id to conversation owner if not provided
            effective_sender_user_id = sender_user_id
            if role == "USER" and not effective_sender_user_id:
                effective_sender_user_id = user_id
            new_message = Message(
                role=role,
                content=message,
                conversation_id=conversation_id,
                notify=notify,
                sender_user_id=effective_sender_user_id,
            )
            # Use the provided timestamp if one is given
            if timestamp:
                try:
                    # Try to parse the timestamp - it might be in various formats
                    from dateutil import parser

                    parsed_time = parser.parse(timestamp)
                    new_message.timestamp = parsed_time
                    new_message.updated_at = parsed_time
                except:
                    # If parsing fails, just log it and continue with auto timestamps
                    logging.warning(f"Could not parse timestamp: {timestamp}")

        except Exception as e:
            conversation = self.new_conversation()
            session.close()
            session = get_session()
            new_message = Message(
                role=role,
                content=message,
                conversation_id=conversation_id,
                notify=notify,
                sender_user_id=(
                    effective_sender_user_id
                    if "effective_sender_user_id" in dir()
                    else sender_user_id
                ),
            )

        session.add(new_message)
        session.commit()

        message_id = str(new_message.id)

        # Notify WebSocket listeners about the new message
        # The WebSocket endpoint polling will pick this up on the next check,
        # but for USER messages we can also trigger an immediate notification
        # to improve responsiveness
        # Note: The actual WebSocket sending happens in the WebSocket endpoint's polling loop

        session.close()
        return message_id

    def delete_conversation(self):
        session = get_session()
        user_id = self._user_id
        if not self.conversation_name:
            self.conversation_name = "-"
        # First try: find by conversation_id if available (most reliable)
        conversation = None
        if self.conversation_id:
            conversation = (
                session.query(Conversation)
                .filter(Conversation.id == self.conversation_id)
                .first()
            )
            # Verify the user has access to this conversation
            if conversation and conversation.user_id != user_id:
                # Check if user is in the same company for group/thread/channel/dm
                if conversation.company_id:
                    has_access = (
                        session.query(UserCompany)
                        .filter(
                            UserCompany.user_id == user_id,
                            UserCompany.company_id == conversation.company_id,
                        )
                        .first()
                    )
                    if not has_access:
                        conversation = None
                else:
                    # Check if user is a participant
                    is_participant = (
                        session.query(ConversationParticipant)
                        .filter(
                            ConversationParticipant.conversation_id
                            == self.conversation_id,
                            ConversationParticipant.user_id == user_id,
                            ConversationParticipant.participant_type == "user",
                            ConversationParticipant.status == "active",
                        )
                        .first()
                    )
                    if not is_participant:
                        conversation = None
        # Fallback: find by name + user_id (legacy personal conversations)
        if not conversation:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )
        if not conversation:
            session.close()
            return

        try:
            conv_id = conversation.id
            # Delete all FK-dependent records before deleting the conversation
            # 1. DiscardedContext (references conversation_id and message_id)
            session.query(DiscardedContext).filter(
                DiscardedContext.conversation_id == conv_id
            ).delete()
            # 2. Memory (references conversation_id)
            session.query(Memory).filter(Memory.conversation_id == conv_id).delete()
            # 3. MessageReaction (references message_id)
            message_ids = [
                m.id
                for m in session.query(Message.id)
                .filter(Message.conversation_id == conv_id)
                .all()
            ]
            if message_ids:
                session.query(MessageReaction).filter(
                    MessageReaction.message_id.in_(message_ids)
                ).delete(synchronize_session="fetch")
            # 4. Messages
            session.query(Message).filter(Message.conversation_id == conv_id).delete()
            # 5. ConversationParticipant (references conversation_id)
            session.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conv_id
            ).delete()
            # 6. ConversationShare (references source or shared conversation_id)
            session.query(ConversationShare).filter(
                (ConversationShare.source_conversation_id == conv_id)
                | (ConversationShare.shared_conversation_id == conv_id)
            ).delete(synchronize_session="fetch")
            # 7. Child conversations (parent_id references this conversation)
            child_conv_ids = [
                row[0]
                for row in session.query(Conversation.id)
                .filter(Conversation.parent_id == conv_id)
                .all()
            ]
            if child_conv_ids:
                # Batch clean up all child conversations at once
                session.query(DiscardedContext).filter(
                    DiscardedContext.conversation_id.in_(child_conv_ids)
                ).delete(synchronize_session="fetch")
                session.query(Memory).filter(
                    Memory.conversation_id.in_(child_conv_ids)
                ).delete(synchronize_session="fetch")
                child_message_ids = [
                    row[0]
                    for row in session.query(Message.id)
                    .filter(Message.conversation_id.in_(child_conv_ids))
                    .all()
                ]
                if child_message_ids:
                    session.query(MessageReaction).filter(
                        MessageReaction.message_id.in_(child_message_ids)
                    ).delete(synchronize_session="fetch")
                session.query(Message).filter(
                    Message.conversation_id.in_(child_conv_ids)
                ).delete(synchronize_session="fetch")
                session.query(ConversationParticipant).filter(
                    ConversationParticipant.conversation_id.in_(child_conv_ids)
                ).delete(synchronize_session="fetch")
                session.query(ConversationShare).filter(
                    (ConversationShare.source_conversation_id.in_(child_conv_ids))
                    | (ConversationShare.shared_conversation_id.in_(child_conv_ids))
                ).delete(synchronize_session="fetch")
                session.query(Conversation).filter(
                    Conversation.id.in_(child_conv_ids)
                ).delete(synchronize_session="fetch")
            # 8. Finally delete the conversation itself
            session.query(Conversation).filter(Conversation.id == conv_id).delete()
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting conversation: {e}")
            raise
        finally:
            session.close()
        # Invalidate cache for this conversation
        invalidate_conversation_cache(
            user_id=str(user_id), conversation_name=self.conversation_name
        )

    def delete_message(self, message):
        session = get_session()
        user_id = self._user_id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            session.close()
            return
        msg = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        )

        if not msg:
            session.close()
            return
        session.delete(msg)
        session.commit()
        session.close()

    def get_message_by_id(self, message_id):
        session = get_session()
        user_id = self._user_id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            session.close()
            return
        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            session.close()
            return
        session.close()
        return message.content

    def get_last_agent_name(self):
        # Get the last role in the conversation that isn't "user"
        session = get_session()
        try:
            # Use cached conversation_id (avoids name-based Conversation query)
            conversation_id = self.get_conversation_id()
            if not conversation_id:
                return "AGiXT"
            message = (
                session.query(Message.role)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.role != "USER",
                    Message.role != "user",
                )
                .order_by(Message.timestamp.desc())
                .first()
            )
            return message[0] if message else "AGiXT"
        finally:
            session.close()

    def delete_message_by_id(self, message_id):
        session = get_session()
        user_id = self._user_id

        conversation = None

        # Prefer conversation_id lookup (fast, unambiguous) over name-based lookup
        if self.conversation_id:
            company_ids = _get_user_company_ids(user_id)

            participant_conv_ids = session.query(
                ConversationParticipant.conversation_id
            ).filter(
                ConversationParticipant.conversation_id == self.conversation_id,
                ConversationParticipant.user_id == user_id,
                ConversationParticipant.participant_type == "user",
                ConversationParticipant.status == "active",
            )

            access_filters = [
                and_(
                    Conversation.id == self.conversation_id,
                    Conversation.user_id == user_id,
                ),
            ]
            if company_ids:
                access_filters.append(
                    and_(
                        Conversation.id == self.conversation_id,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                )
            access_filters.append(
                and_(
                    Conversation.id == self.conversation_id,
                    Conversation.id.in_(participant_conv_ids),
                )
            )

            conversation = (
                session.query(Conversation).filter(or_(*access_filters)).first()
            )
        else:
            # Fallback: name-based lookup for legacy /api/ endpoint
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not conversation:
                # Fallback: check group conversations accessible via company membership
                company_ids = _get_user_company_ids(user_id)
                if company_ids:
                    conversation = (
                        session.query(Conversation)
                        .filter(
                            Conversation.name == self.conversation_name,
                            Conversation.company_id.in_(company_ids),
                            Conversation.conversation_type.in_(
                                ["group", "dm", "thread", "channel"]
                            ),
                        )
                        .first()
                    )

            if not conversation:
                # Fallback: check conversations where user is a participant
                participant_conv = (
                    session.query(ConversationParticipant)
                    .filter(
                        ConversationParticipant.user_id == user_id,
                        ConversationParticipant.participant_type == "user",
                        ConversationParticipant.status == "active",
                    )
                    .all()
                )
                if participant_conv:
                    participant_conv_ids = [
                        str(p.conversation_id) for p in participant_conv
                    ]
                    conversation = (
                        session.query(Conversation)
                        .filter(
                            Conversation.name == self.conversation_name,
                            Conversation.id.in_(participant_conv_ids),
                        )
                        .first()
                    )

        if not conversation:
            session.close()
            return
        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            session.close()
            return
        session.delete(message)
        session.commit()
        session.close()

    def delete_messages_after(self, message_id):
        """
        Delete all messages after a specific message ID (including that message).
        This is used when regenerating responses from an edited user message.
        """
        session = get_session()
        user_id = self._user_id

        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if not conversation:
            # Fallback: check group conversations accessible via company membership
            company_ids = _get_user_company_ids(user_id)
            if company_ids:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.name == self.conversation_name,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                    .first()
                )

        if not conversation:
            session.close()
            return

        # Find the target message to get its timestamp
        target_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not target_message:
            session.close()
            return

        target_timestamp = target_message.timestamp
        target_message_id = target_message.id

        # Check if there's an activity message immediately before the target that should also be deleted
        # Find messages with timestamp < target_timestamp, ordered by timestamp descending
        activity_messages_to_delete = []
        previous_messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.timestamp < target_timestamp,
            )
            .order_by(Message.timestamp.desc())
            .limit(5)  # Check last 5 messages before target
            .all()
        )

        for prev_msg in previous_messages:
            msg_content = prev_msg.content or ""
            # Check if this is an activity or subactivity message
            if msg_content.startswith("[ACTIVITY]") or msg_content.startswith(
                "[SUBACTIVITY]"
            ):
                # Check if this activity message has no other children after it besides our target
                # (meaning the target is the only thing this activity was doing)
                messages_between = (
                    session.query(Message)
                    .filter(
                        Message.conversation_id == conversation.id,
                        Message.timestamp > prev_msg.timestamp,
                        Message.timestamp < target_timestamp,
                    )
                    .count()
                )

                if messages_between == 0:
                    # This activity message has no children except the target, so delete it too
                    activity_messages_to_delete.append(prev_msg)
                    break  # Only delete the immediate parent activity

        # Verify the target message still exists before trying to delete
        verification_check = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )
        if not verification_check:
            logging.warning(f"Target message {message_id} was already deleted!")

        # Get all messages that will be deleted for logging
        messages_to_delete = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.timestamp >= target_timestamp,
            )
            .all()
        )

        # Delete all messages with timestamp >= target message timestamp OR the target message itself by ID
        # Also delete any parent activity messages we identified
        # Using OR condition to ensure target message is included even if timestamp comparison fails
        activity_ids = [msg.id for msg in activity_messages_to_delete]

        # Get all message IDs that will be deleted BEFORE deleting them
        messages_query = session.query(Message).filter(
            Message.conversation_id == conversation.id,
            or_(
                Message.timestamp >= target_timestamp,
                Message.id == message_id,
                Message.id.in_(activity_ids) if activity_ids else False,
            ),
        )
        deleted_message_ids = [str(msg.id) for msg in messages_query.all()]

        deleted_count = messages_query.delete(synchronize_session=False)

        session.commit()
        session.close()
        return {
            "deleted_count": deleted_count,
            "deleted_message_ids": deleted_message_ids,
        }

    def toggle_feedback_received(self, message):
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            if not conversation_id:
                return
            msg = (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.content == message,
                )
                .first()
            )
            if not msg:
                return
            msg.feedback_received = not msg.feedback_received
            session.commit()
        finally:
            session.close()

    def has_received_feedback(self, message):
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            if not conversation_id:
                return
            msg = (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.content == message,
                )
                .first()
            )
            if not msg:
                return
            return msg.feedback_received
        finally:
            session.close()

    def update_message(self, message, new_message):
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            if not conversation_id:
                return
            msg = (
                session.query(Message)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.content == message,
                )
                .first()
            )
            if not msg:
                return
            msg.content = new_message
            session.commit()
        finally:
            session.close()

    def update_message_by_id(self, message_id, new_message):
        session = get_session()
        user_id = self._user_id
        conversation = None

        # If we already have a conversation_id, use it directly (most reliable)
        if self.conversation_id:
            conversation = (
                session.query(Conversation)
                .filter(Conversation.id == self.conversation_id)
                .first()
            )

        # Fallback 1: lookup by name + user ownership
        if not conversation:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )

        # Fallback 2: group conversations accessible via company membership
        if not conversation:
            company_ids = _get_user_company_ids(user_id)
            if company_ids:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.name == self.conversation_name,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                    .first()
                )

        # Fallback 3: conversations where user is a participant (handles DMs without company_id)
        if not conversation:
            participant_conv = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.participant_type == "user",
                    ConversationParticipant.status == "active",
                )
                .first()
            )
            if participant_conv:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.id == participant_conv.conversation_id,
                        Conversation.name == self.conversation_name,
                    )
                    .first()
                )

        if not conversation:
            logging.warning(
                f"update_message_by_id: conversation not found for name={self.conversation_name}, id={self.conversation_id}, user={user_id}"
            )
            session.close()
            return

        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )

        if not message:
            logging.warning(
                f"update_message_by_id: message {message_id} not found in conversation {conversation.id}"
            )
            session.close()
            return

        # Update the message content and metadata
        message.content = str(new_message)  # Ensure the content is a string
        message.updated_by = user_id  # Track who updated the message
        message.updated_at = datetime.now()  # Explicitly set the update timestamp

        try:
            session.commit()
            logging.debug(
                f"Message {message_id} successfully updated - committed to database"
            )
        except Exception as e:
            logging.error(f"Error updating message: {e}")
            session.rollback()
        finally:
            session.close()

    def toggle_pin_message(self, message_id):
        """Toggle the pinned state of a message."""
        session = get_session()
        user_id = self._user_id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            company_ids = _get_user_company_ids(user_id)
            if company_ids:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.name == self.conversation_name,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                    .first()
                )
        if not conversation:
            session.close()
            return {"pinned": False}
        message = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.id == message_id,
            )
            .first()
        )
        if not message:
            session.close()
            return {"pinned": False}
        current_pinned = bool(message.pinned)
        new_pinned = not current_pinned
        now = datetime.now()
        try:
            # Use explicit SQL UPDATE to ensure persistence
            from sqlalchemy import update

            stmt = (
                update(Message)
                .where(Message.id == message_id)
                .values(
                    pinned=new_pinned,
                    pinned_at=now if new_pinned else None,
                    pinned_by=user_id if new_pinned else None,
                )
            )
            session.execute(stmt)
            session.flush()
            session.commit()
            logging.info(
                f"Pin toggled for message {message_id}: {current_pinned} -> {new_pinned}"
            )
            return {"pinned": new_pinned, "message_id": str(message_id)}
        except Exception as e:
            logging.error(f"Error toggling pin: {e}")
            session.rollback()
            return {"pinned": False}
        finally:
            session.close()

    def get_pinned_messages(self):
        """Get all pinned messages in this conversation."""
        session = get_session()
        user_id = self._user_id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == self.conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            company_ids = _get_user_company_ids(user_id)
            if company_ids:
                conversation = (
                    session.query(Conversation)
                    .filter(
                        Conversation.name == self.conversation_name,
                        Conversation.company_id.in_(company_ids),
                        Conversation.conversation_type.in_(
                            ["group", "dm", "thread", "channel"]
                        ),
                    )
                    .first()
                )
        if not conversation:
            session.close()
            return []
        conv_id = str(conversation.id)
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == conv_id,
                Message.pinned == True,
            )
            .order_by(Message.pinned_at.desc())
            .all()
        )
        # Batch-fetch all sender users at once instead of N+1 individual queries
        sender_ids = list(
            {str(msg.sender_user_id) for msg in messages if msg.sender_user_id}
        )
        senders_by_id = {}
        if sender_ids:
            users = session.query(User).filter(User.id.in_(sender_ids)).all()
            senders_by_id = {
                str(u.id): {
                    "id": str(u.id),
                    "email": u.email,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                }
                for u in users
            }
        result = []
        for msg in messages:
            sender = (
                senders_by_id.get(str(msg.sender_user_id))
                if msg.sender_user_id
                else None
            )
            result.append(
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "message": str(msg.content),
                    "timestamp": str(msg.timestamp),
                    "pinned_at": str(msg.pinned_at) if msg.pinned_at else None,
                    "pinned_by": str(msg.pinned_by) if msg.pinned_by else None,
                    "sender": sender,
                }
            )
        session.close()
        return result

    def get_conversation_id(self):
        # Return cached ID if available - this is stable even if name changes
        if self.conversation_id:
            return str(self.conversation_id)

        if not self.conversation_name:
            conversation_name = "-"
        else:
            conversation_name = self.conversation_name

        # Delegate to the cached module-level function
        conversation_id = get_conversation_id_by_name(
            conversation_name=conversation_name,
            user_id=self._user_id,
            create_if_missing=True,
        )
        # Cache the ID on the instance for future calls
        self.conversation_id = conversation_id
        return conversation_id

    def rename_conversation(self, new_name: str):
        session = get_session()
        user_id = self._user_id
        # Use conversation_id for lookup if available - more stable than name
        conversation_id = self.get_conversation_id()
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            # Fallback to name-based lookup for backwards compatibility
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )
        if not conversation:
            conversation = Conversation(name=self.conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        conversation.name = new_name
        # Also update internal state so future lookups use the new name
        old_name = self.conversation_name
        self.conversation_name = new_name
        session.commit()
        session.close()
        # Invalidate cache for both old and new names
        invalidate_conversation_cache(user_id=str(user_id), conversation_name=old_name)
        invalidate_conversation_cache(user_id=str(user_id), conversation_name=new_name)
        return new_name

    def update_pin_order(self, conversation_id: str, pin_order: int = None):
        """
        Update the pin order for a conversation.
        pin_order=None means unpinned, integer means pinned at that position.
        Lower numbers appear first in the pinned list.
        """
        session = get_session()
        user_id = self._user_id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            session.close()
            return False
        conversation.pin_order = pin_order
        session.commit()
        session.close()
        return True

    def get_last_activity_id(self):
        session = get_session()
        try:
            # Use cached conversation_id (avoids name-based Conversation query)
            conversation_id = self.get_conversation_id()
            if not conversation_id:
                return None
            last_activity = (
                session.query(Message.id)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.content.like("[ACTIVITY]%"),
                )
                .order_by(Message.timestamp.desc())
                .first()
            )
            return str(last_activity[0]) if last_activity else None
        finally:
            session.close()

    def set_conversation_summary(self, summary: str):
        session = get_session()
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            session.close()
            return ""
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            session.close()
            return ""
        conversation.summary = summary
        session.commit()
        session.close()
        return summary

    def get_conversation_summary(self):
        session = get_session()
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            session.close()
            return ""
        result = (
            session.query(Conversation.summary)
            .filter(Conversation.id == conversation_id)
            .scalar()
        )
        session.close()
        return result or ""

    def get_attachment_count(self):
        session = get_session()
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            session.close()
            return 0
        result = (
            session.query(Conversation.attachment_count)
            .filter(Conversation.id == conversation_id)
            .scalar()
        )
        session.close()
        return result or 0

    def update_attachment_count(self, count: int):
        session = get_session()
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            session.close()
            return 0
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            session.close()
            return 0
        conversation.attachment_count = count
        session.commit()
        session.close()
        return count

    def increment_attachment_count(self):
        session = get_session()
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            session.close()
            return 0
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            session.close()
            return 0
        conversation.attachment_count += 1
        session.commit()
        session.close()
        return conversation.attachment_count

    def share_conversation(
        self,
        share_type="public",
        target_user_email=None,
        include_workspace=True,
        expires_at=None,
    ):
        """
        Share a conversation by creating a fork and generating a share token.

        Args:
            share_type: 'public' or 'email'
            target_user_email: Email of user to share with (required if share_type='email')
            include_workspace: Whether to copy workspace files
            expires_at: ISO datetime string when share expires (None for no expiration)

        Returns:
            dict: Share information including token and URL
        """
        session = get_session()
        try:
            # Use cached user_id
            user_id = self._user_id
            if not user_id:
                raise ValueError("User not found")

            # Get source conversation
            source_conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == self.conversation_name,
                    Conversation.user_id == user_id,
                )
                .first()
            )

            if not source_conversation:
                raise ValueError("Conversation not found")

            # Determine target user
            if share_type == "email":
                if not target_user_email:
                    raise ValueError("target_user_email required for email shares")
                target_user = (
                    session.query(User).filter(User.email == target_user_email).first()
                )
                if not target_user:
                    raise ValueError(f"User {target_user_email} not found")
                target_user_id = target_user.id
                shared_with_user_id = target_user_id
            else:  # public
                # Use DEFAULT_USER for public shares
                default_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if not default_user:
                    raise ValueError("Default user not found")
                target_user_id = default_user.id
                shared_with_user_id = None

            # Fork the conversation to the target user
            # Get all messages from source conversation
            messages = (
                session.query(Message)
                .filter(Message.conversation_id == source_conversation.id)
                .order_by(Message.timestamp.asc())
                .all()
            )

            # Create new conversation for the share
            shared_conversation_name = f"Shared: {self.conversation_name}"
            shared_conversation = Conversation(
                name=shared_conversation_name,
                user_id=target_user_id,
                summary=source_conversation.summary,
            )
            session.add(shared_conversation)
            session.flush()

            # Copy all messages
            for message in messages:
                new_message = Message(
                    role=message.role,
                    content=message.content,
                    conversation_id=shared_conversation.id,
                    timestamp=message.timestamp,
                    updated_at=message.updated_at,
                    updated_by=message.updated_by,
                    feedback_received=message.feedback_received,
                    notify=False,
                )
                session.add(new_message)

            # Generate unique share token
            share_token = secrets.token_urlsafe(32)

            # Parse expiration datetime if specified
            expires_at_datetime = None
            if expires_at:
                try:
                    from dateutil import parser

                    expires_at_datetime = parser.parse(expires_at)
                except Exception as e:
                    logging.warning(f"Could not parse expires_at datetime: {e}")

            # Create ConversationShare record
            conversation_share = ConversationShare(
                source_conversation_id=source_conversation.id,
                shared_conversation_id=shared_conversation.id,
                share_type=share_type,
                share_token=share_token,
                shared_by_user_id=user_id,
                shared_with_user_id=shared_with_user_id,
                include_workspace=include_workspace,
                expires_at=expires_at_datetime,
            )
            session.add(conversation_share)
            session.commit()

            # Copy workspace files if requested
            if include_workspace:
                try:
                    from Workspaces import WorkspaceManager

                    workspace_manager = WorkspaceManager()

                    # Get source agent ID from the conversation's messages
                    source_agent_name = (
                        session.query(Message)
                        .filter(
                            Message.conversation_id == source_conversation.id,
                            Message.role != "USER",
                            Message.role != "user",
                        )
                        .order_by(Message.timestamp.desc())
                        .first()
                    )

                    if source_agent_name:
                        source_agent_name = source_agent_name.role

                        # Get agent IDs
                        source_agent = (
                            session.query(Agent)
                            .filter(
                                Agent.name == source_agent_name,
                                Agent.user_id == user_id,
                            )
                            .first()
                        )
                        # For target, use the same agent name but with target user
                        target_agent = (
                            session.query(Agent)
                            .filter(
                                Agent.name == source_agent_name,
                                Agent.user_id == target_user_id,
                            )
                            .first()
                        )

                        # If target agent doesn't exist for DEFAULT_USER, create it
                        if not target_agent and share_type == "public":
                            target_agent = Agent(
                                name=source_agent_name,
                                user_id=target_user_id,
                                settings=source_agent.settings if source_agent else {},
                            )
                            session.add(target_agent)
                            session.commit()  # Commit agent before workspace copy

                        if source_agent and target_agent:
                            files_copied = (
                                workspace_manager.copy_conversation_workspace(
                                    source_agent_id=str(source_agent.id),
                                    source_conversation_id=str(source_conversation.id),
                                    target_agent_id=str(target_agent.id),
                                    target_conversation_id=str(shared_conversation.id),
                                )
                            )
                        else:
                            logging.warning(
                                f"❌ Could not copy workspace files: source_agent={bool(source_agent)}, target_agent={bool(target_agent)}"
                            )
                    else:
                        logging.warning(
                            "❌ Could not find agent name from conversation messages"
                        )
                except Exception as e:
                    logging.error(f"Error copying workspace files: {e}")
                    import traceback

                    logging.error(traceback.format_exc())
                    # Don't fail the share if workspace copy fails

            # Build share URL - use APP_URI for frontend URL
            app_uri = getenv("APP_URI", "http://localhost:3000")
            share_url = f"{app_uri}/shared/{share_token}"

            return {
                "share_token": share_token,
                "share_url": share_url,
                "share_type": share_type,
                "shared_conversation_id": str(shared_conversation.id),
                "include_workspace": include_workspace,
                "expires_at": expires_at_datetime,
                "created_at": conversation_share.created_at,
            }

        except Exception as e:
            session.rollback()
            logging.error(f"Error sharing conversation: {e}")
            raise
        finally:
            session.close()

    def get_shared_conversations(self):
        """
        Get all conversations shared with the current user.
        OPTIMIZED: Batch-fetch conversations and users instead of N+1 queries.

        Returns:
            list: List of shared conversation details
        """
        session = get_session()
        try:
            user_id = self._user_id
            if not user_id:
                return []

            # Get all shares where this user is the recipient
            shares = (
                session.query(ConversationShare)
                .filter(ConversationShare.shared_with_user_id == user_id)
                .all()
            )

            if not shares:
                return []

            # Filter out expired shares
            now = datetime.now()
            active_shares = [
                s for s in shares if not s.expires_at or s.expires_at >= now
            ]

            if not active_shares:
                return []

            # Batch-fetch all conversations and users in 2 queries
            conv_ids = list(set(s.shared_conversation_id for s in active_shares))
            user_ids = list(set(s.shared_by_user_id for s in active_shares))

            convs_map = {}
            if conv_ids:
                convs = (
                    session.query(Conversation)
                    .filter(Conversation.id.in_(conv_ids))
                    .all()
                )
                convs_map = {str(c.id): c for c in convs}

            users_map = {}
            if user_ids:
                users = session.query(User).filter(User.id.in_(user_ids)).all()
                users_map = {str(u.id): u for u in users}

            result = []
            for share in active_shares:
                shared_conv = convs_map.get(str(share.shared_conversation_id))
                shared_by = users_map.get(str(share.shared_by_user_id))

                if shared_conv:
                    result.append(
                        {
                            "conversation_id": str(shared_conv.id),
                            "conversation_name": shared_conv.name,
                            "share_token": share.share_token,
                            "shared_by": shared_by.email if shared_by else "Unknown",
                            "created_at": share.created_at,
                            "expires_at": share.expires_at,
                            "include_workspace": share.include_workspace,
                        }
                    )

            return result

        except Exception as e:
            logging.error(f"Error getting shared conversations: {e}")
            return []
        finally:
            session.close()

    def get_conversation_by_share_token(self, share_token):
        """
        Get conversation details by share token (public access).

        Args:
            share_token: The share token

        Returns:
            dict: Conversation details including history
        """
        session = get_session()
        try:
            # Find the share
            share = (
                session.query(ConversationShare)
                .filter(ConversationShare.share_token == share_token)
                .first()
            )

            if not share:
                raise ValueError("Share not found")

            # Check if expired
            if share.expires_at and share.expires_at < datetime.now():
                raise ValueError("Share has expired")

            # Get the shared conversation
            conversation = (
                session.query(Conversation)
                .filter(Conversation.id == share.shared_conversation_id)
                .first()
            )

            if not conversation:
                raise ValueError("Conversation not found")

            # Get shared by user
            shared_by = (
                session.query(User).filter(User.id == share.shared_by_user_id).first()
            )

            # Get messages
            messages = (
                session.query(Message)
                .filter(Message.conversation_id == conversation.id)
                .order_by(Message.timestamp.asc())
                .all()
            )

            # Structure messages with activities and subactivities
            conversation_history = []
            activity_map = {}  # Map activity IDs to their index in conversation_history
            orphaned_subactivities = {}  # Track subactivities without parents

            # First pass: collect all activities and orphaned subactivities
            for message in messages:
                content = str(message.content)

                # Check if this is a subactivity
                if content.startswith("[SUBACTIVITY]["):
                    # Extract parent activity ID
                    try:
                        # Format: [SUBACTIVITY][parent_id]...
                        parent_id = content.split("][")[1].split("]")[0]

                        # Create subactivity message
                        submsg = {
                            "id": str(message.id),
                            "role": message.role,
                            "message": content.replace(
                                "http://localhost:7437", getenv("AGIXT_URI")
                            ),
                            "timestamp": message.timestamp.isoformat(),
                        }

                        # Track for second pass
                        if parent_id not in orphaned_subactivities:
                            orphaned_subactivities[parent_id] = []
                        orphaned_subactivities[parent_id].append(submsg)
                    except (IndexError, ValueError) as e:
                        logging.warning(f"Could not parse subactivity parent ID: {e}")
                        # Add as regular message if parsing fails
                        msg = {
                            "id": str(message.id),
                            "role": message.role,
                            "message": content.replace(
                                "http://localhost:7437", getenv("AGIXT_URI")
                            ),
                            "timestamp": message.timestamp.isoformat(),
                            "children": [],
                        }
                        conversation_history.append(msg)
                else:
                    # Regular message or activity
                    msg = {
                        "id": str(message.id),
                        "role": message.role,
                        "message": content.replace(
                            "http://localhost:7437", getenv("AGIXT_URI")
                        ),
                        "timestamp": message.timestamp.isoformat(),
                        "children": [],
                    }

                    # If this is an activity, track it and attach any orphaned subactivities
                    if content.startswith("[ACTIVITY]"):
                        activity_id = str(message.id)
                        activity_map[activity_id] = len(conversation_history)

                        # Attach orphaned subactivities if they exist
                        if activity_id in orphaned_subactivities:
                            msg["children"] = orphaned_subactivities[activity_id]
                            del orphaned_subactivities[activity_id]

                    conversation_history.append(msg)

            # Insert placeholder activities for orphaned subactivities in chronological order
            for parent_id, subactivities in orphaned_subactivities.items():
                if subactivities:
                    # Create a placeholder "Completed activities" parent
                    # Use the timestamp of the first subactivity
                    placeholder_timestamp = subactivities[0]["timestamp"]
                    placeholder_activity = {
                        "id": parent_id,
                        "role": subactivities[0]["role"],
                        "message": "[ACTIVITY] Completed activities.",
                        "timestamp": placeholder_timestamp,
                        "children": subactivities,
                    }

                    # Find the correct position to insert based on timestamp
                    # Insert it right before its first subactivity would have appeared chronologically
                    inserted = False
                    for i, msg in enumerate(conversation_history):
                        if msg["timestamp"] > placeholder_timestamp:
                            conversation_history.insert(i, placeholder_activity)
                            inserted = True
                            break

                    # If we didn't insert it (all messages are earlier), append to end
                    if not inserted:
                        conversation_history.append(placeholder_activity)

            return {
                "conversation_history": conversation_history,
                "conversation_name": conversation.name,
                "conversation_id": str(conversation.id),
                "shared_by": shared_by.email if shared_by else "Unknown",
                "created_at": conversation.created_at,
                "include_workspace": share.include_workspace,
            }

        except Exception as e:
            logging.error(f"Error getting conversation by share token: {e}")
            raise
        finally:
            session.close()

    def revoke_share(self, share_token):
        """
        Revoke a conversation share.

        Args:
            share_token: The share token to revoke

        Returns:
            bool: True if successful
        """
        session = get_session()
        try:
            user_id = self._user_id
            if not user_id:
                raise ValueError("User not found")

            # Find the share
            share = (
                session.query(ConversationShare)
                .filter(
                    ConversationShare.share_token == share_token,
                    ConversationShare.shared_by_user_id == user_id,
                )
                .first()
            )

            if not share:
                raise ValueError("Share not found or you don't have permission")

            # Delete the share
            session.delete(share)
            session.commit()

            return True

        except Exception as e:
            session.rollback()
            logging.error(f"Error revoking share: {e}")
            raise
        finally:
            session.close()

    # =========================================================================
    # Group Chat / Participant Management
    # =========================================================================

    def create_group_conversation(
        self,
        company_id,
        conversation_type="group",
        agents=None,
        parent_id=None,
        parent_message_id=None,
        category=None,
        invite_only=False,
        force_new=False,
    ):
        """
        Create a new group conversation (channel) or thread within a company/group.

        Args:
            company_id: The company/group this channel belongs to
            conversation_type: 'group', 'dm', or 'thread'
            agents: Optional list of agent names to add as participants
            parent_id: For threads - the parent conversation ID
            parent_message_id: For threads - the message that spawned this thread
            category: Optional category for grouping channels (e.g., "Text Channels")
            invite_only: If True, only explicitly invited users can join

        Returns:
            dict with conversation info including id
        """
        session = get_session()
        user_id = self._user_id
        try:
            # For DM conversations, check if one already exists between the
            # same participants to avoid creating duplicates.
            # When force_new is True, skip dedup to allow creating additional conversations.
            if conversation_type == "dm" and not force_new:
                from sqlalchemy import func

                # Find DM conversations where the current user is a participant
                user_dm_ids = (
                    session.query(ConversationParticipant.conversation_id)
                    .join(
                        Conversation,
                        Conversation.id == ConversationParticipant.conversation_id,
                    )
                    .filter(
                        ConversationParticipant.user_id == user_id,
                        ConversationParticipant.status == "active",
                        Conversation.conversation_type == "dm",
                    )
                    .scalar_subquery()
                )

                # Check for existing DM with the same agent(s)
                if agents:
                    for agent_name in agents:
                        agent = (
                            session.query(Agent)
                            .filter(Agent.name == agent_name)
                            .first()
                        )
                        if agent:
                            existing = (
                                session.query(Conversation)
                                .join(
                                    ConversationParticipant,
                                    ConversationParticipant.conversation_id
                                    == Conversation.id,
                                )
                                .filter(
                                    Conversation.id.in_(user_dm_ids),
                                    ConversationParticipant.agent_id == str(agent.id),
                                    ConversationParticipant.status == "active",
                                )
                                .first()
                            )
                            if existing:
                                session.close()
                                return {
                                    "id": str(existing.id),
                                    "name": existing.name,
                                    "conversation_type": existing.conversation_type,
                                    "company_id": (
                                        str(existing.company_id)
                                        if existing.company_id
                                        else None
                                    ),
                                    "parent_id": (
                                        str(existing.parent_id)
                                        if existing.parent_id
                                        else None
                                    ),
                                    "parent_message_id": (
                                        str(existing.parent_message_id)
                                        if existing.parent_message_id
                                        else None
                                    ),
                                }
                else:
                    # User-to-user DM: look for existing DMs by conversation
                    # name pattern. The name is set by the frontend as
                    # "DM-{targetName}" so we match on the same name + creator.
                    existing = (
                        session.query(Conversation)
                        .filter(
                            Conversation.id.in_(user_dm_ids),
                            Conversation.name == self.conversation_name,
                            Conversation.conversation_type == "dm",
                        )
                        .first()
                    )
                    if existing:
                        session.close()
                        return {
                            "id": str(existing.id),
                            "name": existing.name,
                            "conversation_type": existing.conversation_type,
                            "company_id": (
                                str(existing.company_id)
                                if existing.company_id
                                else None
                            ),
                            "parent_id": (
                                str(existing.parent_id) if existing.parent_id else None
                            ),
                            "parent_message_id": (
                                str(existing.parent_message_id)
                                if existing.parent_message_id
                                else None
                            ),
                        }

            conversation = Conversation(
                name=self.conversation_name,
                user_id=user_id,
                conversation_type=conversation_type,
                company_id=company_id if company_id else None,
                parent_id=parent_id,
                parent_message_id=parent_message_id,
                category=category,
                invite_only=invite_only,
            )
            session.add(conversation)
            session.commit()
            conversation_id = str(conversation.id)
            self.conversation_id = conversation_id

            # Add the creator as owner participant
            from DB import get_new_id

            owner_participant = ConversationParticipant(
                conversation_id=conversation_id,
                user_id=user_id,
                participant_type="user",
                role="owner",
                status="active",
            )
            session.add(owner_participant)

            # Add agents as participants if specified
            if agents:
                for agent_name in agents:
                    agent = (
                        session.query(Agent).filter(Agent.name == agent_name).first()
                    )
                    if agent:
                        agent_participant = ConversationParticipant(
                            conversation_id=conversation_id,
                            agent_id=str(agent.id),
                            participant_type="agent",
                            role="member",
                            status="active",
                        )
                        session.add(agent_participant)

            # Auto-add all company members when not invite-only
            if not invite_only and company_id and conversation_type == "group":
                company_users = (
                    session.query(UserCompany)
                    .filter(UserCompany.company_id == company_id)
                    .all()
                )
                for uc in company_users:
                    uc_user_id = str(uc.user_id)
                    if uc_user_id == user_id:
                        continue  # Already added as owner
                    member_participant = ConversationParticipant(
                        conversation_id=conversation_id,
                        user_id=uc_user_id,
                        participant_type="user",
                        role="member",
                        status="active",
                    )
                    session.add(member_participant)

            # For threads: inherit participants from the parent conversation
            if conversation_type == "thread" and parent_id:
                parent_participants = (
                    session.query(ConversationParticipant)
                    .filter(
                        ConversationParticipant.conversation_id == parent_id,
                        ConversationParticipant.status == "active",
                    )
                    .all()
                )
                for pp in parent_participants:
                    pp_user_id = str(pp.user_id) if pp.user_id else None
                    if pp_user_id and pp_user_id == user_id:
                        continue  # Already added as owner
                    inherited = ConversationParticipant(
                        conversation_id=conversation_id,
                        user_id=pp_user_id,
                        agent_id=str(pp.agent_id) if pp.agent_id else None,
                        participant_type=pp.participant_type,
                        role="member",
                        status="active",
                    )
                    session.add(inherited)

            session.commit()
            return {
                "id": conversation_id,
                "name": self.conversation_name,
                "conversation_type": conversation_type,
                "company_id": company_id,
                "parent_id": parent_id,
                "parent_message_id": parent_message_id,
            }
        except Exception as e:
            session.rollback()
            logging.error(f"Error creating group conversation: {e}")
            raise
        finally:
            session.close()

    def can_speak(self, user_id: str) -> bool:
        """
        Check if a user can speak (send messages) in this conversation.
        Users with 'observer' participant role cannot speak.
        Locked threads only allow owner/admin to speak.
        Returns True if the user can speak, False if they are muted/observer.
        Non-group conversations always allow speaking (unless locked).
        If user has no participant record, allow speaking (they may be the owner).
        """
        conversation_id = self.get_conversation_id()
        if not conversation_id:
            return True
        session = get_session()
        try:
            conversation = (
                session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            if not conversation:
                return True

            # Check if conversation is locked (closed thread)
            if getattr(conversation, "locked", False):
                # Only owners and admins can speak in locked conversations
                participant = (
                    session.query(ConversationParticipant)
                    .filter(
                        ConversationParticipant.conversation_id == conversation_id,
                        ConversationParticipant.user_id == user_id,
                        ConversationParticipant.status == "active",
                    )
                    .first()
                )
                if not participant or participant.role not in ("owner", "admin"):
                    return False
                return True

            if conversation.conversation_type != "group":
                return True
            participant = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.status == "active",
                )
                .first()
            )
            if not participant:
                return True  # No participant record = allow (owner fallback)
            return participant.role != "observer"
        finally:
            session.close()

    def add_participant(
        self, user_id=None, agent_id=None, participant_type="user", role="member"
    ):
        """
        Add a user or agent as a participant to this conversation.

        Args:
            user_id: User ID to add (for user participants)
            agent_id: Agent ID to add (for agent participants)
            participant_type: 'user' or 'agent'
            role: 'owner', 'admin', 'member', 'observer'

        Returns:
            str: Participant ID
        """
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()

            # Check if already a participant
            existing = session.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.status == "active",
            )
            if participant_type == "user" and user_id:
                existing = existing.filter(
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.participant_type == "user",
                )
            elif participant_type == "agent" and agent_id:
                existing = existing.filter(
                    ConversationParticipant.agent_id == agent_id,
                    ConversationParticipant.participant_type == "agent",
                )
            else:
                raise ValueError(
                    "Must provide user_id for user participants or agent_id for agent participants"
                )

            existing_record = existing.first()
            if existing_record:
                return str(existing_record.id)

            participant = ConversationParticipant(
                conversation_id=conversation_id,
                user_id=user_id if participant_type == "user" else None,
                agent_id=agent_id if participant_type == "agent" else None,
                participant_type=participant_type,
                role=role,
                status="active",
            )
            session.add(participant)
            session.commit()
            participant_id = str(participant.id)
            return participant_id
        except Exception as e:
            session.rollback()
            logging.error(f"Error adding participant: {e}")
            raise
        finally:
            session.close()

    def remove_participant(self, participant_id):
        """Remove a participant from this conversation (sets status to 'removed')."""
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            participant = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.id == participant_id,
                    ConversationParticipant.conversation_id == conversation_id,
                )
                .first()
            )
            if not participant:
                raise ValueError("Participant not found")
            participant.status = "removed"
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logging.error(f"Error removing participant: {e}")
            raise
        finally:
            session.close()

    def get_participants(self):
        """
        Get all active participants in this conversation.
        For threads, inherits participants from the parent channel so that
        all channel members can see and access the thread. Thread-specific
        roles (e.g. owner) are preserved when they exist.

        Returns:
            List of participant dicts with user/agent info
        """
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()

            # Check if this is a thread with a parent channel
            conversation = (
                session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            parent_id = None
            if (
                conversation
                and conversation.conversation_type == "thread"
                and conversation.parent_id
            ):
                parent_id = str(conversation.parent_id)

            # Get thread's own participants
            thread_participants = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.status == "active",
                )
                .all()
            )

            # For threads, merge parent channel participants so all channel
            # members appear even if they weren't copied at thread creation time
            # or joined the channel after the thread was created.
            if parent_id:
                parent_participants = (
                    session.query(ConversationParticipant)
                    .filter(
                        ConversationParticipant.conversation_id == parent_id,
                        ConversationParticipant.status == "active",
                    )
                    .all()
                )
                # Build a set of (participant_type, user_id/agent_id) already
                # in the thread so we don't duplicate them
                existing_keys = set()
                for p in thread_participants:
                    if p.participant_type == "user" and p.user_id:
                        existing_keys.add(("user", str(p.user_id)))
                    elif p.participant_type == "agent" and p.agent_id:
                        existing_keys.add(("agent", str(p.agent_id)))

                # Add missing parent participants to the thread DB records
                # so they persist and have proper access going forward
                added_any = False
                for pp in parent_participants:
                    if pp.participant_type == "user" and pp.user_id:
                        key = ("user", str(pp.user_id))
                    elif pp.participant_type == "agent" and pp.agent_id:
                        key = ("agent", str(pp.agent_id))
                    else:
                        continue
                    if key not in existing_keys:
                        inherited = ConversationParticipant(
                            conversation_id=conversation_id,
                            user_id=(
                                pp.user_id if pp.participant_type == "user" else None
                            ),
                            agent_id=(
                                pp.agent_id if pp.participant_type == "agent" else None
                            ),
                            participant_type=pp.participant_type,
                            role="member",
                            status="active",
                        )
                        session.add(inherited)
                        added_any = True

                if added_any:
                    session.commit()
                    # Re-fetch to get the newly added participants
                    thread_participants = (
                        session.query(ConversationParticipant)
                        .filter(
                            ConversationParticipant.conversation_id == conversation_id,
                            ConversationParticipant.status == "active",
                        )
                        .all()
                    )

            participants = thread_participants

            # Batch-fetch all users and agents in 2 queries instead of N
            user_ids = [
                p.user_id
                for p in participants
                if p.participant_type == "user" and p.user_id
            ]
            agent_ids = [
                p.agent_id
                for p in participants
                if p.participant_type == "agent" and p.agent_id
            ]

            users_map = {}
            if user_ids:
                users = session.query(User).filter(User.id.in_(user_ids)).all()
                users_map = {str(u.id): u for u in users}

            agents_map = {}
            if agent_ids:
                agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
                agents_map = {str(a.id): a for a in agents}

            result = []
            # Pre-fetch timezone ONCE for fast inline conversion
            _convert_time_fast = _make_time_converter(self._user_id)

            for p in participants:
                participant_data = {
                    "id": str(p.id),
                    "participant_type": p.participant_type,
                    "role": p.role,
                    "joined_at": (
                        _convert_time_fast(p.joined_at).isoformat()
                        if p.joined_at
                        else None
                    ),
                    "last_read_at": (
                        _convert_time_fast(p.last_read_at).isoformat()
                        if p.last_read_at
                        else None
                    ),
                    "status": p.status,
                }
                if p.participant_type == "user" and p.user_id:
                    user = users_map.get(str(p.user_id))
                    if user:
                        participant_data["user"] = {
                            "id": str(user.id),
                            "email": user.email,
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "avatar_url": getattr(user, "avatar_url", None),
                            "last_seen": (
                                user.last_seen.isoformat()
                                if getattr(user, "last_seen", None)
                                else None
                            ),
                            "status_text": getattr(user, "status_text", None),
                        }
                elif p.participant_type == "agent" and p.agent_id:
                    agent = agents_map.get(str(p.agent_id))
                    if agent:
                        participant_data["agent"] = {
                            "id": str(agent.id),
                            "name": agent.name,
                        }
                result.append(participant_data)

            return result
        finally:
            session.close()

    def update_participant_role(self, participant_id, new_role):
        """Update a participant's role in this conversation."""
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            participant = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.id == participant_id,
                    ConversationParticipant.conversation_id == conversation_id,
                )
                .first()
            )
            if not participant:
                raise ValueError("Participant not found")
            participant.role = new_role
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating participant role: {e}")
            raise
        finally:
            session.close()

    def update_last_read(self, user_id=None):
        """Update the last_read_at timestamp for a user in this conversation."""
        session = get_session()
        try:
            effective_user_id = user_id or self._user_id
            conversation_id = self.get_conversation_id()
            participant = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.user_id == effective_user_id,
                    ConversationParticipant.status == "active",
                )
                .first()
            )
            if participant:
                participant.last_read_at = datetime.utcnow()
                session.commit()
            return True
        except Exception as e:
            session.rollback()
            logging.warning(f"Error updating last read: {e}")
            return False
        finally:
            session.close()

    def get_group_conversations_for_company(self, company_id):
        """
        Get all group conversations for a company that the current user is a participant of.

        Args:
            company_id: The company/group ID

        Returns:
            Dict of conversation details keyed by conversation ID
        """
        session = get_session()
        user_id = self._user_id
        try:
            # Single query: conversations where user is active participant OR owner
            all_conversations = (
                session.query(Conversation)
                .outerjoin(
                    ConversationParticipant,
                    ConversationParticipant.conversation_id == Conversation.id,
                )
                .filter(
                    Conversation.company_id == company_id,
                    Conversation.conversation_type == "group",
                    or_(
                        and_(
                            ConversationParticipant.user_id == user_id,
                            ConversationParticipant.status == "active",
                        ),
                        Conversation.user_id == user_id,
                    ),
                )
                .distinct()
                .all()
            )

            all_convos = {str(c.id): c for c in all_conversations}

            # Auto-create a #general channel if the company has no group channels at all
            if not all_convos:
                any_group = (
                    session.query(Conversation.id)
                    .filter(
                        Conversation.company_id == company_id,
                        Conversation.conversation_type == "group",
                    )
                    .first()
                )
                if not any_group:
                    general = Conversation(
                        name="general",
                        user_id=user_id,
                        conversation_type="group",
                        company_id=company_id,
                        category="Text Channels",
                    )
                    session.add(general)
                    session.commit()
                    general_id = str(general.id)

                    # Add all company members as participants
                    company_users = (
                        session.query(UserCompany)
                        .filter(UserCompany.company_id == company_id)
                        .all()
                    )
                    for uc in company_users:
                        uc_user_id = str(uc.user_id)
                        participant = ConversationParticipant(
                            conversation_id=general_id,
                            user_id=uc_user_id,
                            participant_type="user",
                            role="owner" if uc_user_id == user_id else "member",
                            status="active",
                        )
                        session.add(participant)
                    session.commit()

                    all_convos[general_id] = general

            # --- Batch all per-channel queries BEFORE the loop ---
            all_conv_ids = list(all_convos.keys())

            # Batch: participant records for this user
            user_participants = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id.in_(all_conv_ids),
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.status == "active",
                )
                .all()
            )
            participant_map = {str(p.conversation_id): p for p in user_participants}

            # Batch: participant counts per channel
            part_counts = (
                session.query(
                    ConversationParticipant.conversation_id,
                    func.count().label("cnt"),
                )
                .filter(
                    ConversationParticipant.conversation_id.in_(all_conv_ids),
                    ConversationParticipant.status == "active",
                )
                .group_by(ConversationParticipant.conversation_id)
                .all()
            )
            part_count_map = {str(r[0]): r[1] for r in part_counts}

            # Batch: thread counts per channel
            thr_counts = (
                session.query(
                    Conversation.parent_id,
                    func.count().label("cnt"),
                )
                .filter(
                    Conversation.parent_id.in_(all_conv_ids),
                    Conversation.conversation_type == "thread",
                )
                .group_by(Conversation.parent_id)
                .all()
            )
            thr_count_map = {str(r[0]): r[1] for r in thr_counts}

            # Batch: unread counts for channels with last_read_at baselines
            baseline_map = {}
            no_participant_ids = []
            for cid in all_conv_ids:
                p = participant_map.get(cid)
                if p:
                    mode = getattr(p, "notification_mode", None) or "all"
                    if mode != "none" and p.last_read_at:
                        baseline_map[cid] = p.last_read_at
                else:
                    no_participant_ids.append(cid)

            unread_count_map = {}  # conv_id -> int
            if baseline_map:
                baseline_case = case(
                    *[
                        (Message.conversation_id == cid, ts)
                        for cid, ts in baseline_map.items()
                    ],
                )
                rows = (
                    session.query(
                        Message.conversation_id,
                        func.count().label("cnt"),
                    )
                    .filter(
                        Message.conversation_id.in_(list(baseline_map.keys())),
                        Message.timestamp > baseline_case,
                        Message.role != "USER",
                        ~Message.content.like("[ACTIVITY]%"),
                        ~Message.content.like("[SUBACTIVITY]%"),
                    )
                    .group_by(Message.conversation_id)
                    .all()
                )
                for row in rows:
                    unread_count_map[str(row.conversation_id)] = row.cnt

            # Batch: fallback notify counts for channels without participant records
            if no_participant_ids:
                rows = (
                    session.query(
                        Message.conversation_id,
                        func.count().label("cnt"),
                    )
                    .filter(
                        Message.conversation_id.in_(no_participant_ids),
                        Message.notify == True,
                    )
                    .group_by(Message.conversation_id)
                    .all()
                )
                for row in rows:
                    unread_count_map[str(row.conversation_id)] = row.cnt

            # Pre-fetch timezone ONCE for fast inline conversion
            _convert_time_fast = _make_time_converter(user_id)

            result = {}
            for conv_id, conversation in all_convos.items():
                participant = participant_map.get(conv_id)
                notification_mode = (
                    getattr(participant, "notification_mode", None) or "all"
                    if participant
                    else "all"
                )
                notification_count = 0
                has_notifications = False
                if notification_mode != "none":
                    notification_count = unread_count_map.get(conv_id, 0)
                    has_notifications = notification_count > 0

                result[conv_id] = {
                    "name": conversation.name,
                    "conversation_type": conversation.conversation_type,
                    "company_id": (
                        str(conversation.company_id)
                        if conversation.company_id
                        else None
                    ),
                    "created_at": _convert_time_fast(conversation.created_at),
                    "updated_at": _convert_time_fast(conversation.updated_at),
                    "has_notifications": has_notifications,
                    "notification_count": notification_count,
                    "summary": conversation.summary or None,
                    "attachment_count": conversation.attachment_count or 0,
                    "pin_order": conversation.pin_order,
                    "participant_count": part_count_map.get(conv_id, 0),
                    "thread_count": thr_count_map.get(conv_id, 0),
                    "category": getattr(conversation, "category", None),
                    "description": getattr(conversation, "description", None),
                    "notification_mode": notification_mode,
                }

            return result
        finally:
            session.close()

    def get_threads(self, conversation_id=None):
        """
        Get all threads for a given parent conversation (channel).

        Args:
            conversation_id: The parent conversation ID. Uses self.conversation_id if not provided.

        Returns:
            List of thread dicts with id, name, parent_message_id, created_at, message_count
        """
        parent_id = conversation_id or self.conversation_id
        if not parent_id:
            return []

        session = get_session()
        user_id = self._user_id
        try:
            # Pre-fetch timezone ONCE for fast inline conversion
            _convert_time_fast = _make_time_converter(user_id)

            # Batch: message count + last message time per thread (avoids N+1)
            thread_stats = (
                session.query(
                    Message.conversation_id,
                    func.count().label("message_count"),
                    func.max(Message.timestamp).label("last_message_time"),
                )
                .group_by(Message.conversation_id)
                .subquery()
            )

            threads = (
                session.query(
                    Conversation,
                    thread_stats.c.message_count,
                    thread_stats.c.last_message_time,
                )
                .outerjoin(
                    thread_stats,
                    thread_stats.c.conversation_id == Conversation.id,
                )
                .filter(
                    Conversation.parent_id == parent_id,
                    Conversation.conversation_type == "thread",
                )
                .order_by(Conversation.created_at.desc())
                .all()
            )

            result = []
            for thread, message_count, last_message_time in threads:
                created = _convert_time_fast(thread.created_at)
                updated = _convert_time_fast(thread.updated_at)
                last_msg_time = _convert_time_fast(last_message_time)

                result.append(
                    {
                        "id": str(thread.id),
                        "name": thread.name,
                        "parent_id": (
                            str(thread.parent_id) if thread.parent_id else None
                        ),
                        "parent_message_id": (
                            str(thread.parent_message_id)
                            if thread.parent_message_id
                            else None
                        ),
                        "conversation_type": thread.conversation_type,
                        "created_at": (
                            created.isoformat()
                            if hasattr(created, "isoformat")
                            else str(created)
                        ),
                        "updated_at": (
                            updated.isoformat()
                            if hasattr(updated, "isoformat")
                            else str(updated)
                        ),
                        "message_count": message_count or 0,
                        "last_message_at": (
                            last_msg_time.isoformat()
                            if last_msg_time and hasattr(last_msg_time, "isoformat")
                            else str(last_msg_time) if last_msg_time else None
                        ),
                        "locked": getattr(thread, "locked", False) or False,
                    }
                )

            return result
        finally:
            session.close()

    def get_thread_count(self, conversation_id=None):
        """
        Get the count of threads for a conversation.
        """
        parent_id = conversation_id or self.conversation_id
        if not parent_id:
            return 0

        session = get_session()
        try:
            return (
                session.query(Conversation)
                .filter(
                    Conversation.parent_id == parent_id,
                    Conversation.conversation_type == "thread",
                )
                .count()
            )
        finally:
            session.close()
