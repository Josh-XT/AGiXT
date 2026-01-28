"""
Slack Bot Manager for AGiXT

This module manages Slack bots for multiple companies. Each company can have
its own Slack bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Monitors bot health and restarts failed bots
- Handles graceful shutdown of all bots
- Provides APIs for querying bot status

Slack Bot Architecture:
- Uses Slack Bolt framework for event handling
- Supports Socket Mode for secure communication without public endpoints
- Handles app_mention events and direct messages
- Integrates with AGiXT for AI-powered responses
"""

import asyncio
import logging
import sys
import os
import json
import base64
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# Check for Slack Bolt library availability
SLACK_AVAILABLE = False
slack_bolt = None
slack_sdk = None

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    slack_bolt = True
    slack_sdk = True
    SLACK_AVAILABLE = True
    logging.info("Successfully loaded Slack Bolt and SDK libraries")
except ImportError as e:
    logging.warning(f"Slack Bolt library not installed: {e}")
except Exception as e:
    logging.warning(f"Failed to load Slack libraries: {e}")

from DB import get_session, CompanyExtensionSetting, Company
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions

logger = logging.getLogger(__name__)


def _get_slack_user_ids(company_id=None):
    """Wrapper to import get_slack_user_ids from our extension."""
    from extensions.slack import get_slack_user_ids

    return get_slack_user_ids(company_id)


@dataclass
class SlackBotStatus:
    """Status information for a company's Slack bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    workspace_count: int = 0
    team_name: Optional[str] = None


class CompanySlackBot:
    """
    A Slack bot instance for a specific company.
    Handles user impersonation based on Slack user ID mapping.
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        bot_token: str,
        app_token: str,
        signing_secret: str = None,
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.bot_token = bot_token
        self.app_token = app_token
        self.signing_secret = signing_secret

        # Initialize Slack app
        self.app = App(
            token=bot_token,
            signing_secret=signing_secret if signing_secret else "not-used-in-socket-mode",
        )
        self.client = WebClient(token=bot_token)

        # Cache for Slack user ID -> email mapping
        self.slack_user_cache: Dict[str, str] = {}
        self._is_ready = False
        self._started_at: Optional[datetime] = None
        self._team_info: Dict = {}
        self._handler: Optional[AsyncSocketModeHandler] = None

        # Register event handlers
        self._setup_events()

    def _setup_events(self):
        """Set up Slack event handlers."""

        @self.app.event("app_mention")
        def handle_app_mention(event, say, client):
            """Handle when the bot is @mentioned."""
            asyncio.create_task(self._handle_mention(event, say, client))

        @self.app.event("message")
        def handle_message(event, say, client):
            """Handle direct messages and channel messages."""
            # Only handle DMs (channel type 'im')
            if event.get("channel_type") == "im":
                asyncio.create_task(self._handle_direct_message(event, say, client))

        @self.app.event("app_home_opened")
        def handle_app_home(event, client):
            """Handle when user opens the App Home tab."""
            user_id = event.get("user")
            try:
                client.views_publish(
                    user_id=user_id,
                    view={
                        "type": "home",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"*Welcome to {self.company_name} AI Assistant!* 🤖",
                                },
                            },
                            {"type": "divider"},
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "You can interact with me by:\n• *@mentioning me* in any channel\n• *Direct messaging* me here\n\nI'll use your connected AGiXT account to provide personalized responses.",
                                },
                            },
                        ],
                    },
                )
            except SlackApiError as e:
                logger.error(f"Error publishing App Home: {e}")

    def _refresh_slack_user_cache(self):
        """
        Refresh the Slack user ID -> email mapping cache.
        """
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

    def _get_conversation_name(self, event: Dict) -> str:
        """
        Generate a conversation name based on the Slack context.
        """
        channel = event.get("channel", "unknown")
        channel_type = event.get("channel_type", "channel")

        if channel_type == "im":
            user_id = event.get("user", "unknown")
            return f"Slack-DM-{user_id}"
        elif channel_type == "mpim":
            return f"Slack-Group-{channel}"
        else:
            # Try to get channel name
            try:
                result = self.client.conversations_info(channel=channel)
                channel_name = result.get("channel", {}).get("name", channel)
                team_name = self._team_info.get("name", "Workspace")
                return f"Slack-{team_name}-{channel_name}"
            except:
                return f"Slack-Channel-{channel}"

    async def _handle_mention(self, event: Dict, say, client):
        """Handle @mention events."""
        await self._process_message(event, say, client, is_mention=True)

    async def _handle_direct_message(self, event: Dict, say, client):
        """Handle direct message events."""
        # Skip bot's own messages
        if event.get("bot_id"):
            return
        await self._process_message(event, say, client, is_mention=False)

    async def _process_message(self, event: Dict, say, client, is_mention: bool = False):
        """Process incoming Slack messages and generate AI responses."""
        user_id = event.get("user")
        channel = event.get("channel")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        # Remove bot mention from text if present
        if is_mention:
            # Remove <@BOT_ID> mentions from text
            import re

            text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        if not text and not event.get("files"):
            return

        # Get user email from mapping
        user_email = self._get_user_email_from_slack_id(user_id)

        if not user_email:
            # User hasn't connected their Slack account
            await say(
                text="Please connect your Slack account to AGiXT to use this bot. "
                "Visit your AGiXT settings to link your account.",
                thread_ts=thread_ts,
            )
            return

        # Get JWT for impersonation
        user_jwt = impersonate_user(user_email)
        agixt = InternalClient(api_key=user_jwt, user=user_email)

        # Get user's primary agent
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

        # Get conversation name
        conversation_name = self._get_conversation_name(event)

        try:
            # Get channel context (recent messages)
            context = await self._get_channel_context(channel, thread_ts)

            # Import AGiXT for chat
            from XT import AGiXT

            agixt_instance = AGiXT(
                user=user_email,
                agent_name=agent_name,
                api_key=agixt.headers.get("Authorization", ""),
                conversation_name=conversation_name,
            )

            # Handle file attachments
            file_urls = []
            if event.get("files"):
                for file in event["files"]:
                    file_data = await self._download_file(file, client)
                    if file_data:
                        file_urls.append(file_data)

            # Build message
            if file_urls:
                multimodal_content = [{"type": "text", "text": text}]
                for file_url in file_urls:
                    multimodal_content.append(
                        {"type": "file_url", "file_url": {"url": file_url}}
                    )
                message_data = {
                    "role": "user",
                    "content": multimodal_content,
                    "prompt_name": "Think About It",
                    "prompt_category": "Default",
                    "context": context,
                    "injected_memories": 0,
                }
            else:
                message_data = {
                    "role": "user",
                    "content": text,
                    "prompt_name": "Think About It",
                    "prompt_category": "Default",
                    "context": context,
                    "injected_memories": 0,
                }

            # Create chat prompt
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

            # Send response (Slack has 40k char limit per message)
            if len(reply) > 39000:
                chunks = [reply[i : i + 39000] for i in range(0, len(reply), 39000)]
                for chunk in chunks:
                    await say(text=chunk, thread_ts=thread_ts)
            else:
                await say(text=reply, thread_ts=thread_ts)

        except Exception as e:
            logger.error(f"Error processing Slack message: {e}")
            await say(
                text=f"Sorry, I encountered an error: {str(e)}", thread_ts=thread_ts
            )

    async def _get_channel_context(self, channel: str, thread_ts: str = None) -> str:
        """Get recent conversation context from the channel or thread."""
        try:
            messages = []

            if thread_ts:
                # Get thread replies
                result = self.client.conversations_replies(
                    channel=channel, ts=thread_ts, limit=20
                )
                messages = result.get("messages", [])[:-1]  # Exclude current message
            else:
                # Get recent channel messages
                result = self.client.conversations_history(channel=channel, limit=10)
                messages = result.get("messages", [])[1:]  # Exclude current message

            context_lines = []
            for msg in reversed(messages):
                user_id = msg.get("user", "Unknown")
                text = msg.get("text", "")
                context_lines.append(f"User {user_id}: {text}")

            return "\n".join(context_lines) if context_lines else ""

        except Exception as e:
            logger.warning(f"Could not get channel context: {e}")
            return ""

    async def _download_file(self, file: Dict, client) -> Optional[str]:
        """Download a Slack file and return base64 encoded data."""
        try:
            import aiohttp

            url = file.get("url_private_download") or file.get("url_private")
            if not url:
                return None

            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.bot_token}"}
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.read()
                        encoded = base64.b64encode(data).decode("utf-8")
                        mimetype = file.get("mimetype", "application/octet-stream")
                        return f"data:{mimetype};base64,{encoded}"
            return None
        except Exception as e:
            logger.error(f"Error downloading Slack file: {e}")
            return None

    async def start(self):
        """Start the Slack bot using Socket Mode."""
        try:
            # Get team info
            try:
                result = self.client.team_info()
                self._team_info = result.get("team", {})
                logger.info(
                    f"Connected to Slack workspace: {self._team_info.get('name')}"
                )
            except Exception as e:
                logger.warning(f"Could not get team info: {e}")

            # Refresh user cache
            self._refresh_slack_user_cache()
            logger.info(f"Loaded {len(self.slack_user_cache)} Slack user mappings")

            # Start Socket Mode handler
            self._handler = AsyncSocketModeHandler(self.app, self.app_token)
            self._is_ready = True
            self._started_at = datetime.now()

            logger.info(
                f"Slack bot for company {self.company_name} ({self.company_id}) started"
            )

            await self._handler.start_async()

        except Exception as e:
            logger.error(f"Slack bot for company {self.company_name} failed: {e}")
            self._is_ready = False
            raise

    async def stop(self):
        """Stop the Slack bot gracefully."""
        if self._handler:
            await self._handler.close_async()
        self._is_ready = False
        logger.info(f"Slack bot for company {self.company_name} stopped")

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def team_name(self) -> Optional[str]:
        return self._team_info.get("name")


class SlackBotManager:
    """
    Manages Slack bots for multiple companies.

    This class handles:
    - Starting/stopping bots based on company settings
    - Supporting server-level bot token as default for all companies
    - Monitoring bot health
    - Providing status information
    - Graceful shutdown of all bots

    Bot Token Precedence:
    1. Company-level SLACK_BOT_TOKEN + SLACK_APP_TOKEN in CompanyExtensionSetting (if enabled)
    2. Server-level tokens environment variables (shared by all companies)
    """

    SERVER_BOT_ID = "server"

    def __init__(self):
        self.bots: Dict[str, CompanySlackBot] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def get_server_bot_tokens(self) -> Dict[str, str]:
        """Get the server-level Slack bot tokens from environment or ServerExtensionSetting."""
        tokens = {
            "bot_token": getenv("SLACK_BOT_TOKEN"),
            "app_token": getenv("SLACK_APP_TOKEN"),
            "signing_secret": getenv("SLACK_SIGNING_SECRET"),
        }

        if tokens["bot_token"] and tokens["app_token"]:
            return tokens

        # Try database
        try:
            from DB import ServerExtensionSetting
            from endpoints.ServerConfig import decrypt_config_value

            with get_session() as db:
                for key in ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"]:
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "slack",
                            ServerExtensionSetting.setting_key == key,
                        )
                        .first()
                    )
                    if setting and setting.setting_value:
                        value = (
                            decrypt_config_value(setting.setting_value)
                            if setting.is_sensitive
                            else setting.setting_value
                        )
                        if key == "SLACK_BOT_TOKEN":
                            tokens["bot_token"] = value
                        elif key == "SLACK_APP_TOKEN":
                            tokens["app_token"] = value
                        elif key == "SLACK_SIGNING_SECRET":
                            tokens["signing_secret"] = value
        except Exception as e:
            logger.error(f"Error getting server bot tokens from database: {e}")

        return tokens

    def get_company_bot_config(self) -> Dict[str, Dict[str, str]]:
        """Get Slack bot configuration for all companies from the database."""
        configs = {}

        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(CompanyExtensionSetting.extension_name == "slack")
                .filter(
                    CompanyExtensionSetting.setting_key.in_(
                        [
                            "SLACK_BOT_TOKEN",
                            "SLACK_APP_TOKEN",
                            "SLACK_SIGNING_SECRET",
                            "SLACK_BOT_ENABLED",
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
                        "signing_secret": None,
                        "enabled": "false",
                    }

                value = setting.setting_value
                if setting.is_sensitive and value:
                    from endpoints.ServerConfig import decrypt_config_value

                    value = decrypt_config_value(value)

                if setting.setting_key == "SLACK_BOT_TOKEN":
                    configs[company_id]["bot_token"] = value
                elif setting.setting_key == "SLACK_APP_TOKEN":
                    configs[company_id]["app_token"] = value
                elif setting.setting_key == "SLACK_SIGNING_SECRET":
                    configs[company_id]["signing_secret"] = value
                elif setting.setting_key == "SLACK_BOT_ENABLED":
                    configs[company_id]["enabled"] = value

        return configs

    async def start_bot_for_company(
        self,
        company_id: str,
        company_name: str,
        bot_token: str,
        app_token: str,
        signing_secret: str = None,
    ) -> bool:
        """Start a Slack bot for a specific company."""
        if company_id in self.bots and company_id in self._tasks:
            logger.warning(f"Slack bot for company {company_name} is already running")
            return False

        try:
            bot = CompanySlackBot(
                company_id, company_name, bot_token, app_token, signing_secret
            )
            self.bots[company_id] = bot

            task = asyncio.create_task(bot.start())
            self._tasks[company_id] = task

            task.add_done_callback(
                lambda t: self._handle_bot_error(company_id, company_name, t)
            )

            logger.info(f"Started Slack bot for company {company_name} ({company_id})")
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
        server_tokens = self.get_server_bot_tokens()
        company_configs = self.get_company_bot_config()

        company_bots_configured = any(
            config.get("enabled", "").lower() == "true"
            and config.get("bot_token")
            and config.get("app_token")
            for config in company_configs.values()
        )

        if company_bots_configured:
            if self.SERVER_BOT_ID in self.bots:
                logger.info(
                    "Stopping server-level Slack bot in favor of company-specific bots"
                )
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
                        company_id,
                        config["name"],
                        config["bot_token"],
                        config["app_token"],
                        config.get("signing_secret"),
                    )

        elif server_tokens.get("bot_token") and server_tokens.get("app_token"):
            for company_id in list(self.bots.keys()):
                if company_id != self.SERVER_BOT_ID:
                    await self.stop_bot_for_company(company_id)

            if self.SERVER_BOT_ID not in self.bots:
                logger.info(
                    "Starting server-level Slack bot (shared across all companies)"
                )
                await self.start_bot_for_company(
                    self.SERVER_BOT_ID,
                    "AGiXT Server Bot",
                    server_tokens["bot_token"],
                    server_tokens["app_token"],
                    server_tokens.get("signing_secret"),
                )
        else:
            for company_id in list(self.bots.keys()):
                await self.stop_bot_for_company(company_id)

            if not self.bots:
                logger.debug("No Slack bot tokens configured (server or company level)")

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
        if not SLACK_AVAILABLE:
            logger.warning(
                "Slack Bolt library not available. "
                "Install with: pip install slack-bolt slack-sdk"
            )
            return

        self._running = True
        logger.info("Starting Slack Bot Manager...")

        await self.sync_bots()

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Slack Bot Manager started")

    async def stop(self):
        """Stop all Slack bots and the manager."""
        logger.info("Stopping Slack Bot Manager...")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        for company_id in list(self.bots.keys()):
            await self.stop_bot_for_company(company_id)

        logger.info("Slack Bot Manager stopped")

    def get_bot_statuses(self) -> Dict[str, SlackBotStatus]:
        """Get status information for all bots."""
        statuses = {}
        for company_id, bot in self.bots.items():
            statuses[company_id] = SlackBotStatus(
                company_id=company_id,
                company_name=bot.company_name,
                started_at=bot.started_at,
                is_running=bot.is_ready,
                team_name=bot.team_name,
            )
        return statuses


# Singleton instance
_slack_bot_manager: Optional[SlackBotManager] = None


def get_slack_bot_manager() -> SlackBotManager:
    """Get or create the singleton SlackBotManager instance."""
    global _slack_bot_manager
    if _slack_bot_manager is None:
        _slack_bot_manager = SlackBotManager()
    return _slack_bot_manager


async def start_slack_bot_manager():
    """Start the Slack bot manager."""
    manager = get_slack_bot_manager()
    await manager.start()


async def stop_slack_bot_manager():
    """Stop the Slack bot manager."""
    global _slack_bot_manager
    if _slack_bot_manager:
        await _slack_bot_manager.stop()
        _slack_bot_manager = None


if __name__ == "__main__":
    # Run the bot manager standalone
    async def main():
        manager = get_slack_bot_manager()
        try:
            await manager.start()
            # Keep running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await manager.stop()

    asyncio.run(main())
