"""
Microsoft Teams Bot Manager for AGiXT

This module manages Microsoft Teams bots for multiple companies. Each company can have
its own Teams bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Monitors bot health and restarts failed bots
- Handles graceful shutdown of all bots
- Provides APIs for querying bot status

Teams Bot Architecture:
- Uses Microsoft Bot Framework for message handling
- Supports Azure Bot Service for cloud deployment
- Handles @mentions and direct messages
- Integrates with AGiXT for AI-powered responses
"""

import asyncio
import logging
import sys
import os
import json
import base64
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime

# Check for Bot Framework library availability
BOT_FRAMEWORK_AVAILABLE = False
botbuilder = None

try:
    from botbuilder.core import (
        BotFrameworkAdapter,
        BotFrameworkAdapterSettings,
        TurnContext,
        ActivityHandler,
        MessageFactory,
    )
    from botbuilder.schema import Activity, ActivityTypes, ChannelAccount
    from aiohttp import web

    BOT_FRAMEWORK_AVAILABLE = True
    logging.info("Successfully loaded Microsoft Bot Framework libraries")
except ImportError as e:
    logging.warning(f"Microsoft Bot Framework library not installed: {e}")
except Exception as e:
    logging.warning(f"Failed to load Bot Framework libraries: {e}")

from DB import get_session, CompanyExtensionSetting, Company
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions

logger = logging.getLogger(__name__)


def _get_teams_user_ids(company_id=None):
    """Wrapper to import get_teams_user_ids from our extension."""
    from extensions.teams import get_teams_user_ids

    return get_teams_user_ids(company_id)


@dataclass
class TeamsBotStatus:
    """Status information for a company's Teams bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    tenant_count: int = 0


class CompanyTeamsBot(ActivityHandler):
    """
    A Teams bot instance for a specific company.
    Handles user impersonation based on Teams user ID mapping.
    
    This bot handles:
    - @mentions in channels
    - Direct messages
    - File attachments (via Microsoft Graph API)
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        app_id: str,
        app_password: str,
    ):
        super().__init__()
        self.company_id = company_id
        self.company_name = company_name
        self.app_id = app_id
        self.app_password = app_password

        # Initialize Bot Framework adapter
        settings = BotFrameworkAdapterSettings(
            app_id=app_id,
            app_password=app_password,
        )
        self.adapter = BotFrameworkAdapter(settings)
        
        # Error handler
        self.adapter.on_turn_error = self._on_error

        # Cache for Teams user ID -> email mapping
        self.teams_user_cache: Dict[str, str] = {}
        self._is_ready = False
        self._started_at: Optional[datetime] = None
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._port: int = 3978  # Default Bot Framework port

    async def _on_error(self, context: TurnContext, error: Exception):
        """Handle errors during bot turns."""
        logger.error(f"Teams bot error: {error}")
        await context.send_activity(
            f"Sorry, I encountered an error processing your request."
        )

    def _refresh_teams_user_cache(self):
        """Refresh the Teams user ID -> email mapping cache."""
        try:
            if self.company_id == "server":
                self.teams_user_cache = _get_teams_user_ids(company_id=None)
            else:
                self.teams_user_cache = _get_teams_user_ids(self.company_id)
            logger.debug(
                f"Refreshed Teams user cache for {self.company_name}: "
                f"{len(self.teams_user_cache)} users"
            )
        except Exception as e:
            logger.error(f"Failed to refresh Teams user cache: {e}")

    def _get_user_email_from_teams_id(self, teams_id: str) -> Optional[str]:
        """Get user email from Teams ID, refreshing cache if needed."""
        if teams_id not in self.teams_user_cache:
            self._refresh_teams_user_cache()
        return self.teams_user_cache.get(teams_id)

    def _get_conversation_name(self, activity: Activity) -> str:
        """Generate a conversation name based on the Teams context."""
        conversation = activity.conversation
        
        if conversation.conversation_type == "personal":
            user_id = activity.from_property.id if activity.from_property else "unknown"
            return f"Teams-DM-{user_id}"
        elif conversation.conversation_type == "groupChat":
            return f"Teams-Group-{conversation.id[:20]}"
        else:
            # Channel conversation
            channel_name = getattr(activity, "channel_id", "unknown")
            team_name = conversation.name or "Team"
            return f"Teams-{team_name}-{channel_name}"

    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming message activities."""
        activity = turn_context.activity
        user_id = activity.from_property.id if activity.from_property else None
        text = activity.text or ""
        
        # Remove bot mention from text if present
        if activity.entities:
            for entity in activity.entities:
                if entity.type == "mention":
                    mentioned = getattr(entity, "mentioned", None)
                    if mentioned and hasattr(mentioned, "id"):
                        if mentioned.id == self.app_id:
                            # Remove the mention text
                            mention_text = getattr(entity, "text", "")
                            text = text.replace(mention_text, "").strip()

        if not text and not activity.attachments:
            return

        # Get user email from mapping
        user_email = self._get_user_email_from_teams_id(user_id)

        if not user_email:
            # Try to get email from activity
            user_email = getattr(activity.from_property, "email", None)
            
        if not user_email:
            await turn_context.send_activity(
                "Please connect your Microsoft Teams account to AGiXT to use this bot. "
                "Visit your AGiXT settings to link your account."
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
        conversation_name = self._get_conversation_name(activity)

        try:
            # Show typing indicator
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))

            # Get context from conversation history
            context = await self._get_conversation_context(turn_context)

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
            if activity.attachments:
                for attachment in activity.attachments:
                    file_data = await self._download_attachment(attachment)
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

            # Send response (Teams has ~28KB message limit)
            if len(reply) > 25000:
                chunks = [reply[i : i + 25000] for i in range(0, len(reply), 25000)]
                for chunk in chunks:
                    await turn_context.send_activity(chunk)
            else:
                await turn_context.send_activity(reply)

        except Exception as e:
            logger.error(f"Error processing Teams message: {e}")
            await turn_context.send_activity(
                f"Sorry, I encountered an error: {str(e)}"
            )

    async def _get_conversation_context(self, turn_context: TurnContext) -> str:
        """Get recent conversation context."""
        # Note: Getting conversation history in Teams requires Graph API permissions
        # For now, we return empty context - conversation history is tracked by AGiXT
        return ""

    async def _download_attachment(self, attachment) -> Optional[str]:
        """Download a Teams attachment and return base64 encoded data."""
        try:
            import aiohttp

            content_url = attachment.content_url
            if not content_url:
                return None

            # For Teams attachments, we may need to use Graph API
            async with aiohttp.ClientSession() as session:
                async with session.get(content_url) as response:
                    if response.status == 200:
                        data = await response.read()
                        encoded = base64.b64encode(data).decode("utf-8")
                        content_type = attachment.content_type or "application/octet-stream"
                        return f"data:{content_type};base64,{encoded}"
            return None
        except Exception as e:
            logger.error(f"Error downloading Teams attachment: {e}")
            return None

    async def on_members_added_activity(
        self, members_added: List[ChannelAccount], turn_context: TurnContext
    ):
        """Handle when members are added to a conversation."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    f"Hello! I'm the {self.company_name} AI Assistant. "
                    f"You can @mention me or send me a direct message to get started."
                )

    async def _process_request(self, request: web.Request) -> web.Response:
        """Process incoming HTTP request from Bot Framework."""
        if "application/json" in request.headers.get("Content-Type", ""):
            body = await request.json()
        else:
            body = await request.text()

        activity = Activity().deserialize(body)
        auth_header = request.headers.get("Authorization", "")

        try:
            response = await self.adapter.process_activity(
                activity, auth_header, self.on_turn
            )
            if response:
                return web.json_response(data=response.body, status=response.status)
            return web.Response(status=201)
        except Exception as e:
            logger.error(f"Error processing Teams activity: {e}")
            return web.Response(status=500, text=str(e))

    async def start(self, port: int = None):
        """Start the Teams bot HTTP endpoint."""
        try:
            self._port = port or int(getenv("TEAMS_BOT_PORT", "3978"))
            
            # Create web application
            self._app = web.Application()
            self._app.router.add_post("/api/messages", self._process_request)
            
            # Refresh user cache
            self._refresh_teams_user_cache()
            logger.info(f"Loaded {len(self.teams_user_cache)} Teams user mappings")

            # Start the server
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
            await self._site.start()

            self._is_ready = True
            self._started_at = datetime.now()

            logger.info(
                f"Teams bot for company {self.company_name} ({self.company_id}) "
                f"started on port {self._port}"
            )

        except Exception as e:
            logger.error(f"Teams bot for company {self.company_name} failed: {e}")
            self._is_ready = False
            raise

    async def stop(self):
        """Stop the Teams bot gracefully."""
        if self._runner:
            await self._runner.cleanup()
        self._is_ready = False
        logger.info(f"Teams bot for company {self.company_name} stopped")

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at


class TeamsBotManager:
    """
    Manages Teams bots for multiple companies.

    This class handles:
    - Starting/stopping bots based on company settings
    - Supporting server-level bot credentials as default for all companies
    - Monitoring bot health
    - Providing status information
    - Graceful shutdown of all bots

    Bot Credential Precedence:
    1. Company-level TEAMS_APP_ID + TEAMS_APP_PASSWORD in CompanyExtensionSetting (if enabled)
    2. Server-level credentials from environment variables (shared by all companies)
    """

    SERVER_BOT_ID = "server"

    def __init__(self):
        self.bots: Dict[str, CompanyTeamsBot] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._base_port = int(getenv("TEAMS_BOT_BASE_PORT", "3978"))

    def get_server_bot_credentials(self) -> Dict[str, str]:
        """Get the server-level Teams bot credentials from environment or ServerExtensionSetting."""
        credentials = {
            "app_id": getenv("TEAMS_APP_ID") or getenv("TEAMS_CLIENT_ID"),
            "app_password": getenv("TEAMS_APP_PASSWORD") or getenv("TEAMS_CLIENT_SECRET"),
        }

        if credentials["app_id"] and credentials["app_password"]:
            return credentials

        # Try database
        try:
            from DB import ServerExtensionSetting
            from endpoints.ServerConfig import decrypt_config_value

            with get_session() as db:
                for key in ["TEAMS_APP_ID", "TEAMS_APP_PASSWORD"]:
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "teams",
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
                        if key == "TEAMS_APP_ID":
                            credentials["app_id"] = value
                        elif key == "TEAMS_APP_PASSWORD":
                            credentials["app_password"] = value
        except Exception as e:
            logger.error(f"Error getting server bot credentials from database: {e}")

        return credentials

    def get_company_bot_config(self) -> Dict[str, Dict[str, str]]:
        """Get Teams bot configuration for all companies from the database."""
        configs = {}

        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(CompanyExtensionSetting.extension_name == "teams")
                .filter(
                    CompanyExtensionSetting.setting_key.in_(
                        [
                            "TEAMS_APP_ID",
                            "TEAMS_APP_PASSWORD",
                            "TEAMS_BOT_ENABLED",
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
                        "app_id": None,
                        "app_password": None,
                        "enabled": "false",
                    }

                value = setting.setting_value
                if setting.is_sensitive and value:
                    from endpoints.ServerConfig import decrypt_config_value

                    value = decrypt_config_value(value)

                if setting.setting_key == "TEAMS_APP_ID":
                    configs[company_id]["app_id"] = value
                elif setting.setting_key == "TEAMS_APP_PASSWORD":
                    configs[company_id]["app_password"] = value
                elif setting.setting_key == "TEAMS_BOT_ENABLED":
                    configs[company_id]["enabled"] = value

        return configs

    async def start_bot_for_company(
        self,
        company_id: str,
        company_name: str,
        app_id: str,
        app_password: str,
        port: int = None,
    ) -> bool:
        """Start a Teams bot for a specific company."""
        if company_id in self.bots and company_id in self._tasks:
            logger.warning(f"Teams bot for company {company_name} is already running")
            return False

        try:
            bot = CompanyTeamsBot(company_id, company_name, app_id, app_password)
            self.bots[company_id] = bot

            # Assign unique port for each company bot
            if port is None:
                port = self._base_port + len(self.bots) - 1

            task = asyncio.create_task(bot.start(port=port))
            self._tasks[company_id] = task

            task.add_done_callback(
                lambda t: self._handle_bot_error(company_id, company_name, t)
            )

            logger.info(f"Started Teams bot for company {company_name} ({company_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to start Teams bot for company {company_name}: {e}")
            return False

    def _handle_bot_error(self, company_id: str, company_name: str, task: asyncio.Task):
        """Handle bot task completion/failure."""
        try:
            exc = task.exception()
            if exc:
                logger.error(f"Teams bot for company {company_name} crashed: {exc}")
        except asyncio.CancelledError:
            logger.info(f"Teams bot for company {company_name} was cancelled")
        except Exception as e:
            logger.error(f"Error checking Teams bot task for {company_name}: {e}")

        if company_id in self.bots:
            del self.bots[company_id]
        if company_id in self._tasks:
            del self._tasks[company_id]

    async def stop_bot_for_company(self, company_id: str) -> bool:
        """Stop a Teams bot for a specific company."""
        if company_id not in self.bots:
            logger.warning(f"No Teams bot running for company {company_id}")
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

            logger.info(f"Stopped Teams bot for company {company_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop Teams bot for company {company_id}: {e}")
            return False

    async def sync_bots(self):
        """Sync running bots with database configuration."""
        server_credentials = self.get_server_bot_credentials()
        company_configs = self.get_company_bot_config()

        company_bots_configured = any(
            config.get("enabled", "").lower() == "true"
            and config.get("app_id")
            and config.get("app_password")
            for config in company_configs.values()
        )

        if company_bots_configured:
            if self.SERVER_BOT_ID in self.bots:
                logger.info(
                    "Stopping server-level Teams bot in favor of company-specific bots"
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
                    and config.get("app_id")
                    and config.get("app_password")
                    and company_id not in self.bots
                ):
                    await self.start_bot_for_company(
                        company_id,
                        config["name"],
                        config["app_id"],
                        config["app_password"],
                    )

        elif server_credentials.get("app_id") and server_credentials.get("app_password"):
            for company_id in list(self.bots.keys()):
                if company_id != self.SERVER_BOT_ID:
                    await self.stop_bot_for_company(company_id)

            if self.SERVER_BOT_ID not in self.bots:
                logger.info(
                    "Starting server-level Teams bot (shared across all companies)"
                )
                await self.start_bot_for_company(
                    self.SERVER_BOT_ID,
                    "AGiXT Server Bot",
                    server_credentials["app_id"],
                    server_credentials["app_password"],
                    port=self._base_port,
                )
        else:
            for company_id in list(self.bots.keys()):
                await self.stop_bot_for_company(company_id)

            if not self.bots:
                logger.debug("No Teams bot credentials configured (server or company level)")

    async def _monitor_loop(self):
        """Monitor loop that syncs bots periodically."""
        while self._running:
            try:
                await self.sync_bots()
            except Exception as e:
                logger.error(f"Error in Teams bot monitor loop: {e}")
            await asyncio.sleep(60)

    async def start(self):
        """Start the Teams bot manager."""
        if not BOT_FRAMEWORK_AVAILABLE:
            logger.warning(
                "Microsoft Bot Framework library not available. "
                "Install with: pip install botbuilder-core aiohttp"
            )
            return

        self._running = True
        logger.info("Starting Teams Bot Manager...")

        await self.sync_bots()

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Teams Bot Manager started")

    async def stop(self):
        """Stop all Teams bots and the manager."""
        logger.info("Stopping Teams Bot Manager...")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        for company_id in list(self.bots.keys()):
            await self.stop_bot_for_company(company_id)

        logger.info("Teams Bot Manager stopped")

    def get_bot_statuses(self) -> Dict[str, TeamsBotStatus]:
        """Get status information for all bots."""
        statuses = {}
        for company_id, bot in self.bots.items():
            statuses[company_id] = TeamsBotStatus(
                company_id=company_id,
                company_name=bot.company_name,
                started_at=bot.started_at,
                is_running=bot.is_ready,
            )
        return statuses


# Singleton instance
_teams_bot_manager: Optional[TeamsBotManager] = None


def get_teams_bot_manager() -> TeamsBotManager:
    """Get or create the singleton TeamsBotManager instance."""
    global _teams_bot_manager
    if _teams_bot_manager is None:
        _teams_bot_manager = TeamsBotManager()
    return _teams_bot_manager


async def start_teams_bot_manager():
    """Start the Teams bot manager."""
    manager = get_teams_bot_manager()
    await manager.start()


async def stop_teams_bot_manager():
    """Stop the Teams bot manager."""
    global _teams_bot_manager
    if _teams_bot_manager:
        await _teams_bot_manager.stop()
        _teams_bot_manager = None


if __name__ == "__main__":
    # Run the bot manager standalone
    async def main():
        manager = get_teams_bot_manager()
        try:
            await manager.start()
            # Keep running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await manager.stop()

    asyncio.run(main())
