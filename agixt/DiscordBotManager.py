"""
Discord Bot Manager for AGiXT

This module manages Discord bots for multiple companies. Each company can have
its own Discord bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Monitors bot health and restarts failed bots
- Handles graceful shutdown of all bots
- Provides APIs for querying bot status
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# Import the discord.py library before any extensions that might shadow it
# We need to import it with a specific name to avoid conflicts with extensions/discord.py
DISCORD_AVAILABLE = False
discord_module = None
discord_commands = None

try:
    # Temporarily modify sys.path to exclude extensions directory
    # This ensures we get the installed discord.py package, not our extension
    import importlib
    import importlib.util

    # Find the discord.py package from site-packages, not from local extensions
    spec = importlib.util.find_spec("discord")
    if spec and spec.origin and "site-packages" in spec.origin:
        # Load from site-packages
        discord_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(discord_module)
        sys.modules["_discord_lib"] = discord_module

        # Now load discord.ext.commands
        ext_spec = importlib.util.find_spec("discord.ext.commands")
        if ext_spec and ext_spec.origin:
            discord_commands = importlib.util.module_from_spec(ext_spec)
            ext_spec.loader.exec_module(discord_commands)
            DISCORD_AVAILABLE = True
            logging.info("Successfully loaded discord.py library from site-packages")
        else:
            logging.warning("discord.ext.commands not found in site-packages")
    else:
        # Fallback: try direct import with path manipulation
        original_path = sys.path.copy()
        # Remove paths that might contain our extensions/discord.py
        sys.path = [
            p for p in sys.path if not p.endswith("agixt") and "extensions" not in p
        ]
        try:
            import discord as _discord_lib
            from discord.ext import commands as _discord_commands

            discord_module = _discord_lib
            discord_commands = _discord_commands
            DISCORD_AVAILABLE = True
            logging.info("Successfully loaded discord.py library via path manipulation")
        finally:
            sys.path = original_path
except ImportError as e:
    logging.warning(f"discord.py library not installed: {e}")
except Exception as e:
    logging.warning(f"Failed to load discord.py library: {e}")

from DB import get_session, CompanyExtensionSetting, Company
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions


# Import our discord extension's utility function (not the discord.py library)
# This must come after the discord library import to avoid shadowing
def _get_discord_user_ids(company_id=None):
    """Wrapper to import get_discord_user_ids from our extension."""
    from extensions.discord import get_discord_user_ids

    return get_discord_user_ids(company_id)


logger = logging.getLogger(__name__)


@dataclass
class BotStatus:
    """Status information for a company's Discord bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    guild_count: int = 0


class CompanyDiscordBot:
    """
    A Discord bot instance for a specific company.
    Handles user impersonation based on Discord user ID mapping.
    """

    def __init__(self, company_id: str, company_name: str, discord_token: str):
        self.company_id = company_id
        self.company_name = company_name
        self.discord_token = discord_token

        # Set up Discord bot using imported modules
        intents = discord_module.Intents.default()
        intents.message_content = True
        self.bot = discord_commands.Bot(command_prefix="!", intents=intents)

        # Cache for Discord user ID -> email mapping
        self.discord_user_cache: Dict[str, str] = {}
        self._is_ready = False
        self._started_at: Optional[datetime] = None

        # Register event handlers
        self._setup_events()

    def _setup_events(self):
        """Set up Discord event handlers."""

        @self.bot.event
        async def on_ready():
            self._is_ready = True
            self._started_at = datetime.now()
            self._refresh_discord_user_cache()
            logger.info(
                f"Discord bot for company {self.company_name} ({self.company_id}) "
                f"connected as {self.bot.user}. Loaded {len(self.discord_user_cache)} user mappings."
            )

        @self.bot.event
        async def on_message(message):
            # Ignore messages from the bot itself
            if message.author == self.bot.user:
                return
            await self._handle_message(message)
            await self.bot.process_commands(message)

    def _refresh_discord_user_cache(self):
        """
        Refresh the Discord user ID -> email mapping cache.

        For server-level bot (company_id == "server"), gets mappings from all companies.
        For company-specific bots, only gets mappings for that company.
        """
        try:
            if self.company_id == "server":
                # Server-level bot: get Discord user mappings from all companies
                self.discord_user_cache = _get_discord_user_ids(company_id=None)
            else:
                # Company-specific bot: only get mappings for this company
                self.discord_user_cache = _get_discord_user_ids(self.company_id)
            logger.debug(
                f"Refreshed Discord user cache for {self.company_name}: "
                f"{len(self.discord_user_cache)} users"
            )
        except Exception as e:
            logger.error(f"Failed to refresh Discord user cache: {e}")

    def _get_user_email_from_discord_id(self, discord_id: int) -> Optional[str]:
        """Get user email from Discord ID, refreshing cache if needed."""
        discord_id_str = str(discord_id)
        if discord_id_str not in self.discord_user_cache:
            self._refresh_discord_user_cache()
        return self.discord_user_cache.get(discord_id_str)

    def _get_conversation_name(self, message) -> str:
        """
        Generate a conversation name based on the Discord context.

        For server channels: "Discord-ServerName-ChannelName"
        For DMs: "Discord-Username"
        For group DMs: "Discord-User1-User2-..."
        """
        is_dm = isinstance(message.channel, discord_module.DMChannel)
        is_group_dm = isinstance(message.channel, discord_module.GroupChannel)

        if is_dm:
            # Direct message - use the other user's name
            return f"Discord-{message.author.display_name}"
        elif is_group_dm:
            # Group DM - list recipients (up to 3, then "and X more")
            recipients = [r.display_name for r in message.channel.recipients[:3]]
            if len(message.channel.recipients) > 3:
                recipients.append(f"and {len(message.channel.recipients) - 3} more")
            return f"Discord-{'-'.join(recipients)}"
        else:
            # Server channel - use server name and channel name
            server_name = message.guild.name if message.guild else "Unknown"
            channel_name = (
                message.channel.name if hasattr(message.channel, "name") else "unknown"
            )
            # Sanitize names (remove special chars that might cause issues)
            server_name = "".join(
                c for c in server_name if c.isalnum() or c in " -_"
            ).strip()
            channel_name = "".join(
                c for c in channel_name if c.isalnum() or c in " -_"
            ).strip()
            return f"Discord-{server_name}-{channel_name}"

    async def _handle_message(self, message):
        """Handle incoming Discord messages."""
        import base64
        import aiohttp

        # Get user email from Discord ID mapping
        user_email = self._get_user_email_from_discord_id(message.author.id)

        if not user_email:
            # User hasn't connected their Discord account via OAuth
            # Optionally send a message telling them to connect their account
            return

        # Get JWT for impersonation
        user_jwt = impersonate_user(user_email)

        # Create internal client for this user
        agixt = InternalClient(api_key=user_jwt, user=user_email)

        # Get the user's primary agent
        try:
            agents = agixt.get_agents()
            if agents and len(agents) > 0:
                # Use the first agent (primary) for this user
                agent_name = (
                    agents[0].get("name", "XT")
                    if isinstance(agents[0], dict)
                    else agents[0]
                )
            else:
                agent_name = "XT"  # Fallback to default
        except Exception as e:
            logger.warning(f"Could not get user's agents, using default: {e}")
            agent_name = "XT"

        # Check if the message is a direct message or mentions the bot
        is_dm = isinstance(message.channel, discord_module.DMChannel)
        is_group_dm = isinstance(message.channel, discord_module.GroupChannel)

        # Check for direct user mention
        is_user_mentioned = self.bot.user in message.mentions

        # Check if the bot's role is mentioned (bot roles are managed roles with the bot's ID)
        is_role_mentioned = False
        if hasattr(message, "role_mentions") and message.role_mentions:
            for role in message.role_mentions:
                # Bot-managed roles have a tag with bot_id matching the bot's user ID
                if (
                    hasattr(role, "tags")
                    and role.tags
                    and role.tags.bot_id == self.bot.user.id
                ):
                    is_role_mentioned = True
                    break

        # Bot responds to:
        # - DMs: Always respond
        # - Group DMs: Only when @mentioned (not every message)
        # - Server channels: When user or role is @mentioned
        should_respond = (
            is_dm
            or (is_group_dm and is_user_mentioned)
            or is_user_mentioned
            or is_role_mentioned
        )

        if should_respond:
            # Remove the bot mention from the message if present
            content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            # Also remove role mention if present
            if is_role_mentioned:
                for role in message.role_mentions:
                    if (
                        hasattr(role, "tags")
                        and role.tags
                        and role.tags.bot_id == self.bot.user.id
                    ):
                        content = content.replace(f"<@&{role.id}>", "").strip()

            # If the message is empty after removing the mention and has no attachments, ignore it
            if not content and not message.attachments:
                return

            # Start typing indicator that continues until we're done
            typing_task = None
            try:
                # Create a background task to keep typing indicator active
                async def keep_typing():
                    try:
                        while True:
                            # Use the HTTP API directly to trigger typing
                            await message.channel._state.http.send_typing(
                                message.channel.id
                            )
                            await asyncio.sleep(
                                5
                            )  # Discord typing lasts ~10 seconds, refresh every 5
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.debug(f"Typing indicator error: {e}")

                typing_task = asyncio.create_task(keep_typing())

                # Get channel and guild info for context
                channel_id = str(message.channel.id)
                channel_name = getattr(message.channel, "name", "DM")
                guild_id = str(message.guild.id) if message.guild else None
                guild_name = message.guild.name if message.guild else "Direct Message"

                # Generate human-readable conversation name (needed for workspace path)
                conversation_name = self._get_conversation_name(message)

                # Import AGiXT class to create instance early (need workspace path for attachment downloads)
                from XT import AGiXT

                # Create AGiXT instance with the user's context
                agixt_instance = AGiXT(
                    user=user_email,
                    agent_name=agent_name,
                    api_key=agixt.headers.get("Authorization", ""),
                    conversation_name=conversation_name,
                )

                # Get the workspace path for storing downloaded attachments
                workspace_path = agixt_instance.conversation_workspace

                # Get conversation context - fetch recent channel history and download attachments
                context, downloaded_files = await self._get_channel_context(
                    message.channel,
                    message,
                    user_email=user_email,
                    workspace_path=workspace_path,
                )

                # Build file guidance if any files were downloaded from history
                file_guidance = ""
                if downloaded_files:
                    file_guidance = (
                        "\n**FILES FROM CHANNEL HISTORY (downloaded to workspace):**\n"
                    )
                    for file_info in downloaded_files:
                        file_type_desc = self._get_file_type_description(
                            file_info.get("content_type", ""),
                            file_info.get("filename", ""),
                        )
                        file_guidance += f"- `{file_info['local_path']}` ({file_info['filename']}) - {file_type_desc}\n"
                    file_guidance += "\nYou can access these files using file reading commands or vision analysis as appropriate.\n\n"

                # Add channel info to context so agent knows where it is
                channel_info = f"""**CURRENT DISCORD LOCATION:**
- Server: {guild_name} (ID: {guild_id})
- Channel: #{channel_name} (ID: {channel_id})
- The agent can use 'Search Discord Channel' command to search for specific content further back in this channel's history.

**IMPORTANT TOOL GUIDANCE:**
- To get information from a specific URL or link, use 'Fetch Webpage Content' with the full URL.
- For Goodreads books, the URL format is: https://www.goodreads.com/book/show/{id}
- For general web research without a specific URL, use 'Web Search'.
- For images in the channel, use vision/image analysis commands with the file path.
- For documents (PDF, Word, etc.), use file reading commands with the file path.

{file_guidance}"""
                context = channel_info + context

                logger.info(
                    f"Discord context gathered ({len(context)} chars, {len(downloaded_files)} files): {context[:500]}..."
                    if len(context) > 500
                    else f"Discord context gathered: {context}"
                )

                # Prepare prompt arguments
                # Set conversation_results to 0 to not use AGiXT conversation history
                # since we're already providing the Discord channel context
                prompt_args = {
                    "user_input": content,
                    "context": context,
                    "conversation_results": 0,  # Disable AGiXT conversation history - use Discord context instead
                }

                # Handle current message attachments - download to workspace and add as file_urls
                current_msg_files = []
                if message.attachments:
                    file_urls = []
                    for attachment in message.attachments:
                        # Download to workspace
                        file_info = await self._download_attachment_to_workspace(
                            attachment, workspace_path, str(message.id)
                        )
                        if file_info:
                            current_msg_files.append(file_info)

                        # Also get base64 for vision pipeline
                        file_data = await self._download_attachment(attachment)
                        if file_data:
                            file_urls.append(file_data)

                    if file_urls:
                        prompt_args["file_urls"] = file_urls

                    # Add current message file paths to content for clarity
                    if current_msg_files:
                        file_list = ", ".join(
                            [f"`{f['local_path']}`" for f in current_msg_files]
                        )
                        content = f"{content}\n\n[User attached files: {file_list}]"

                logger.info(
                    f"Calling AGiXT with prompt_args keys: {list(prompt_args.keys())}, context_len={len(prompt_args.get('context', ''))}"
                )

                # Build messages in OpenAI chat format (agixt_instance already created above for workspace access)
                # When file_urls are present, use the multimodal content format for vision support
                if "file_urls" in prompt_args and prompt_args["file_urls"]:
                    # Build multimodal content as a list with text and file_url items
                    multimodal_content = [
                        {
                            "type": "text",
                            "text": content,
                        }
                    ]
                    # Add each file as a file_url type item for vision processing
                    for file_url in prompt_args["file_urls"]:
                        multimodal_content.append(
                            {
                                "type": "file_url",
                                "file_url": {"url": file_url},
                            }
                        )
                    message_data = {
                        "role": "user",
                        "content": multimodal_content,
                        "prompt_name": "Think About It",
                        "prompt_category": "Default",
                        "context": context,
                        "injected_memories": 0,  # Disable AGiXT conversation history - use Discord context instead
                        "prompt_args": prompt_args,
                    }
                    logger.info(
                        f"Built multimodal message with {len(prompt_args['file_urls'])} file(s) for vision processing"
                    )
                else:
                    message_data = {
                        "role": "user",
                        "content": content,
                        "prompt_name": "Think About It",
                        "prompt_category": "Default",
                        "context": context,
                        "injected_memories": 0,  # Disable AGiXT conversation history - use Discord context instead
                        "prompt_args": prompt_args,
                    }

                # Create ChatCompletions prompt with streaming enabled
                chat_prompt = ChatCompletions(
                    model=agent_name,
                    user=conversation_name,
                    messages=[message_data],
                    stream=True,
                )

                # Collect the full response from the streaming endpoint
                full_response = ""
                async for chunk in agixt_instance.chat_completions_stream(
                    prompt=chat_prompt
                ):
                    # Parse the SSE chunks to extract content
                    if chunk.startswith("data: "):
                        data = chunk[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            import json

                            chunk_data = json.loads(data)
                            if (
                                "choices" in chunk_data
                                and len(chunk_data["choices"]) > 0
                            ):
                                delta = chunk_data["choices"][0].get("delta", {})
                                content_chunk = delta.get("content", "")
                                if content_chunk:
                                    full_response += content_chunk
                        except json.JSONDecodeError:
                            # Some chunks might not be valid JSON, skip them
                            pass

                reply = (
                    full_response.strip()
                    if full_response
                    else "I couldn't generate a response."
                )

                # Split long messages if needed
                if len(reply) > 2000:
                    chunks = [reply[i : i + 2000] for i in range(0, len(reply), 2000)]
                    for chunk in chunks:
                        await message.reply(chunk)
                else:
                    await message.reply(reply)

            except Exception as e:
                logger.error(
                    f"Error handling message for company {self.company_name}: {e}"
                )
                await message.reply(f"Sorry, I encountered an error: {str(e)}")
            finally:
                # Cancel the typing indicator task
                if typing_task:
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass

    async def _get_channel_context(
        self,
        channel,
        current_message,
        limit=50,
        user_email: str = None,
        workspace_path: str = None,
    ) -> tuple:
        """Get recent conversation history for context and download any attachments.

        This fetches messages from the channel including timestamps and Discord user IDs,
        so the bot can understand the full conversation context with who said what and when.
        Timestamps are converted to the user's timezone for consistency with other AGiXT features.

        When workspace_path is provided, attachments from messages will be downloaded to the
        workspace so the agent can access them via file commands.

        Strategy:
        1. First try to get messages from the past hour
        2. If no messages found, fall back to fetching the last `limit` messages regardless of time

        Returns:
            tuple: (context_string, list_of_downloaded_files)
        """
        from datetime import datetime, timedelta, timezone
        from MagicalAuth import get_user_id, get_user_timezone, convert_time

        # Get user's timezone for timestamp conversion
        user_tz_name = "UTC"
        if user_email:
            try:
                user_id = get_user_id(user_email)
                user_tz_name = get_user_timezone(user_id)
            except Exception as e:
                logger.debug(f"Could not get user timezone, using UTC: {e}")

        messages = []
        downloaded_files = []  # Track all downloaded attachments
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        # First try to get recent messages (last hour)
        async for msg in channel.history(limit=limit, after=one_hour_ago):
            # Skip the current message being responded to (it's passed separately as user_input)
            if msg.id == current_message.id:
                continue

            # Skip the bot's own messages to prevent it from echoing previous answers
            if msg.author == self.bot.user:
                continue

            # Convert timestamp to user's timezone
            msg_time_utc = msg.created_at
            if user_email:
                try:
                    user_id = get_user_id(user_email)
                    msg_time_local = convert_time(msg_time_utc, user_id)
                    timestamp = (
                        msg_time_local.strftime("%Y-%m-%d %H:%M:%S")
                        + f" ({user_tz_name})"
                    )
                except Exception:
                    timestamp = msg_time_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                timestamp = msg_time_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

            # Get display name and Discord ID
            author_name = msg.author.display_name or msg.author.name
            author_id = msg.author.id

            # Mark if this is a bot (other bots, not ourselves - we skip our own messages)
            if msg.author.bot:
                author_label = f"{author_name} (Bot, ID:{author_id})"
            else:
                author_label = f"{author_name} (User, ID:{author_id})"

            # Include the message content, with attachment info if present
            content = msg.content if msg.content else "[No text content]"

            # Handle attachments - download if workspace provided
            if msg.attachments:
                attachment_info_parts = []
                for attachment in msg.attachments:
                    if workspace_path:
                        # Download attachment to workspace
                        file_info = await self._download_attachment_to_workspace(
                            attachment, workspace_path, str(msg.id)
                        )
                        if file_info:
                            downloaded_files.append(
                                {
                                    **file_info,
                                    "author": author_name,
                                    "timestamp": timestamp,
                                }
                            )
                            file_type = self._get_file_type_description(
                                file_info.get("content_type", ""),
                                file_info.get("filename", ""),
                            )
                            attachment_info_parts.append(
                                f"{attachment.filename} -> `{file_info['local_path']}` ({file_type})"
                            )
                        else:
                            attachment_info_parts.append(attachment.filename)
                    else:
                        attachment_info_parts.append(attachment.filename)

                content += f" [Attachments: {', '.join(attachment_info_parts)}]"

            # If it's just a URL (like a GIF), note that
            if msg.embeds:
                embed_types = [e.type for e in msg.embeds if e.type]
                if embed_types:
                    content += f" [Embed: {', '.join(embed_types)}]"

            # Store timestamp and formatted message for sorting
            messages.append((msg.created_at, timestamp, author_label, content))

        # If no messages in the last hour, fall back to fetching the last N messages regardless of time
        if not messages:
            logger.info(
                f"No messages in last hour, falling back to last {limit} messages"
            )
            async for msg in channel.history(limit=limit):
                # Skip the current message being responded to
                if msg.id == current_message.id:
                    continue

                # Skip the bot's own messages
                if msg.author == self.bot.user:
                    continue

                # Convert timestamp to user's timezone
                msg_time_utc = msg.created_at
                if user_email:
                    try:
                        user_id = get_user_id(user_email)
                        msg_time_local = convert_time(msg_time_utc, user_id)
                        timestamp = (
                            msg_time_local.strftime("%Y-%m-%d %H:%M:%S")
                            + f" ({user_tz_name})"
                        )
                    except Exception:
                        timestamp = msg_time_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    timestamp = msg_time_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

                # Get display name and Discord ID
                author_name = msg.author.display_name or msg.author.name
                author_id = msg.author.id

                # Mark if this is a bot
                if msg.author.bot:
                    author_label = f"{author_name} (Bot, ID:{author_id})"
                else:
                    author_label = f"{author_name} (User, ID:{author_id})"

                # Include the message content
                content = msg.content if msg.content else "[No text content]"

                # Handle attachments - download if workspace provided
                if msg.attachments:
                    attachment_info_parts = []
                    for attachment in msg.attachments:
                        if workspace_path:
                            # Download attachment to workspace
                            file_info = await self._download_attachment_to_workspace(
                                attachment, workspace_path, str(msg.id)
                            )
                            if file_info:
                                downloaded_files.append(
                                    {
                                        **file_info,
                                        "author": author_name,
                                        "timestamp": timestamp,
                                    }
                                )
                                file_type = self._get_file_type_description(
                                    file_info.get("content_type", ""),
                                    file_info.get("filename", ""),
                                )
                                attachment_info_parts.append(
                                    f"{attachment.filename} -> `{file_info['local_path']}` ({file_type})"
                                )
                            else:
                                attachment_info_parts.append(attachment.filename)
                        else:
                            attachment_info_parts.append(attachment.filename)

                    content += f" [Attachments: {', '.join(attachment_info_parts)}]"

                if msg.embeds:
                    embed_types = [e.type for e in msg.embeds if e.type]
                    if embed_types:
                        content += f" [Embed: {', '.join(embed_types)}]"

                messages.append((msg.created_at, timestamp, author_label, content))

        if not messages:
            return (
                "**DISCORD CHANNEL CONTEXT**: No conversation history found in this channel.",
                downloaded_files,
            )

        # Sort by timestamp descending (most recent FIRST)
        messages.sort(key=lambda x: x[0], reverse=True)

        # Build a quick reference of each user's most recent message
        user_most_recent = {}  # author_name -> (timestamp, content)
        for _, timestamp, author_label, content in messages:
            # Extract just the name part before " (User" or " (Bot"
            author_name = author_label.split(" (")[0]
            if author_name not in user_most_recent:
                user_most_recent[author_name] = (timestamp, content[:100])

        # Format quick reference section
        quick_ref_lines = ["**MOST RECENT MESSAGE FROM EACH USER:**"]
        for author_name, (timestamp, content) in user_most_recent.items():
            quick_ref_lines.append(
                f"- {author_name}: [{timestamp}] {content}{'...' if len(content) >= 100 else ''}"
            )
        quick_reference = "\n".join(quick_ref_lines)

        # Format with numbered indices - #1 is MOST RECENT
        formatted_messages = []
        for idx, (_, timestamp, author_label, content) in enumerate(messages, 1):
            formatted_messages.append(f"#{idx} [{timestamp}] {author_label}: {content}")
            # Log Nick's messages specifically to debug
            if "Nick" in author_label:
                logger.info(f"Nick's message #{idx}: [{timestamp}] {content[:50]}...")

        # Add a header to clarify this is conversation history from Discord
        header = f"""**DISCORD CHANNEL CONTEXT**
This is the real-time conversation happening in the Discord channel.
Files attached to messages have been downloaded to the workspace - use file paths shown to access them.
Total messages in last hour: {len(messages)} (bot's own messages excluded)
Downloaded files: {len(downloaded_files)}
Timestamps shown in: {user_tz_name}

{quick_reference}

**FULL MESSAGE HISTORY (most recent first):**

HOW TO READ:
- Messages are numbered by recency: #1 is the MOST RECENT, higher numbers are OLDER
- When asked about someone's "last" or "most recent" message, find the LOWEST # for that user
- User messages are labeled "(User, ID:...)"
- Attached files show their workspace path in backticks - use these paths with file commands
---"""

        return (f"{header}\n" + "\n".join(formatted_messages), downloaded_files)

    async def _download_attachment(self, attachment) -> Optional[str]:
        """Download an attachment and return its base64 encoded content."""
        import base64
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as response:
                if response.status == 200:
                    data = await response.read()
                    encoded_data = base64.b64encode(data).decode("utf-8")
                    return f"data:{attachment.content_type};base64,{encoded_data}"
        return None

    async def _download_attachment_to_workspace(
        self, attachment, workspace_path: str, message_id: str
    ) -> Optional[Dict[str, str]]:
        """
        Download a Discord attachment to the agent's workspace.

        Args:
            attachment: Discord attachment object
            workspace_path: Path to the agent's conversation workspace
            message_id: Discord message ID (used for organizing files)

        Returns:
            Dict with 'local_path', 'filename', 'content_type', and 'url' if successful, None otherwise
        """
        import aiohttp
        import os

        try:
            # Create a subdirectory for Discord attachments
            attachments_dir = os.path.join(workspace_path, "discord_attachments")
            os.makedirs(attachments_dir, exist_ok=True)

            # Generate a unique filename using message_id to avoid collisions
            safe_filename = f"{message_id}_{attachment.filename}"
            local_path = os.path.join(attachments_dir, safe_filename)

            # Download the file
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        data = await response.read()
                        with open(local_path, "wb") as f:
                            f.write(data)

                        logger.debug(f"Downloaded attachment to: {local_path}")
                        return {
                            "local_path": local_path,
                            "filename": attachment.filename,
                            "content_type": attachment.content_type
                            or "application/octet-stream",
                            "url": attachment.url,
                            "size": attachment.size,
                        }
            return None
        except Exception as e:
            logger.error(f"Error downloading attachment {attachment.filename}: {e}")
            return None

    def _get_file_type_description(self, content_type: str, filename: str) -> str:
        """Get a human-readable description of the file type for the agent."""
        if not content_type:
            content_type = ""

        # Image types
        if content_type.startswith("image/") or filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        ):
            return "IMAGE - Use vision/image analysis to view this"

        # Document types
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            return "PDF DOCUMENT - Use 'Read PDF' or file reading commands"

        if filename.lower().endswith((".doc", ".docx")):
            return "WORD DOCUMENT - Use file reading commands"

        if filename.lower().endswith((".xls", ".xlsx")):
            return "EXCEL SPREADSHEET - Use file reading commands"

        if filename.lower().endswith((".txt", ".md", ".json", ".csv", ".log")):
            return "TEXT FILE - Use 'Read File' command"

        if filename.lower().endswith(
            (".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".html", ".css")
        ):
            return "CODE FILE - Use 'Read File' command"

        # Audio/Video
        if content_type.startswith("audio/") or filename.lower().endswith(
            (".mp3", ".wav", ".ogg", ".m4a")
        ):
            return "AUDIO FILE"

        if content_type.startswith("video/") or filename.lower().endswith(
            (".mp4", ".mov", ".avi", ".webm")
        ):
            return "VIDEO FILE"

        return "FILE - Use appropriate file reading commands"

    async def start(self):
        """Start the Discord bot."""
        try:
            await self.bot.start(self.discord_token)
        except Exception as e:
            logger.error(f"Bot for company {self.company_name} failed: {e}")
            raise

    async def stop(self):
        """Stop the Discord bot gracefully."""
        if not self.bot.is_closed():
            await self.bot.close()
        self._is_ready = False

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def guild_count(self) -> int:
        return len(self.bot.guilds) if self._is_ready else 0


class DiscordBotManager:
    """
    Manages Discord bots for multiple companies.

    This class handles:
    - Starting/stopping bots based on company settings
    - Supporting server-level bot token as default for all companies
    - Monitoring bot health
    - Providing status information
    - Graceful shutdown of all bots

    Bot Token Precedence:
    1. Company-level DISCORD_BOT_TOKEN in CompanyExtensionSetting (if enabled)
    2. Server-level DISCORD_BOT_TOKEN environment variable (shared by all companies)
    """

    SERVER_BOT_ID = "server"  # Special ID for server-level bot

    def __init__(self):
        self.bots: Dict[str, CompanyDiscordBot] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def get_server_bot_token(self) -> Optional[str]:
        """Get the server-level Discord bot token from environment or ServerExtensionSetting."""
        # First check environment variable
        token = getenv("DISCORD_BOT_TOKEN")
        if token:
            return token

        # Then check ServerExtensionSetting table (where OAuth settings are stored)
        try:
            from DB import ServerExtensionSetting
            from endpoints.ServerConfig import decrypt_config_value

            with get_session() as db:
                setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == "discord",
                        ServerExtensionSetting.setting_key == "DISCORD_BOT_TOKEN",
                    )
                    .first()
                )
                if setting and setting.setting_value:
                    if setting.is_sensitive:
                        return decrypt_config_value(setting.setting_value)
                    return setting.setting_value
        except Exception as e:
            logger.error(f"Error getting server bot token from database: {e}")

        return None

    def get_company_bot_config(self) -> Dict[str, Dict[str, str]]:
        """
        Get Discord bot configuration for all companies from the database.
        Returns: {company_id: {"token": "...", "enabled": "true/false", "name": "..."}}
        """
        configs = {}

        with get_session() as db:
            # Get all companies with Discord bot settings
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(CompanyExtensionSetting.extension_name == "discord")
                .filter(
                    CompanyExtensionSetting.setting_key.in_(
                        ["DISCORD_BOT_TOKEN", "DISCORD_BOT_ENABLED"]
                    )
                )
                .all()
            )

            # Group by company
            for setting in settings:
                company_id = str(setting.company_id)
                if company_id not in configs:
                    # Get company name
                    company = (
                        db.query(Company)
                        .filter(Company.id == setting.company_id)
                        .first()
                    )
                    configs[company_id] = {
                        "name": company.name if company else "Unknown",
                        "token": None,
                        "enabled": "false",
                    }

                # Decrypt if needed
                value = setting.setting_value
                if setting.is_sensitive and value:
                    from endpoints.ServerConfig import decrypt_config_value

                    value = decrypt_config_value(value)

                if setting.setting_key == "DISCORD_BOT_TOKEN":
                    configs[company_id]["token"] = value
                elif setting.setting_key == "DISCORD_BOT_ENABLED":
                    configs[company_id]["enabled"] = value

        return configs

    async def start_bot_for_company(
        self, company_id: str, company_name: str, token: str
    ) -> bool:
        """Start a Discord bot for a specific company."""
        if company_id in self.bots and company_id in self._tasks:
            logger.warning(f"Bot for company {company_name} is already running")
            return False

        try:
            bot = CompanyDiscordBot(company_id, company_name, token)
            self.bots[company_id] = bot

            # Create and store the task
            task = asyncio.create_task(bot.start())
            self._tasks[company_id] = task

            # Add error callback
            task.add_done_callback(
                lambda t: self._handle_bot_error(company_id, company_name, t)
            )

            logger.info(
                f"Started Discord bot for company {company_name} ({company_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start bot for company {company_name}: {e}")
            return False

    def _handle_bot_error(self, company_id: str, company_name: str, task: asyncio.Task):
        """Handle bot task completion/failure."""
        try:
            exc = task.exception()
            if exc:
                logger.error(f"Bot for company {company_name} crashed: {exc}")
        except asyncio.CancelledError:
            logger.info(f"Bot for company {company_name} was cancelled")
        except Exception as e:
            logger.error(f"Error checking bot task for {company_name}: {e}")

        # Clean up
        if company_id in self.bots:
            del self.bots[company_id]
        if company_id in self._tasks:
            del self._tasks[company_id]

    async def stop_bot_for_company(self, company_id: str) -> bool:
        """Stop a Discord bot for a specific company."""
        if company_id not in self.bots:
            logger.warning(f"No bot running for company {company_id}")
            return False

        try:
            bot = self.bots[company_id]
            await bot.stop()

            # Cancel the task if it exists
            if company_id in self._tasks:
                task = self._tasks[company_id]
                if not task.done():
                    task.cancel()

            # Clean up
            del self.bots[company_id]
            if company_id in self._tasks:
                del self._tasks[company_id]

            logger.info(f"Stopped Discord bot for company {company_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop bot for company {company_id}: {e}")
            return False

    async def sync_bots(self):
        """
        Sync running bots with database configuration.

        Priority:
        1. If companies have their own DISCORD_BOT_TOKEN + DISCORD_BOT_ENABLED=true,
           start company-specific bots
        2. If no company bots are configured but server-level DISCORD_BOT_TOKEN exists,
           start a single server-level bot that handles all companies
        """
        server_token = self.get_server_bot_token()
        company_configs = self.get_company_bot_config()

        # Check if any company has its own bot configured and enabled
        company_bots_configured = any(
            config.get("enabled", "").lower() == "true" and config.get("token")
            for config in company_configs.values()
        )

        if company_bots_configured:
            # Company-level bots take precedence - stop server bot if running
            if self.SERVER_BOT_ID in self.bots:
                logger.info(
                    "Stopping server-level bot in favor of company-specific bots"
                )
                await self.stop_bot_for_company(self.SERVER_BOT_ID)

            # Stop company bots that should not be running
            companies_to_stop = []
            for company_id in list(self.bots.keys()):
                if company_id == self.SERVER_BOT_ID:
                    continue
                config = company_configs.get(company_id)
                if not config or config.get("enabled", "").lower() != "true":
                    companies_to_stop.append(company_id)

            for company_id in companies_to_stop:
                await self.stop_bot_for_company(company_id)

            # Start company bots that should be running
            for company_id, config in company_configs.items():
                if (
                    config.get("enabled", "").lower() == "true"
                    and config.get("token")
                    and company_id not in self.bots
                ):
                    await self.start_bot_for_company(
                        company_id, config["name"], config["token"]
                    )

        elif server_token:
            # No company bots configured - use server-level bot
            # Stop any lingering company bots
            for company_id in list(self.bots.keys()):
                if company_id != self.SERVER_BOT_ID:
                    await self.stop_bot_for_company(company_id)

            # Start server-level bot if not running
            if self.SERVER_BOT_ID not in self.bots:
                logger.info(
                    "Starting server-level Discord bot (shared across all companies)"
                )
                await self.start_bot_for_company(
                    self.SERVER_BOT_ID, "AGiXT Server Bot", server_token
                )
        else:
            # No tokens configured anywhere - stop all bots
            for company_id in list(self.bots.keys()):
                await self.stop_bot_for_company(company_id)

            if not self.bots:
                logger.debug(
                    "No Discord bot tokens configured (server or company level)"
                )

    async def _monitor_loop(self):
        """Monitor loop that syncs bots periodically."""
        while self._running:
            try:
                await self.sync_bots()
            except Exception as e:
                logger.error(f"Error in Discord bot monitor loop: {e}")

            # Check every 60 seconds
            await asyncio.sleep(60)

    async def start(self):
        """Start the Discord bot manager."""
        self._running = True
        logger.info("Starting Discord Bot Manager...")

        # Initial sync
        await self.sync_bots()

        # Start monitor loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Discord Bot Manager started")

    async def stop(self):
        """Stop all bots and the manager."""
        self._running = False

        # Cancel monitor task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

        # Stop all bots
        for company_id in list(self.bots.keys()):
            await self.stop_bot_for_company(company_id)

        logger.info("Discord Bot Manager stopped")

    def get_status(self) -> Dict[str, BotStatus]:
        """Get status of all running bots."""
        statuses = {}
        for company_id, bot in self.bots.items():
            statuses[company_id] = BotStatus(
                company_id=company_id,
                company_name=bot.company_name,
                started_at=bot.started_at,
                is_running=bot.is_ready,
                guild_count=bot.guild_count,
            )
        return statuses

    def get_bot_status(self, company_id: str) -> Optional[BotStatus]:
        """Get status of a specific company's bot."""
        bot = self.bots.get(company_id)
        if not bot:
            return None
        return BotStatus(
            company_id=company_id,
            company_name=bot.company_name,
            started_at=bot.started_at,
            is_running=bot.is_ready,
            guild_count=bot.guild_count,
        )


# Global instance for use in endpoints
_manager: Optional[DiscordBotManager] = None


def get_discord_bot_manager() -> Optional[DiscordBotManager]:
    """Get the global Discord bot manager instance."""
    return _manager


async def start_discord_bot_manager():
    """Start the global Discord bot manager."""
    global _manager

    if not DISCORD_AVAILABLE:
        logger.warning(
            "Discord bot manager cannot start - discord.py library not installed"
        )
        return None

    if _manager is None:
        _manager = DiscordBotManager()
    await _manager.start()
    return _manager


async def stop_discord_bot_manager():
    """Stop the global Discord bot manager."""
    global _manager
    if _manager:
        await _manager.stop()
        _manager = None
