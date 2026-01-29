"""
Microsoft Teams Bot Manager for AGiXT

This module manages Microsoft Teams bots for multiple companies. Each company can have
its own Teams bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Uses Microsoft Bot Framework for real-time messaging
- Handles graceful shutdown of all bots
- Provides APIs for querying bot status

Requires:
- botbuilder-core package
- MICROSOFT_APP_ID: Bot Framework app ID
- MICROSOFT_APP_PASSWORD: Bot Framework app password
- Microsoft Graph API permissions for Teams
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# Import Bot Framework SDK
TEAMS_BOT_AVAILABLE = False
botbuilder = None

try:
    from botbuilder.core import (
        BotFrameworkAdapter,
        BotFrameworkAdapterSettings,
        TurnContext,
    )
    from botbuilder.schema import Activity, ActivityTypes

    TEAMS_BOT_AVAILABLE = True
    logging.info("Successfully loaded botbuilder-core library")
except ImportError as e:
    logging.warning(f"botbuilder-core library not installed: {e}")
except Exception as e:
    logging.warning(f"Failed to load botbuilder-core library: {e}")

from DB import get_session, CompanyExtensionSetting, Company
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions


def _get_teams_user_ids(company_id=None):
    """Wrapper to import get_teams_user_ids from our extension."""
    from extensions.teams import get_teams_user_ids

    return get_teams_user_ids(company_id)


logger = logging.getLogger(__name__)


@dataclass
class TeamsBotStatus:
    """Status information for a company's Teams bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None


class CompanyTeamsBot:
    """
    A Teams bot instance for a specific company.
    Handles user impersonation based on Teams user ID mapping.

    Permission modes:
    - owner_only: Only the user who set up the bot can interact
    - recognized_users: Only users with linked AGiXT accounts can interact (default)
    - anyone: Anyone can interact with the bot
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        app_id: str,
        app_password: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.app_id = app_id
        self.app_password = app_password

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        # Parse allowlist - comma-separated Teams user IDs or emails
        self.bot_allowlist = set()
        if bot_allowlist:
            for item in bot_allowlist.split(","):
                item = item.strip().lower()  # Normalize to lowercase
                if item:
                    self.bot_allowlist.add(item)

        # Initialize Bot Framework adapter
        settings = BotFrameworkAdapterSettings(app_id, app_password)
        self.adapter = BotFrameworkAdapter(settings)

        # Cache for Teams user ID -> email mapping
        self.teams_user_cache: Dict[str, str] = {}
        # Cache for user's selected agent per conversation
        self.user_agent_selection: Dict[tuple, str] = {}
        # Team conversation configuration
        self.team_conversation_config: Dict[str, Dict[str, str]] = {}

        self._is_ready = False
        self._started_at: Optional[datetime] = None

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

    def _get_conversation_name(
        self, conversation_id: str, channel_name: str = None
    ) -> str:
        """Generate a conversation name based on the Teams context."""
        if channel_name:
            return f"Teams-{self.company_name}-{channel_name}"
        return f"Teams-{self.company_id}-{conversation_id[:20]}"

    async def handle_message(self, turn_context: TurnContext):
        """Handle incoming Teams messages."""
        import base64

        activity = turn_context.activity

        # Ignore non-message activities
        if activity.type != ActivityTypes.message:
            return

        user_id = activity.from_property.aad_object_id or activity.from_property.id
        conversation_id = activity.conversation.id
        text = activity.text or ""

        # Remove bot mention from text
        if activity.entities:
            for entity in activity.entities:
                if entity.type == "mention":
                    mention_text = entity.additional_properties.get("text", "")
                    text = text.replace(mention_text, "").strip()

        # Get user email from Teams ID mapping
        user_email = self._get_user_email_from_teams_id(user_id)
        use_owner_context = False

        # Apply permission mode checks
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
        elif self.bot_permission_mode == "allowlist":
            # Only Teams users in the allowlist can interact (check both ID and email)
            user_id_lower = user_id.lower() if user_id else ""
            user_email_lower = user_email.lower() if user_email else ""
            # Also check the UPN (User Principal Name) from activity
            upn = turn_context.activity.from_property.aad_object_id or ""
            upn_lower = upn.lower() if upn else ""
            
            if user_id_lower not in self.bot_allowlist and user_email_lower not in self.bot_allowlist and upn_lower not in self.bot_allowlist:
                logger.debug(f"Teams user {user_id} not in allowlist, ignoring")
                return
            # For allowlist mode, use owner context if no linked account
            if not user_email:
                use_owner_context = True
                if self.bot_owner_id:
                    try:
                        from DB import User
                        with get_session() as db:
                            owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                            if owner:
                                user_email = owner.email
                    except Exception as e:
                        logger.error(f"Error getting owner email for allowlist user: {e}")
                        return
                if not user_email:
                    logger.warning("Cannot handle allowlist interaction: no owner configured")
                    return
        elif self.bot_permission_mode == "recognized_users":
            # Default behavior - only users with linked accounts
            if not user_email:
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        text="Please connect your Microsoft Teams account to use this bot. Visit your profile settings to link your account.",
                    )
                )
                return
        elif self.bot_permission_mode == "anyone":
            # Anyone can interact - use owner context if not linked
            if not user_email:
                use_owner_context = True
                if self.bot_owner_id:
                    try:
                        from DB import User

                        with get_session() as db:
                            owner = (
                                db.query(User)
                                .filter(User.id == self.bot_owner_id)
                                .first()
                            )
                            if owner:
                                user_email = owner.email
                    except Exception as e:
                        logger.error(f"Error getting owner email: {e}")
                        return
                if not user_email:
                    logger.warning(
                        "Cannot handle anonymous interaction: no owner configured"
                    )
                    return
        else:
            # Unknown permission mode, default to recognized_users behavior
            if not user_email:
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        text="Please connect your Microsoft Teams account to use this bot. Visit your profile settings to link your account.",
                    )
                )
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
                    if isinstance(agent, dict) and str(agent.get("id")) == str(
                        self.bot_agent_id
                    ):
                        agent_name = agent.get("name", "XT")
                        break
                if not agent_name:
                    logger.warning(
                        f"Configured bot agent ID {self.bot_agent_id} not found, using default"
                    )
            except Exception as e:
                logger.warning(f"Could not lookup configured agent: {e}")

        # If no configured agent, get the user's primary agent
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

        # Handle admin commands - only allow for recognized users
        if not use_owner_context:
            text_lower = text.lower()
            if text_lower.startswith("!list"):
                await self._handle_list_command(
                    turn_context, agixt, agents if "agents" in dir() else None
                )
                return
            elif text_lower.startswith("!select "):
                await self._handle_select_command(turn_context, user_id, text, agixt)
                return
            elif text_lower.startswith("!clear"):
                await self._handle_clear_command(
                    turn_context, user_id, agixt, agent_name
                )
                return

        # Check for user's selected agent in this conversation (only if no bot-level agent configured)
        if not self.bot_agent_id and not use_owner_context:
            selection_key = (user_id, conversation_id)
            if selection_key in self.user_agent_selection:
                agent_name = self.user_agent_selection[selection_key]

        # Check team mode (only if no bot-level agent configured)
        if not self.bot_agent_id and conversation_id in self.team_conversation_config:
            team_config = self.team_conversation_config[conversation_id]
            agent_name = team_config["agent_name"]
            admin_email = self._get_user_email_from_teams_id(
                team_config["admin_user_id"]
            )
            if admin_email:
                admin_jwt = impersonate_user(admin_email)
                agixt = InternalClient(api_key=admin_jwt, user=admin_email)

        if not text:
            return

        # Send typing indicator
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        try:
            # Get channel info for context
            channel_name = (
                activity.channel_data.get("channel", {}).get("name", "")
                if activity.channel_data
                else ""
            )
            conversation_name = self._get_conversation_name(
                conversation_id, channel_name
            )

            # Import AGiXT class
            from XT import AGiXT

            agixt_instance = AGiXT(
                user=user_email,
                agent_name=agent_name,
                api_key=agixt.headers.get("Authorization", ""),
                conversation_name=conversation_name,
            )

            # Build message
            prompt_args = {
                "user_input": text,
                "context": f"**TEAMS CONVERSATION CONTEXT**\nConversation ID: {conversation_id}",
                "conversation_results": 0,
            }

            # Handle file attachments
            if activity.attachments:
                file_urls = []
                for attachment in activity.attachments:
                    if attachment.content_url:
                        try:
                            import aiohttp

                            async with aiohttp.ClientSession() as session:
                                async with session.get(attachment.content_url) as resp:
                                    if resp.status == 200:
                                        data = await resp.read()
                                        content_type = (
                                            attachment.content_type
                                            or "application/octet-stream"
                                        )
                                        encoded = base64.b64encode(data).decode("utf-8")
                                        file_urls.append(
                                            f"data:{content_type};base64,{encoded}"
                                        )
                        except Exception as e:
                            logger.error(f"Error downloading Teams attachment: {e}")

                if file_urls:
                    prompt_args["file_urls"] = file_urls

            message_data = {
                "role": "user",
                "content": text,
                "prompt_name": "Think About It",
                "prompt_category": "Default",
                "context": prompt_args.get("context", ""),
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
            async for chunk in agixt_instance.chat_completions_stream(
                prompt=chat_prompt
            ):
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

            # Send response (Teams supports longer messages than Discord)
            await turn_context.send_activity(
                Activity(type=ActivityTypes.message, text=reply)
            )

        except Exception as e:
            logger.error(
                f"Error handling Teams message for company {self.company_name}: {e}"
            )
            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    text=f"Sorry, I encountered an error: {str(e)}",
                )
            )

    async def _handle_list_command(self, turn_context, agixt, agents=None):
        """Handle the !list command."""
        try:
            if agents is None:
                agents = agixt.get_agents()

            if not agents:
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        text="You don't have any agents configured.",
                    )
                )
                return

            agent_list = []
            for i, agent in enumerate(agents, 1):
                name = (
                    agent.get("name", "Unknown") if isinstance(agent, dict) else agent
                )
                agent_list.append(f"{i}. **{name}**")

            response = "**Your Available Agents:**\n" + "\n".join(agent_list)
            response += "\n\n_Use `!select <agent_name>` to switch agents._"

            await turn_context.send_activity(
                Activity(type=ActivityTypes.message, text=response)
            )

        except Exception as e:
            logger.error(f"Error handling !list command: {e}")

    async def _handle_select_command(self, turn_context, user_id, text, agixt):
        """Handle the !select command."""
        try:
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        text="Usage: `!select <agent_name>`\nUse `!list` to see available agents.",
                    )
                )
                return

            requested_agent = parts[1].strip()
            agents = agixt.get_agents()

            if not agents:
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        text="You don't have any agents configured.",
                    )
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
                await turn_context.send_activity(
                    Activity(
                        type=ActivityTypes.message,
                        text=f"Agent `{requested_agent}` not found.\n\n**Available agents:** {', '.join(available)}",
                    )
                )
                return

            conversation_id = turn_context.activity.conversation.id
            selection_key = (user_id, conversation_id)
            self.user_agent_selection[selection_key] = matched_agent

            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    text=f"✅ Switched to **{matched_agent}** for this conversation.",
                )
            )

        except Exception as e:
            logger.error(f"Error handling !select command: {e}")

    async def _handle_clear_command(
        self, turn_context, user_id, agixt, current_agent_name
    ):
        """Handle the !clear command."""
        try:
            conversation_id = turn_context.activity.conversation.id
            selection_key = (user_id, conversation_id)
            if selection_key in self.user_agent_selection:
                current_agent_name = self.user_agent_selection[selection_key]

            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    text=f"✅ Conversation cleared. Starting fresh with **{current_agent_name}**!",
                )
            )

        except Exception as e:
            logger.error(f"Error handling !clear command: {e}")

    async def start(self):
        """Start the Teams bot."""
        try:
            # Refresh user cache
            self._refresh_teams_user_cache()

            self._is_ready = True
            self._started_at = datetime.now()

            logger.info(
                f"Teams bot for company {self.company_name} ({self.company_id}) started"
            )

            # Keep alive - the adapter will handle incoming requests via the API endpoint
            while self._is_ready:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Teams bot for company {self.company_name} failed: {e}")
            raise

    async def stop(self):
        """Stop the Teams bot gracefully."""
        self._is_ready = False

    async def process_activity(self, activity_json: dict) -> str:
        """Process an incoming activity from the Bot Framework webhook."""
        try:
            activity = Activity.deserialize(activity_json)
            auth_header = activity_json.get("authorization", "")

            async def callback(turn_context: TurnContext):
                await self.handle_message(turn_context)

            await self.adapter.process_activity(activity, auth_header, callback)
            return "OK"
        except Exception as e:
            logger.error(f"Error processing Teams activity: {e}")
            raise

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at


class TeamsBotManager:
    """
    Manages Microsoft Teams bots for multiple companies.
    """

    SERVER_BOT_ID = "server"

    def __init__(self):
        self.bots: Dict[str, CompanyTeamsBot] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def get_server_bot_credentials(self) -> tuple:
        """Get the server-level Teams bot credentials."""
        app_id = getenv("MICROSOFT_APP_ID")
        app_password = getenv("MICROSOFT_APP_PASSWORD")

        if app_id and app_password:
            return app_id, app_password

        # Check database
        try:
            from DB import ServerExtensionSetting
            from endpoints.ServerConfig import decrypt_config_value

            with get_session() as db:
                app_id_setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == "teams",
                        ServerExtensionSetting.setting_key == "MICROSOFT_APP_ID",
                    )
                    .first()
                )
                app_password_setting = (
                    db.query(ServerExtensionSetting)
                    .filter(
                        ServerExtensionSetting.extension_name == "teams",
                        ServerExtensionSetting.setting_key == "MICROSOFT_APP_PASSWORD",
                    )
                    .first()
                )

                if app_id_setting and app_id_setting.setting_value:
                    if app_id_setting.is_sensitive:
                        app_id = decrypt_config_value(app_id_setting.setting_value)
                    else:
                        app_id = app_id_setting.setting_value

                if app_password_setting and app_password_setting.setting_value:
                    if app_password_setting.is_sensitive:
                        app_password = decrypt_config_value(
                            app_password_setting.setting_value
                        )
                    else:
                        app_password = app_password_setting.setting_value

        except Exception as e:
            logger.error(f"Error getting server Teams credentials from database: {e}")

        return app_id, app_password

    def get_company_bot_config(self) -> Dict[str, Dict[str, str]]:
        """Get Teams bot configuration for all companies."""
        configs = {}

        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(CompanyExtensionSetting.extension_name == "teams")
                .filter(
                    CompanyExtensionSetting.setting_key.in_(
                        [
                            "MICROSOFT_APP_ID",
                            "MICROSOFT_APP_PASSWORD",
                            "TEAMS_BOT_ENABLED",
                            "teams_bot_agent_id",
                            "teams_bot_permission_mode",
                            "teams_bot_owner_id",
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
                        "bot_agent_id": None,
                        "bot_permission_mode": "recognized_users",
                        "bot_owner_id": None,
                    }

                value = setting.setting_value
                if setting.is_sensitive and value:
                    from endpoints.ServerConfig import decrypt_config_value

                    value = decrypt_config_value(value)

                if setting.setting_key == "MICROSOFT_APP_ID":
                    configs[company_id]["app_id"] = value
                elif setting.setting_key == "MICROSOFT_APP_PASSWORD":
                    configs[company_id]["app_password"] = value
                elif setting.setting_key == "TEAMS_BOT_ENABLED":
                    configs[company_id]["enabled"] = value
                elif setting.setting_key == "teams_bot_agent_id":
                    configs[company_id]["bot_agent_id"] = value
                elif setting.setting_key == "teams_bot_permission_mode":
                    configs[company_id]["bot_permission_mode"] = (
                        value or "recognized_users"
                    )
                elif setting.setting_key == "teams_bot_owner_id":
                    configs[company_id]["bot_owner_id"] = value

        return configs

    async def start_bot_for_company(
        self,
        company_id: str,
        company_name: str,
        app_id: str,
        app_password: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
    ) -> bool:
        """Start a Teams bot for a specific company."""
        if company_id in self.bots and company_id in self._tasks:
            logger.warning(f"Teams bot for company {company_name} is already running")
            return False

        try:
            bot = CompanyTeamsBot(
                company_id,
                company_name,
                app_id,
                app_password,
                bot_agent_id=bot_agent_id,
                bot_permission_mode=bot_permission_mode,
                bot_owner_id=bot_owner_id,
            )
            self.bots[company_id] = bot

            task = asyncio.create_task(bot.start())
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
        server_app_id, server_app_password = self.get_server_bot_credentials()
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
                        bot_agent_id=config.get("bot_agent_id"),
                        bot_permission_mode=config.get(
                            "bot_permission_mode", "recognized_users"
                        ),
                        bot_owner_id=config.get("bot_owner_id"),
                    )

        elif server_app_id and server_app_password:
            for company_id in list(self.bots.keys()):
                if company_id != self.SERVER_BOT_ID:
                    await self.stop_bot_for_company(company_id)

            if self.SERVER_BOT_ID not in self.bots:
                logger.info("Starting server-level Teams bot")
                await self.start_bot_for_company(
                    self.SERVER_BOT_ID,
                    "AGiXT Server Bot",
                    server_app_id,
                    server_app_password,
                )
        else:
            for company_id in list(self.bots.keys()):
                await self.stop_bot_for_company(company_id)

            if not self.bots:
                logger.debug("No Teams bot credentials configured")

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
        self._running = True
        logger.info("Starting Teams Bot Manager...")

        await self.sync_bots()

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Teams Bot Manager started")

    async def stop(self):
        """Stop all bots and the manager."""
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

        for company_id in list(self.bots.keys()):
            await self.stop_bot_for_company(company_id)

        logger.info("Teams Bot Manager stopped")

    def get_status(self) -> Dict[str, TeamsBotStatus]:
        """Get status of all running bots."""
        statuses = {}
        for company_id, bot in self.bots.items():
            statuses[company_id] = TeamsBotStatus(
                company_id=company_id,
                company_name=bot.company_name,
                started_at=bot.started_at,
                is_running=bot.is_ready,
            )
        return statuses

    def get_bot_status(self, company_id: str) -> Optional[TeamsBotStatus]:
        """Get status of a specific company's bot."""
        bot = self.bots.get(company_id)
        if not bot:
            return None
        return TeamsBotStatus(
            company_id=company_id,
            company_name=bot.company_name,
            started_at=bot.started_at,
            is_running=bot.is_ready,
        )

    def get_bot(self, company_id: str) -> Optional[CompanyTeamsBot]:
        """Get a specific company's bot instance for webhook handling."""
        return self.bots.get(company_id)


# Global instance
_manager: Optional[TeamsBotManager] = None


def get_teams_bot_manager() -> Optional[TeamsBotManager]:
    """Get the global Teams bot manager instance."""
    return _manager


async def start_teams_bot_manager():
    """Start the global Teams bot manager."""
    global _manager

    if not TEAMS_BOT_AVAILABLE:
        logger.warning(
            "Teams bot manager cannot start - botbuilder-core library not installed"
        )
        return None

    if _manager is None:
        _manager = TeamsBotManager()
    await _manager.start()
    return _manager


async def stop_teams_bot_manager():
    """Stop the global Teams bot manager."""
    global _manager
    if _manager:
        await _manager.stop()
        _manager = None
