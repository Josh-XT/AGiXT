"""
Slack Bot Manager for AGiXT

This module manages Slack bots for multiple companies. Each company can have
its own Slack bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Uses Slack Socket Mode for real-time messaging
- Handles graceful shutdown of all bots
- Provides APIs for querying bot status

Requires:
- slack-sdk package with socket mode support
- SLACK_BOT_TOKEN (xoxb-...) for bot authentication
- SLACK_APP_TOKEN (xapp-...) for socket mode connection
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# Import Slack SDK
SLACK_AVAILABLE = False
slack_sdk = None
slack_socket_mode = None

try:
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    SLACK_AVAILABLE = True
    logging.info("Successfully loaded slack-sdk library")
except ImportError as e:
    logging.warning(f"slack-sdk library not installed: {e}")
except Exception as e:
    logging.warning(f"Failed to load slack-sdk library: {e}")

from DB import get_session, CompanyExtensionSetting, Company
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions


def _get_slack_user_ids(company_id=None):
    """Wrapper to import get_slack_user_ids from our extension."""
    from extensions.slack import get_slack_user_ids

    return get_slack_user_ids(company_id)


logger = logging.getLogger(__name__)


@dataclass
class SlackBotStatus:
    """Status information for a company's Slack bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    workspace_name: str = ""


class CompanySlackBot:
    """
    A Slack bot instance for a specific company.
    Handles user impersonation based on Slack user ID mapping.
    
    Permission modes:
    - owner_only: Only the user who set up the bot can interact
    - recognized_users: Only users with linked AGiXT accounts can interact (default)
    - anyone: Anyone can interact with the bot
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        bot_token: str,
        app_token: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.bot_token = bot_token
        self.app_token = app_token
        
        # Bot configuration
        self.bot_agent_id = bot_agent_id  # The specific agent to use (None = user's default)
        self.bot_permission_mode = bot_permission_mode  # owner_only, recognized_users, anyone
        self.bot_owner_id = bot_owner_id  # User ID of who configured this bot

        # Initialize Slack clients
        self.web_client = WebClient(token=bot_token)
        self.socket_client = None

        # Cache for Slack user ID -> email mapping
        self.slack_user_cache: Dict[str, str] = {}
        # Cache for user's selected agent per channel
        self.user_agent_selection: Dict[tuple, str] = {}
        # Team channel configuration
        self.team_channel_config: Dict[str, Dict[str, str]] = {}

        self._is_ready = False
        self._started_at: Optional[datetime] = None
        self._workspace_name = ""
        self._bot_user_id = None

    def _refresh_slack_user_cache(self):
        """Refresh the Slack user ID -> email mapping cache."""
        try:
            if self.company_id == "server":
                self.slack_user_cache = _get_slack_user_ids(company_id=None)
            else:
                self.slack_user_cache = _get_slack_user_ids(self.company_id)
            logger.debug(
                f"Refreshed Slack user cache for {self.company_name}: "
                f"{len(self.slack_user_cache)} users"
            )
        except Exception as e:
            logger.error(f"Failed to refresh Slack user cache: {e}")

    def _get_user_email_from_slack_id(self, slack_id: str) -> Optional[str]:
        """Get user email from Slack ID, refreshing cache if needed."""
        if slack_id not in self.slack_user_cache:
            self._refresh_slack_user_cache()
        return self.slack_user_cache.get(slack_id)

    def _get_conversation_name(self, channel_id: str, channel_name: str = None) -> str:
        """Generate a conversation name based on the Slack context."""
        if channel_name:
            return f"Slack-{self.company_name}-{channel_name}"
        return f"Slack-{self.company_id}-{channel_id}"

    async def _handle_message(self, event: dict):
        """Handle incoming Slack messages."""
        import base64
        import aiohttp
        from DB import User

        # Ignore bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        # Check if bot was mentioned
        bot_mention = f"<@{self._bot_user_id}>"
        is_mentioned = bot_mention in text
        is_dm = event.get("channel_type") == "im"

        # Only respond to DMs or mentions
        if not is_dm and not is_mentioned:
            return

        # Remove bot mention from text
        text = text.replace(bot_mention, "").strip()

        # Get user email from Slack ID mapping
        user_email = self._get_user_email_from_slack_id(user_id)
        
        # Apply permission mode checks
        use_owner_context = False
        if self.bot_permission_mode == "owner_only":
            # Only the owner can interact
            if not user_email or not self.bot_owner_id:
                return
            try:
                from MagicalAuth import get_user_id
                interacting_user_id = str(get_user_id(user_email))
                if interacting_user_id != self.bot_owner_id:
                    return
            except Exception as e:
                logger.warning(f"Error checking owner permission: {e}")
                return
        elif self.bot_permission_mode == "recognized_users":
            if not user_email:
                try:
                    self.web_client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text="Please connect your Slack account to use this bot. Visit your profile settings to link your account.",
                    )
                except Exception as e:
                    logger.error(f"Error sending connection message: {e}")
                return
        elif self.bot_permission_mode == "anyone":
            if not user_email:
                use_owner_context = True
                if self.bot_owner_id:
                    try:
                        with get_session() as db:
                            owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                            if owner:
                                user_email = owner.email
                    except Exception as e:
                        logger.error(f"Error getting owner email for anonymous interaction: {e}")
                        return
                if not user_email:
                    logger.warning("Cannot handle anonymous interaction: no owner configured")
                    return
        else:
            if not user_email:
                return

        # Get JWT for impersonation
        user_jwt = impersonate_user(user_email)

        # Create internal client for this user
        agixt = InternalClient(api_key=user_jwt, user=user_email)

        # Determine which agent to use
        agent_name = None
        
        # If bot has a configured agent, use it
        if self.bot_agent_id:
            try:
                agents = agixt.get_agents()
                for agent in agents:
                    if isinstance(agent, dict) and str(agent.get("id")) == str(self.bot_agent_id):
                        agent_name = agent.get("name", "XT")
                        break
                if not agent_name:
                    logger.warning(f"Configured bot agent ID {self.bot_agent_id} not found, using default")
            except Exception as e:
                logger.warning(f"Could not lookup configured agent: {e}")
        
        # If no configured agent, use user's primary agent
        if not agent_name:
            try:
                agents = agixt.get_agents()
                if agents and len(agents) > 0:
                    agent_name = (
                        agents[0].get("name", "XT")
                        if isinstance(agents[0], dict)
                        else agents[0]
                    )
                else:
                    agent_name = "XT"
            except Exception as e:
                logger.warning(f"Could not get user's agents, using default: {e}")
                agent_name = "XT"

        # Handle admin commands (only for recognized users)
        if not use_owner_context:
            text_lower = text.lower()
            if text_lower.startswith("!list"):
                await self._handle_list_command(channel_id, thread_ts, agixt, agents)
                return
            elif text_lower.startswith("!select "):
                await self._handle_select_command(
                    user_id, channel_id, thread_ts, text, agixt
                )
                return
            elif text_lower.startswith("!clear"):
                await self._handle_clear_command(
                    user_id, channel_id, thread_ts, agixt, agent_name
                )
                return

        # Only apply user selection/team mode if no bot-level agent configured
        if not self.bot_agent_id and not use_owner_context:
            # Check for user's selected agent in this channel
            selection_key = (user_id, channel_id)
            if selection_key in self.user_agent_selection:
                agent_name = self.user_agent_selection[selection_key]

            # Check team mode
            if channel_id in self.team_channel_config:
                team_config = self.team_channel_config[channel_id]
                agent_name = team_config["agent_name"]
                admin_email = self._get_user_email_from_slack_id(
                    team_config["admin_user_id"]
                )
                if admin_email:
                    admin_jwt = impersonate_user(admin_email)
                    agixt = InternalClient(api_key=admin_jwt, user=admin_email)

        if not text:
            return

        # Send typing indicator
        try:
            # Slack doesn't have a direct typing indicator API like Discord
            # We can post a temporary message or just proceed
            pass
        except Exception:
            pass

        try:
            # Get channel info for context
            try:
                channel_info = self.web_client.conversations_info(channel=channel_id)
                channel_name = channel_info.get("channel", {}).get("name", channel_id)
            except Exception:
                channel_name = channel_id

            conversation_name = self._get_conversation_name(channel_id, channel_name)

            # Import AGiXT class
            from XT import AGiXT

            agixt_instance = AGiXT(
                user=user_email,
                agent_name=agent_name,
                api_key=agixt.headers.get("Authorization", ""),
                conversation_name=conversation_name,
            )

            # Get channel context
            context = await self._get_channel_context(channel_id, thread_ts, user_email)

            # Build message
            prompt_args = {
                "user_input": text,
                "context": context,
                "conversation_results": 0,
            }

            # Handle file attachments
            files = event.get("files", [])
            if files:
                file_urls = []
                for file_info in files:
                    file_url = file_info.get("url_private")
                    if file_url:
                        # Download file with auth
                        try:
                            import aiohttp

                            headers = {"Authorization": f"Bearer {self.bot_token}"}
                            async with aiohttp.ClientSession() as session:
                                async with session.get(
                                    file_url, headers=headers
                                ) as resp:
                                    if resp.status == 200:
                                        data = await resp.read()
                                        content_type = file_info.get(
                                            "mimetype", "application/octet-stream"
                                        )
                                        encoded = base64.b64encode(data).decode("utf-8")
                                        file_urls.append(
                                            f"data:{content_type};base64,{encoded}"
                                        )
                        except Exception as e:
                            logger.error(f"Error downloading Slack file: {e}")

                if file_urls:
                    prompt_args["file_urls"] = file_urls

            message_data = {
                "role": "user",
                "content": text,
                "prompt_name": "Think About It",
                "prompt_category": "Default",
                "context": context,
                "injected_memories": 0,
                "prompt_args": prompt_args,
            }

            # Create ChatCompletions prompt
            chat_prompt = ChatCompletions(
                model=agent_name,
                user=conversation_name,
                messages=[message_data],
                stream=True,
            )

            # Collect response
            full_response = ""
            async for chunk in agixt_instance.chat_completions_stream(prompt=chat_prompt):
                if chunk.startswith("data: "):
                    data = chunk[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        import json

                        chunk_data = json.loads(data)
                        if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                            delta = chunk_data["choices"][0].get("delta", {})
                            content_chunk = delta.get("content", "")
                            if content_chunk:
                                full_response += content_chunk
                    except json.JSONDecodeError:
                        pass

            reply = (
                full_response.strip()
                if full_response
                else "I couldn't generate a response."
            )

            # Split long messages
            if len(reply) > 4000:
                chunks = self._split_message(reply, 4000)
                for chunk in chunks:
                    self.web_client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=chunk,
                    )
            else:
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=reply,
                )

        except Exception as e:
            logger.error(f"Error handling Slack message for company {self.company_name}: {e}")
            try:
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"Sorry, I encountered an error: {str(e)}",
                )
            except Exception:
                pass

    async def _handle_list_command(self, channel_id, thread_ts, agixt, agents=None):
        """Handle the !list command."""
        try:
            if agents is None:
                agents = agixt.get_agents()

            if not agents:
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="You don't have any agents configured.",
                )
                return

            agent_list = []
            for i, agent in enumerate(agents, 1):
                name = agent.get("name", "Unknown") if isinstance(agent, dict) else agent
                agent_list.append(f"{i}. *{name}*")

            response = "*Your Available Agents:*\n" + "\n".join(agent_list)
            response += "\n\n_Use `!select <agent_name>` to switch agents._"

            self.web_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=response,
            )

        except Exception as e:
            logger.error(f"Error handling !list command: {e}")

    async def _handle_select_command(self, user_id, channel_id, thread_ts, text, agixt):
        """Handle the !select command."""
        try:
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="Usage: `!select <agent_name>`\nUse `!list` to see available agents.",
                )
                return

            requested_agent = parts[1].strip()
            agents = agixt.get_agents()

            if not agents:
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="You don't have any agents configured.",
                )
                return

            matched_agent = None
            for agent in agents:
                name = agent.get("name", "") if isinstance(agent, dict) else agent
                if name.lower() == requested_agent.lower():
                    matched_agent = name
                    break

            if not matched_agent:
                available = [
                    agent.get("name", agent) if isinstance(agent, dict) else agent
                    for agent in agents
                ]
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"Agent `{requested_agent}` not found.\n\n*Available agents:* {', '.join(available)}",
                )
                return

            selection_key = (user_id, channel_id)
            self.user_agent_selection[selection_key] = matched_agent

            self.web_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"✅ Switched to *{matched_agent}* for this channel.",
            )

        except Exception as e:
            logger.error(f"Error handling !select command: {e}")

    async def _handle_clear_command(
        self, user_id, channel_id, thread_ts, agixt, current_agent_name
    ):
        """Handle the !clear command."""
        try:
            selection_key = (user_id, channel_id)
            if selection_key in self.user_agent_selection:
                current_agent_name = self.user_agent_selection[selection_key]

            self.web_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"✅ Conversation cleared. Starting fresh with *{current_agent_name}*!",
            )

        except Exception as e:
            logger.error(f"Error handling !clear command: {e}")

    async def _get_channel_context(
        self, channel_id: str, thread_ts: str = None, user_email: str = None
    ) -> str:
        """Get recent conversation history for context."""
        try:
            messages = []

            # Get thread replies if in a thread
            if thread_ts:
                result = self.web_client.conversations_replies(
                    channel=channel_id, ts=thread_ts, limit=50
                )
                messages = result.get("messages", [])
            else:
                result = self.web_client.conversations_history(
                    channel=channel_id, limit=50
                )
                messages = result.get("messages", [])

            if not messages:
                return "**SLACK CHANNEL CONTEXT**: No conversation history found."

            # Get user info for display names
            user_cache = {}

            def get_user_name(user_id):
                if user_id not in user_cache:
                    try:
                        user_info = self.web_client.users_info(user=user_id)
                        user = user_info.get("user", {})
                        user_cache[user_id] = (
                            user.get("real_name")
                            or user.get("name")
                            or user_id
                        )
                    except Exception:
                        user_cache[user_id] = user_id
                return user_cache[user_id]

            formatted_messages = []
            for msg in reversed(messages):
                user_id = msg.get("user", "Unknown")
                user_name = get_user_name(user_id) if user_id != "Unknown" else "Bot"
                text = msg.get("text", "[No text]")
                ts = msg.get("ts", "")

                # Convert timestamp
                try:
                    dt = datetime.fromtimestamp(float(ts))
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    timestamp = ts

                formatted_messages.append(f"[{timestamp}] {user_name}: {text}")

            header = f"""**SLACK CHANNEL CONTEXT**
This is the real-time conversation happening in the Slack channel.
Total messages: {len(messages)}

**MESSAGE HISTORY:**
---"""

            return f"{header}\n" + "\n".join(formatted_messages)

        except Exception as e:
            logger.error(f"Error getting Slack channel context: {e}")
            return "**SLACK CHANNEL CONTEXT**: Error retrieving conversation history."

    def _split_message(self, text: str, max_length: int = 4000) -> list:
        """Split a message into chunks."""
        if len(text) <= max_length:
            return [text]

        chunks = []
        remaining = text

        while len(remaining) > max_length:
            split_point = remaining.rfind("\n", 0, max_length)
            if split_point == -1 or split_point < max_length * 0.3:
                split_point = remaining.rfind(" ", 0, max_length)
            if split_point == -1:
                split_point = max_length

            chunks.append(remaining[:split_point].rstrip())
            remaining = remaining[split_point:].lstrip()

        if remaining:
            chunks.append(remaining)

        return chunks

    def _handle_socket_message(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming socket mode messages."""
        if req.type == "events_api":
            # Acknowledge the event
            response = SocketModeResponse(envelope_id=req.envelope_id)
            client.send_socket_mode_response(response)

            event = req.payload.get("event", {})
            event_type = event.get("type")

            if event_type == "message" or event_type == "app_mention":
                # Run message handler in asyncio
                asyncio.create_task(self._handle_message(event))

    async def start(self):
        """Start the Slack bot."""
        try:
            # Get bot user ID
            auth_response = self.web_client.auth_test()
            self._bot_user_id = auth_response.get("user_id")
            self._workspace_name = auth_response.get("team", "")

            # Refresh user cache
            self._refresh_slack_user_cache()

            # Initialize socket mode client
            self.socket_client = SocketModeClient(
                app_token=self.app_token,
                web_client=self.web_client,
            )

            # Register message handler
            self.socket_client.socket_mode_request_listeners.append(
                self._handle_socket_message
            )

            # Connect
            self.socket_client.connect()

            self._is_ready = True
            self._started_at = datetime.now()

            logger.info(
                f"Slack bot for company {self.company_name} ({self.company_id}) "
                f"connected to workspace {self._workspace_name}"
            )

            # Keep alive
            while self._is_ready:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Slack bot for company {self.company_name} failed: {e}")
            raise

    async def stop(self):
        """Stop the Slack bot gracefully."""
        self._is_ready = False
        if self.socket_client:
            try:
                self.socket_client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting Slack socket: {e}")

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def workspace_name(self) -> str:
        return self._workspace_name


class SlackBotManager:
    """
    Manages Slack bots for multiple companies.
    """

    SERVER_BOT_ID = "server"

    def __init__(self):
        self.bots: Dict[str, CompanySlackBot] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def get_server_bot_tokens(self) -> tuple:
        """Get the server-level Slack bot and app tokens."""
        bot_token = getenv("SLACK_BOT_TOKEN")
        app_token = getenv("SLACK_APP_TOKEN")

        if bot_token and app_token:
            return bot_token, app_token

        # Check database
        try:
            from DB import ServerExtensionSetting
            from endpoints.ServerConfig import decrypt_config_value

            with get_session() as db:
                bot_setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == "slack",
                        ServerExtensionSetting.setting_key == "SLACK_BOT_TOKEN",
                    )
                    .first()
                )
                app_setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == "slack",
                        ServerExtensionSetting.setting_key == "SLACK_APP_TOKEN",
                    )
                    .first()
                )

                if bot_setting and bot_setting.setting_value:
                    if bot_setting.is_sensitive:
                        bot_token = decrypt_config_value(bot_setting.setting_value)
                    else:
                        bot_token = bot_setting.setting_value

                if app_setting and app_setting.setting_value:
                    if app_setting.is_sensitive:
                        app_token = decrypt_config_value(app_setting.setting_value)
                    else:
                        app_token = app_setting.setting_value

        except Exception as e:
            logger.error(f"Error getting server Slack tokens from database: {e}")

        return bot_token, app_token

    def get_company_bot_config(self) -> Dict[str, Dict[str, str]]:
        """Get Slack bot configuration for all companies."""
        configs = {}

        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(CompanyExtensionSetting.extension_name == "slack")
                .filter(
                    CompanyExtensionSetting.setting_key.in_(
                        [
                            "slack_bot_token",
                            "slack_app_token",
                            "slack_bot_enabled",
                            "slack_bot_agent_id",
                            "slack_bot_permission_mode",
                            "slack_bot_owner_id",
                        ]
                    )
                )
                .all()
            )

            for setting in settings:
                company_id = str(setting.company_id)
                if company_id not in configs:
                    company = (
                        db.query(Company)
                        .filter(Company.id == setting.company_id)
                        .first()
                    )
                    configs[company_id] = {
                        "name": company.name if company else "Unknown",
                        "bot_token": None,
                        "app_token": None,
                        "enabled": "false",
                        "agent_id": None,
                        "permission_mode": "recognized_users",
                        "owner_id": None,
                    }

                value = setting.setting_value
                if setting.is_sensitive and value:
                    from endpoints.ServerConfig import decrypt_config_value

                    value = decrypt_config_value(value)

                if setting.setting_key == "slack_bot_token":
                    configs[company_id]["bot_token"] = value
                elif setting.setting_key == "slack_app_token":
                    configs[company_id]["app_token"] = value
                elif setting.setting_key == "slack_bot_enabled":
                    configs[company_id]["enabled"] = value
                elif setting.setting_key == "slack_bot_agent_id":
                    configs[company_id]["agent_id"] = value
                elif setting.setting_key == "slack_bot_permission_mode":
                    configs[company_id]["permission_mode"] = value or "recognized_users"
                elif setting.setting_key == "slack_bot_owner_id":
                    configs[company_id]["owner_id"] = value

        return configs

    async def start_bot_for_company(
        self,
        company_id: str,
        company_name: str,
        bot_token: str,
        app_token: str,
        agent_id: str = None,
        permission_mode: str = "recognized_users",
        owner_id: str = None,
    ) -> bool:
        """Start a Slack bot for a specific company."""
        if company_id in self.bots and company_id in self._tasks:
            logger.warning(f"Slack bot for company {company_name} is already running")
            return False

        try:
            bot = CompanySlackBot(
                company_id=company_id,
                company_name=company_name,
                bot_token=bot_token,
                app_token=app_token,
                bot_agent_id=agent_id,
                bot_permission_mode=permission_mode,
                bot_owner_id=owner_id,
            )
            self.bots[company_id] = bot

            task = asyncio.create_task(bot.start())
            self._tasks[company_id] = task

            task.add_done_callback(
                lambda t: self._handle_bot_error(company_id, company_name, t)
            )

            logger.info(
                f"Started Slack bot for company {company_name} ({company_id}) "
                f"[agent_id={agent_id}, permission_mode={permission_mode}]"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start Slack bot for company {company_name}: {e}")
            return False

    def _handle_bot_error(self, company_id: str, company_name: str, task: asyncio.Task):
        """Handle bot task completion/failure."""
        try:
            exc = task.exception()
            if exc:
                logger.error(f"Slack bot for company {company_name} crashed: {exc}")
        except asyncio.CancelledError:
            logger.info(f"Slack bot for company {company_name} was cancelled")
        except Exception as e:
            logger.error(f"Error checking Slack bot task for {company_name}: {e}")

        if company_id in self.bots:
            del self.bots[company_id]
        if company_id in self._tasks:
            del self._tasks[company_id]

    async def stop_bot_for_company(self, company_id: str) -> bool:
        """Stop a Slack bot for a specific company."""
        if company_id not in self.bots:
            logger.warning(f"No Slack bot running for company {company_id}")
            return False

        try:
            bot = self.bots[company_id]
            await bot.stop()

            if company_id in self._tasks:
                task = self._tasks[company_id]
                if not task.done():
                    task.cancel()

            del self.bots[company_id]
            if company_id in self._tasks:
                del self._tasks[company_id]

            logger.info(f"Stopped Slack bot for company {company_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop Slack bot for company {company_id}: {e}")
            return False

    async def sync_bots(self):
        """Sync running bots with database configuration."""
        server_bot_token, server_app_token = self.get_server_bot_tokens()
        company_configs = self.get_company_bot_config()

        company_bots_configured = any(
            config.get("enabled", "").lower() == "true"
            and config.get("bot_token")
            and config.get("app_token")
            for config in company_configs.values()
        )

        if company_bots_configured:
            if self.SERVER_BOT_ID in self.bots:
                logger.info("Stopping server-level Slack bot in favor of company-specific bots")
                await self.stop_bot_for_company(self.SERVER_BOT_ID)

            companies_to_stop = []
            for company_id in list(self.bots.keys()):
                if company_id == self.SERVER_BOT_ID:
                    continue
                config = company_configs.get(company_id)
                if not config or config.get("enabled", "").lower() != "true":
                    companies_to_stop.append(company_id)

            for company_id in companies_to_stop:
                await self.stop_bot_for_company(company_id)

            for company_id, config in company_configs.items():
                if (
                    config.get("enabled", "").lower() == "true"
                    and config.get("bot_token")
                    and config.get("app_token")
                    and company_id not in self.bots
                ):
                    await self.start_bot_for_company(
                        company_id=company_id,
                        company_name=config["name"],
                        bot_token=config["bot_token"],
                        app_token=config["app_token"],
                        agent_id=config.get("agent_id"),
                        permission_mode=config.get("permission_mode", "recognized_users"),
                        owner_id=config.get("owner_id"),
                    )

        elif server_bot_token and server_app_token:
            for company_id in list(self.bots.keys()):
                if company_id != self.SERVER_BOT_ID:
                    await self.stop_bot_for_company(company_id)

            if self.SERVER_BOT_ID not in self.bots:
                logger.info("Starting server-level Slack bot")
                await self.start_bot_for_company(
                    self.SERVER_BOT_ID,
                    "AGiXT Server Bot",
                    server_bot_token,
                    server_app_token,
                )
        else:
            for company_id in list(self.bots.keys()):
                await self.stop_bot_for_company(company_id)

            if not self.bots:
                logger.debug("No Slack bot tokens configured")

    async def _monitor_loop(self):
        """Monitor loop that syncs bots periodically."""
        while self._running:
            try:
                await self.sync_bots()
            except Exception as e:
                logger.error(f"Error in Slack bot monitor loop: {e}")

            await asyncio.sleep(60)

    async def start(self):
        """Start the Slack bot manager."""
        self._running = True
        logger.info("Starting Slack Bot Manager...")

        await self.sync_bots()

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Slack Bot Manager started")

    async def stop(self):
        """Stop all bots and the manager."""
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

        for company_id in list(self.bots.keys()):
            await self.stop_bot_for_company(company_id)

        logger.info("Slack Bot Manager stopped")

    def get_status(self) -> Dict[str, SlackBotStatus]:
        """Get status of all running bots."""
        statuses = {}
        for company_id, bot in self.bots.items():
            statuses[company_id] = SlackBotStatus(
                company_id=company_id,
                company_name=bot.company_name,
                started_at=bot.started_at,
                is_running=bot.is_ready,
                workspace_name=bot.workspace_name,
            )
        return statuses

    def get_bot_status(self, company_id: str) -> Optional[SlackBotStatus]:
        """Get status of a specific company's bot."""
        bot = self.bots.get(company_id)
        if not bot:
            return None
        return SlackBotStatus(
            company_id=company_id,
            company_name=bot.company_name,
            started_at=bot.started_at,
            is_running=bot.is_ready,
            workspace_name=bot.workspace_name,
        )


# Global instance
_manager: Optional[SlackBotManager] = None


def get_slack_bot_manager() -> Optional[SlackBotManager]:
    """Get the global Slack bot manager instance."""
    return _manager


async def start_slack_bot_manager():
    """Start the global Slack bot manager."""
    global _manager

    if not SLACK_AVAILABLE:
        logger.warning("Slack bot manager cannot start - slack-sdk library not installed")
        return None

    if _manager is None:
        _manager = SlackBotManager()
    await _manager.start()
    return _manager


async def stop_slack_bot_manager():
    """Stop the global Slack bot manager."""
    global _manager
    if _manager:
        await _manager.stop()
        _manager = None
