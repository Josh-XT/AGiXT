from datetime import datetime, timedelta
import logging
import secrets
import asyncio
import pytz
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
from sqlalchemy.sql import func, or_
from MagicalAuth import convert_time, get_user_id, get_user_timezone
from SharedCache import shared_cache

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)

# Cache TTL for conversation ID lookups (uses SharedCache)
_conversation_id_cache_ttl = 30  # 30 seconds


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
    user = session.query(User).filter(User.id == user_id).first()
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
        user_company_ids = (
            session.query(UserCompany.company_id)
            .filter(UserCompany.user_id == user_id)
            .all()
        )
        company_ids = [str(uc[0]) for uc in user_company_ids]
        if company_ids:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.name == conversation_name,
                    Conversation.company_id.in_(company_ids),
                    Conversation.conversation_type.in_(["group", "dm", "thread", "channel"]),
                )
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
    session = get_session()
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
        user_company_ids = (
            session.query(UserCompany.company_id)
            .filter(UserCompany.user_id == user_id)
            .all()
        )
        company_ids = [str(uc[0]) for uc in user_company_ids]
        if company_ids:
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.id == conversation_id,
                    Conversation.company_id.in_(company_ids),
                    Conversation.conversation_type.in_(["group", "dm", "thread", "channel"]),
                )
                .first()
            )
    if not conversation:
        session.close()
        return "-"
    conversation_name = conversation.name
    session.close()
    return conversation_name


def get_conversation_name_by_message_id(message_id, user_id):
    """Get the conversation name that contains a specific message for a user."""
    session = get_session()
    message = (
        session.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Message.id == message_id,
            Conversation.user_id == user_id,
        )
        .first()
    )
    if not message:
        session.close()
        return None
    conversation = (
        session.query(Conversation)
        .filter(Conversation.id == message.conversation_id)
        .first()
    )
    conversation_name = conversation.name if conversation else None
    session.close()
    return conversation_name


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
        session.close()
        return history

    def get_conversations(self):
        session = get_session()
        user_id = self._user_id

        # Use a LEFT OUTER JOIN to get conversations and their messages
        conversations = (
            session.query(Conversation)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(Message.id != None)  # Only get conversations with messages
            .order_by(Conversation.updated_at.desc())
            .distinct()
            .all()
        )

        conversation_list = [conversation.name for conversation in conversations]
        session.close()
        return conversation_list

    def get_conversations_with_ids(self):
        session = get_session()
        user_id = self._user_id

        # Use a LEFT OUTER JOIN to get conversations and their messages
        conversations = (
            session.query(Conversation)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(Message.id != None)  # Only get conversations with messages
            .order_by(Conversation.updated_at.desc())
            .distinct()
            .all()
        )

        result = {
            str(conversation.id): conversation.name for conversation in conversations
        }
        session.close()
        return result

    def get_agent_id(self, user_id):
        session = get_session()
        agent_name = self.get_last_agent_name()
        # Get the agent's ID from the database
        # Make sure this agent belongs the the right user
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
            # Get the default agent for this user
            agent = session.query(Agent).filter(Agent.user_id == user_id).first()
            try:
                agent_id = str(agent.id)
            except:
                agent_id = None
        session.close()
        return agent_id

    def get_conversations_with_detail(self):
        """
        OPTIMIZED: Single query to get all conversation details with notifications
        and last message timestamps in one batch instead of N+1 queries.
        Also includes DM conversations where the user is a participant (not just owner).
        """
        session = get_session()
        user_id = self._user_id
        if not user_id:
            session.close()
            return {}

        # Get default agent_id once (not per conversation - they all share the same user)
        default_agent = session.query(Agent).filter(Agent.user_id == user_id).first()
        default_agent_id = str(default_agent.id) if default_agent else None

        # Subquery to get max message timestamp per conversation
        last_message_subq = (
            session.query(
                Message.conversation_id,
                func.max(Message.timestamp).label("last_message_time"),
            )
            .group_by(Message.conversation_id)
            .subquery()
        )

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

        # Single query: conversations owned by user OR where user is a participant
        # Exclude group channels and threads from DM/conversation list
        ownership_filter = Conversation.user_id == user_id
        participant_filter = Conversation.id.in_(participant_conv_id_list) if participant_conv_id_list else False

        conversations = (
            session.query(
                Conversation,
                func.count(Message.id)
                .filter(Message.notify == True)
                .label("notification_count"),
                last_message_subq.c.last_message_time,
            )
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .outerjoin(
                last_message_subq,
                last_message_subq.c.conversation_id == Conversation.id,
            )
            .filter(or_(ownership_filter, participant_filter))
            .filter(Message.id != None)
            # Exclude group channels and threads from DM/conversation list
            .filter(
                or_(
                    Conversation.conversation_type.is_(None),
                    Conversation.conversation_type.notin_(["group", "thread"]),
                )
            )
            .group_by(Conversation.id, last_message_subq.c.last_message_time)
            .all()
        )

        # Build result dict with all data from single query
        # For DM conversations, look up participant names so the frontend
        # can display "DM with <name>" instead of the raw conversation name.
        dm_conv_ids = [
            str(c.id) for c, _, _ in conversations
            if c.conversation_type == "dm"
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

        result = {}
        for conversation, notification_count, last_message_time in conversations:
            # Use last message time if available, otherwise use conversation updated_at
            effective_updated_at = last_message_time or conversation.updated_at
            conv_id = str(conversation.id)

            # For DMs, build a display name from the other participants
            display_name = conversation.name
            dm_participant_names = []
            if conversation.conversation_type == "dm" and conv_id in dm_participants:
                for p in dm_participants[conv_id]:
                    pid = str(p.user_id) if p.participant_type == "user" else str(p.agent_id)
                    # Skip the current user
                    if p.participant_type == "user" and str(p.user_id) == str(user_id):
                        continue
                    if p.participant_type == "user" and pid in user_name_map:
                        dm_participant_names.append(user_name_map[pid])
                    elif p.participant_type == "agent" and pid in agent_name_map:
                        dm_participant_names.append(agent_name_map[pid])
                if dm_participant_names:
                    display_name = ", ".join(dm_participant_names)

            result[conv_id] = {
                "name": conversation.name,
                "display_name": display_name,
                "agent_id": default_agent_id,
                "conversation_type": conversation.conversation_type,
                "created_at": convert_time(conversation.created_at, user_id=user_id),
                "updated_at": convert_time(effective_updated_at, user_id=user_id),
                "has_notifications": notification_count > 0,
                "summary": (
                    conversation.summary if conversation.summary else "None available"
                ),
                "attachment_count": conversation.attachment_count or 0,
                "pin_order": conversation.pin_order,
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
                    "timestamp": convert_time(message.timestamp, user_id=user_id),
                }
            )

        session.close()
        return result

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
        session = get_session()
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
                user_company_ids = (
                    session.query(UserCompany.company_id)
                    .filter(UserCompany.user_id == user_id)
                    .all()
                )
                company_ids = [str(uc[0]) for uc in user_company_ids]
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
            session.close()
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

        current_ids = set()
        if last_known_ids is not None:
            # Only query IDs if we need to check for deletions
            id_query = (
                session.query(Message.id)
                .filter(Message.conversation_id == conversation.id)
                .all()
            )
            current_ids = {str(row[0]) for row in id_query}

        # Calculate deleted IDs
        deleted_ids = []
        if last_known_ids:
            # Convert to strings for comparison
            last_known_str = {str(id) for id in last_known_ids}
            deleted_ids = list(last_known_str - current_ids)

        new_messages = []
        updated_messages = []

        if since_timestamp is not None:
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
                        "http://localhost:7437", getenv("AGIXT_URI")
                    ),
                    "timestamp": convert_time(message.timestamp, user_id=user_id),
                    "updated_at": convert_time(message.updated_at, user_id=user_id),
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
                        "http://localhost:7437", getenv("AGIXT_URI")
                    ),
                    "timestamp": convert_time(message.timestamp, user_id=user_id),
                    "updated_at": convert_time(message.updated_at, user_id=user_id),
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

        session.close()
        return {
            "new_messages": new_messages,
            "updated_messages": updated_messages,
            "deleted_ids": deleted_ids,
            "current_count": current_count,
        }

    def get_conversation(self, limit=1000, page=1):
        session = get_session()
        user_id = self._user_id
        if not self.conversation_name:
            self.conversation_name = "-"

        # Prefer conversation_id lookup to avoid duplicate name issues
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
                user_company_ids = (
                    session.query(UserCompany.company_id)
                    .filter(UserCompany.user_id == user_id)
                    .all()
                )
                company_ids = [str(uc[0]) for uc in user_company_ids]
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
            # Create the conversation
            conversation = Conversation(name=self.conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        else:
            # Mark all notifications as read for this conversation
            # Mark notifications as read in a fire-and-forget manner
            # This is not critical to the read path and shouldn't block message retrieval
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
            except Exception as e:
                session.rollback()
                logging.debug(f"Failed to mark notifications as read: {e}")
        offset = (page - 1) * limit
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        if not messages:
            session.close()
            return {"interactions": []}
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
        user_timezone = get_user_timezone(user_id)
        gmt = pytz.timezone("GMT")
        local_tz = pytz.timezone(user_timezone)

        # Inline timezone conversion to avoid per-message function call overhead
        def _convert_time_fast(utc_time):
            if utc_time is None:
                return None
            if utc_time.tzinfo is None:
                return gmt.localize(utc_time).astimezone(local_tz)
            return utc_time.astimezone(local_tz)

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
            }
            return_messages.append(msg)
        session.close()
        return {"interactions": return_messages}

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
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        if not messages:
            session.close()
            return {"activities": []}
        return_activities = []
        for message in messages:
            if message.content.startswith("[ACTIVITY]"):
                msg = {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                }
                return_activities.append(msg)
        # Order messages by timestamp oldest to newest
        return_activities = sorted(return_activities, key=lambda x: x["timestamp"])
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
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.timestamp.asc())
            .all()
        )
        if not messages:
            session.close()
            return ""
        return_subactivities = []
        for message in messages:
            if message.content.startswith(f"[SUBACTIVITY][{activity_id}]"):
                msg = {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "timestamp": message.timestamp,
                }
                return_subactivities.append(msg)
        # Order messages by timestamp oldest to newest
        return_subactivities = sorted(
            return_subactivities, key=lambda x: x["timestamp"]
        )
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
            .filter(Message.conversation_id == conversation.id)
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
            return None

        # Get the most recent thinking activity
        current_thinking = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
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
                Message.conversation_id == conversation.id,
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
        session = get_session()
        user_id = self._user_id
        # Get conversation_id first - it's stable even if name changes
        conversation_id = self.get_conversation_id()
        # Look up by ID instead of name to handle renames during a request
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
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
            child_convos = (
                session.query(Conversation)
                .filter(Conversation.parent_id == conv_id)
                .all()
            )
            for child in child_convos:
                # Recursively clean up child conversations
                child_conv_id = child.id
                session.query(DiscardedContext).filter(
                    DiscardedContext.conversation_id == child_conv_id
                ).delete()
                session.query(Memory).filter(
                    Memory.conversation_id == child_conv_id
                ).delete()
                child_message_ids = [
                    m.id
                    for m in session.query(Message.id)
                    .filter(Message.conversation_id == child_conv_id)
                    .all()
                ]
                if child_message_ids:
                    session.query(MessageReaction).filter(
                        MessageReaction.message_id.in_(child_message_ids)
                    ).delete(synchronize_session="fetch")
                session.query(Message).filter(
                    Message.conversation_id == child_conv_id
                ).delete()
                session.query(ConversationParticipant).filter(
                    ConversationParticipant.conversation_id == child_conv_id
                ).delete()
                session.query(ConversationShare).filter(
                    (ConversationShare.source_conversation_id == child_conv_id)
                    | (ConversationShare.shared_conversation_id == child_conv_id)
                ).delete(synchronize_session="fetch")
                session.delete(child)
            # 8. Finally delete the conversation itself
            session.query(Conversation).filter(
                Conversation.id == conv_id, Conversation.user_id == user_id
            ).delete()
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
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id
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
            return "AGiXT"
        message = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .filter(Message.role != "USER")
            .filter(Message.role != "user")
            .order_by(Message.timestamp.desc())
            .first()
        )
        if not message:
            session.close()
            return "AGiXT"
        session.close()
        return message.role

    def delete_message_by_id(self, message_id):
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
            user_company_ids = (
                session.query(UserCompany.company_id)
                .filter(UserCompany.user_id == user_id)
                .all()
            )
            company_ids = [str(uc[0]) for uc in user_company_ids]
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
            user_company_ids = (
                session.query(UserCompany.company_id)
                .filter(UserCompany.user_id == user_id)
                .all()
            )
            company_ids = [str(uc[0]) for uc in user_company_ids]
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
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id
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
        message.feedback_received = not message.feedback_received
        session.commit()
        session.close()

    def has_received_feedback(self, message):
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
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id
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
        feedback_received = message.feedback_received
        session.close()
        return feedback_received

    def update_message(self, message, new_message):
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
        message_id = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.content == message,
            )
            .first()
        ).id
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
        message.content = new_message
        session.commit()
        session.close()

    def update_message_by_id(self, message_id, new_message):
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
            user_company_ids = (
                session.query(UserCompany.company_id)
                .filter(UserCompany.user_id == user_id)
                .all()
            )
            company_ids = [str(uc[0]) for uc in user_company_ids]
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

    def get_conversation_id(self):
        # Return cached ID if available - this is stable even if name changes
        if self.conversation_id:
            return str(self.conversation_id)

        if not self.conversation_name:
            conversation_name = "-"
        else:
            conversation_name = self.conversation_name
        session = get_session()
        user_id = self._user_id
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.name == conversation_name,
                Conversation.user_id == user_id,
            )
            .first()
        )
        if not conversation:
            conversation = Conversation(name=conversation_name, user_id=user_id)
            session.add(conversation)
            session.commit()
        conversation_id = str(conversation.id)
        # Cache the ID for future calls
        self.conversation_id = conversation_id
        session.close()
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
            return None
        last_activity = (
            session.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .filter(Message.content.like("[ACTIVITY]%"))
            .order_by(Message.timestamp.desc())
            .first()
        )
        if not last_activity:
            session.close()
            return None
        last_id = last_activity.id
        session.close()
        return last_id

    def set_conversation_summary(self, summary: str):
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
            return ""
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation.id)
            .first()
        )
        conversation.summary = summary
        session.commit()
        session.close()
        return summary

    def get_conversation_summary(self):
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
            return ""
        summary = conversation.summary
        session.close()
        return summary

    def get_attachment_count(self):
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
            return 0
        attachment_count = conversation.attachment_count
        session.close()
        return attachment_count

    def update_attachment_count(self, count: int):
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
            return 0
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation.id)
            .first()
        )
        conversation.attachment_count = count
        session.commit()
        session.close()
        return count

    def increment_attachment_count(self):
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
            return 0
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation.id)
            .first()
        )
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

            result = []
            for share in shares:
                # Check if expired
                if share.expires_at and share.expires_at < datetime.now():
                    continue

                shared_conv = (
                    session.query(Conversation)
                    .filter(Conversation.id == share.shared_conversation_id)
                    .first()
                )
                shared_by = (
                    session.query(User)
                    .filter(User.id == share.shared_by_user_id)
                    .first()
                )

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
            conversation = Conversation(
                name=self.conversation_name,
                user_id=user_id,
                conversation_type=conversation_type,
                company_id=company_id,
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
        Returns True if the user can speak, False if they are muted/observer.
        Non-group conversations always allow speaking.
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
            if not conversation or conversation.conversation_type != "group":
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

            if existing.first():
                session.close()
                return str(existing.first().id)

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

        Returns:
            List of participant dicts with user/agent info
        """
        session = get_session()
        try:
            conversation_id = self.get_conversation_id()
            participants = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.status == "active",
                )
                .all()
            )

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
            for p in participants:
                participant_data = {
                    "id": str(p.id),
                    "participant_type": p.participant_type,
                    "role": p.role,
                    "joined_at": str(p.joined_at) if p.joined_at else None,
                    "last_read_at": str(p.last_read_at) if p.last_read_at else None,
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
            # Get conversations where user is a participant
            conversations = (
                session.query(Conversation)
                .join(
                    ConversationParticipant,
                    ConversationParticipant.conversation_id == Conversation.id,
                )
                .filter(
                    Conversation.company_id == company_id,
                    Conversation.conversation_type == "group",
                    ConversationParticipant.user_id == user_id,
                    ConversationParticipant.status == "active",
                )
                .all()
            )

            # Also include conversations the user owns (backward compat)
            owned_conversations = (
                session.query(Conversation)
                .filter(
                    Conversation.company_id == company_id,
                    Conversation.conversation_type == "group",
                    Conversation.user_id == user_id,
                )
                .all()
            )

            # Merge and deduplicate
            all_convos = {str(c.id): c for c in conversations}
            for c in owned_conversations:
                all_convos[str(c.id)] = c

            result = {}
            for conv_id, conversation in all_convos.items():
                # Count unread messages for this user
                participant = (
                    session.query(ConversationParticipant)
                    .filter(
                        ConversationParticipant.conversation_id == conv_id,
                        ConversationParticipant.user_id == user_id,
                        ConversationParticipant.status == "active",
                    )
                    .first()
                )

                has_notifications = False
                if participant and participant.last_read_at:
                    unread_count = (
                        session.query(Message)
                        .filter(
                            Message.conversation_id == conv_id,
                            Message.timestamp > participant.last_read_at,
                            Message.role != "USER",
                        )
                        .count()
                    )
                    has_notifications = unread_count > 0
                else:
                    # Check notify flag as fallback
                    has_notifications = (
                        session.query(Message)
                        .filter(
                            Message.conversation_id == conv_id,
                            Message.notify == True,
                        )
                        .count()
                        > 0
                    )

                # Count participants
                participant_count = (
                    session.query(ConversationParticipant)
                    .filter(
                        ConversationParticipant.conversation_id == conv_id,
                        ConversationParticipant.status == "active",
                    )
                    .count()
                )

                # Count threads
                thread_count = (
                    session.query(Conversation)
                    .filter(
                        Conversation.parent_id == conv_id,
                        Conversation.conversation_type == "thread",
                    )
                    .count()
                )

                result[conv_id] = {
                    "name": conversation.name,
                    "conversation_type": conversation.conversation_type,
                    "company_id": (
                        str(conversation.company_id)
                        if conversation.company_id
                        else None
                    ),
                    "created_at": convert_time(
                        conversation.created_at, user_id=user_id
                    ),
                    "updated_at": convert_time(
                        conversation.updated_at, user_id=user_id
                    ),
                    "has_notifications": has_notifications,
                    "summary": conversation.summary or "None available",
                    "attachment_count": conversation.attachment_count or 0,
                    "pin_order": conversation.pin_order,
                    "participant_count": participant_count,
                    "thread_count": thread_count,
                    "category": getattr(conversation, "category", None),
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
            threads = (
                session.query(Conversation)
                .filter(
                    Conversation.parent_id == parent_id,
                    Conversation.conversation_type == "thread",
                )
                .order_by(Conversation.created_at.desc())
                .all()
            )

            result = []
            for thread in threads:
                # Count messages in thread
                from DB import Message as MessageModel

                message_count = (
                    session.query(MessageModel)
                    .filter(MessageModel.conversation_id == str(thread.id))
                    .count()
                )

                # Get last message time
                last_message = (
                    session.query(MessageModel)
                    .filter(MessageModel.conversation_id == str(thread.id))
                    .order_by(MessageModel.timestamp.desc())
                    .first()
                )

                created = convert_time(thread.created_at, user_id=user_id)
                updated = convert_time(thread.updated_at, user_id=user_id)
                last_msg_time = (
                    convert_time(last_message.timestamp, user_id=user_id)
                    if last_message
                    else None
                )

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
                        "message_count": message_count,
                        "last_message_at": (
                            last_msg_time.isoformat()
                            if last_msg_time and hasattr(last_msg_time, "isoformat")
                            else str(last_msg_time) if last_msg_time else None
                        ),
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
