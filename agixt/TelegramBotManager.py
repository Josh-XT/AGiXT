"""
Telegram Bot Manager for AGiXT

This module manages Telegram bots for multiple companies. Each company can have
its own Telegram bot instance running concurrently within a single manager process.

The manager:
- Starts/stops bots based on company extension settings
- Handles incoming messages via long polling or webhook
- Provides APIs for querying bot status
- Manages bot lifecycle and configuration

Telegram Bot Setup:
1. Create a bot via @BotFather on Telegram
2. Get the bot token
3. Configure the token in company settings (telegram_bot_token)
4. The bot will automatically start when settings are saved

Required company settings:
- telegram_bot_token: Bot token from BotFather
- telegram_bot_enabled: Whether the bot is active (default: true)
- telegram_default_agent: Default AI agent to use (default: XT)
"""

import asyncio
import logging
import requests
from typing import Dict, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime

from DB import (
    get_session,
    CompanyExtensionSetting,
    Company,
    UserOAuth,
    OAuthProvider,
)
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions


def get_telegram_user_ids(company_id=None):
    """
    Get mapping of Telegram user IDs to AGiXT user IDs for a company.

    Args:
        company_id: Optional company ID to filter by

    Returns:
        Dict mapping Telegram user ID (string) -> AGiXT user ID
    """
    user_ids = {}
    with get_session() as session:
        provider = session.query(OAuthProvider).filter_by(name="telegram").first()
        if not provider:
            return user_ids

        query = session.query(UserOAuth).filter_by(provider_id=provider.id)

        if company_id:
            query = query.filter(UserOAuth.company_id == company_id)

        for oauth in query.all():
            if oauth.provider_user_id:
                user_ids[oauth.provider_user_id] = str(oauth.user_id)

    return user_ids


logger = logging.getLogger(__name__)


@dataclass
class TelegramBotStatus:
    """Status information for a company's Telegram bot."""

    company_id: str
    company_name: str
    bot_username: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    last_update_id: int = 0
    messages_processed: int = 0


class CompanyTelegramBot:
    """
    Telegram bot instance for a single company.

    Handles:
    - Long polling for updates
    - Processing incoming messages
    - Responding via Bot API
    - User impersonation for personalized responses
    - Admin commands for bot management

    Permission modes:
    - owner_only: Only the user who set up the bot can interact
    - recognized_users: Only users with linked AGiXT accounts can interact (default)
    - anyone: Anyone can interact with the bot
    """

    # Admin commands
    ADMIN_COMMANDS = {
        "/help": "Show available commands",
        "/list": "List available AI agents",
        "/select <agent>": "Select an AI agent to chat with",
        "/clear": "Clear conversation history",
        "/status": "Show bot status",
        "/link": "Link your Telegram to AGiXT account",
    }

    def __init__(
        self,
        company_id: str,
        company_name: str,
        bot_token: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
    ):
        """
        Initialize the Telegram bot for a company.

        Args:
            company_id: The company's UUID
            company_name: Human-readable company name
            bot_token: Telegram bot token from BotFather
            bot_agent_id: Specific agent ID to use (None = user's default)
            bot_permission_mode: Permission mode (owner_only, recognized_users, allowlist, anyone)
            bot_owner_id: User ID of who configured this bot
            bot_allowlist: Comma-separated Telegram user IDs for allowlist mode
        """
        self.company_id = company_id
        self.company_name = company_name
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        # Parse allowlist - comma-separated Telegram user IDs
        self.bot_allowlist = set()
        if bot_allowlist:
            for item in bot_allowlist.split(","):
                item = item.strip()
                if item:
                    self.bot_allowlist.add(item)

        # Bot state
        self.is_running = False
        self.started_at: Optional[datetime] = None
        self.last_update_id = 0
        self.messages_processed = self._load_messages_processed()
        self._unsaved_message_count = 0  # Track unsaved increments for batching

        # Bot info (fetched on start)
        self.bot_id: Optional[int] = None
        self.bot_username: str = ""

        # User agent selections (Telegram user ID -> agent name)
        self.user_agents: Dict[str, str] = {}

        # Internal client for API calls
        self.internal_client = InternalClient()

        # Cache of Telegram user IDs to AGiXT user IDs
        self._user_id_cache: Dict[str, str] = {}

        logger.info(
            f"Initialized Telegram bot for company {company_name} ({company_id})"
        )

    def _load_messages_processed(self) -> int:
        """Load the messages_processed count from the database."""
        try:
            from DB import ServerExtensionSetting

            with get_session() as db:
                if self.company_id == "server":
                    # Server-level bot
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "telegram",
                            ServerExtensionSetting.setting_key
                            == "TELEGRAM_MESSAGES_PROCESSED",
                        )
                        .first()
                    )
                else:
                    # Company-level bot
                    setting = (
                        db.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == self.company_id,
                            CompanyExtensionSetting.extension_name == "telegram",
                            CompanyExtensionSetting.setting_key
                            == "TELEGRAM_MESSAGES_PROCESSED",
                        )
                        .first()
                    )

                if setting and setting.setting_value:
                    return int(setting.setting_value)
        except Exception as e:
            logger.warning(
                f"Could not load messages_processed for {self.company_id}: {e}"
            )
        return 0

    def _save_messages_processed(self):
        """Save the messages_processed count to the database."""
        try:
            from DB import ServerExtensionSetting

            with get_session() as db:
                if self.company_id == "server":
                    # Server-level bot
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "telegram",
                            ServerExtensionSetting.setting_key
                            == "TELEGRAM_MESSAGES_PROCESSED",
                        )
                        .first()
                    )
                    if setting:
                        setting.setting_value = str(self.messages_processed)
                    else:
                        setting = ServerExtensionSetting(
                            extension_name="telegram",
                            setting_key="TELEGRAM_MESSAGES_PROCESSED",
                            setting_value=str(self.messages_processed),
                            is_sensitive=False,
                        )
                        db.add(setting)
                else:
                    # Company-level bot
                    setting = (
                        db.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == self.company_id,
                            CompanyExtensionSetting.extension_name == "telegram",
                            CompanyExtensionSetting.setting_key
                            == "TELEGRAM_MESSAGES_PROCESSED",
                        )
                        .first()
                    )
                    if setting:
                        setting.setting_value = str(self.messages_processed)
                    else:
                        setting = CompanyExtensionSetting(
                            company_id=self.company_id,
                            extension_name="telegram",
                            setting_key="TELEGRAM_MESSAGES_PROCESSED",
                            setting_value=str(self.messages_processed),
                            is_sensitive=False,
                        )
                        db.add(setting)
                db.commit()
                self._unsaved_message_count = 0
        except Exception as e:
            logger.warning(
                f"Could not save messages_processed for {self.company_id}: {e}"
            )

    def _make_request(self, method: str, data: dict = None, files: dict = None):
        """Make a request to the Telegram Bot API."""
        url = f"{self.base_url}/{method}"

        try:
            if files:
                response = requests.post(url, data=data, files=files, timeout=60)
            elif data:
                response = requests.post(url, json=data, timeout=60)
            else:
                response = requests.get(url, timeout=60)

            result = response.json()

            if not result.get("ok"):
                error_desc = result.get("description", "Unknown error")
                logger.error(f"Telegram API error: {error_desc}")
                return None

            return result.get("result")

        except Exception as e:
            logger.error(f"Telegram request failed: {str(e)}")
            return None

    async def _fetch_bot_info(self) -> bool:
        """Fetch bot information from Telegram."""
        result = self._make_request("getMe")
        if result:
            self.bot_id = result.get("id")
            self.bot_username = result.get("username", "")
            logger.info(f"Bot info: @{self.bot_username} (ID: {self.bot_id})")
            return True
        return False

    def _refresh_user_id_cache(self):
        """Refresh the Telegram user ID to AGiXT user ID cache."""
        self._user_id_cache = get_telegram_user_ids(self.company_id)

    def _get_agixt_user_id(self, telegram_user_id: str) -> Optional[str]:
        """Get the AGiXT user ID for a Telegram user."""
        if telegram_user_id not in self._user_id_cache:
            self._refresh_user_id_cache()
        return self._user_id_cache.get(telegram_user_id)

    async def _get_user_token(self, telegram_user_id: str) -> Optional[str]:
        """Get an impersonation token for a user."""
        agixt_user_id = self._get_agixt_user_id(telegram_user_id)
        if not agixt_user_id:
            return None

        try:
            return impersonate_user(agixt_user_id)
        except Exception as e:
            logger.error(f"Error impersonating user {telegram_user_id}: {e}")
            return None

    async def _get_available_agents(self) -> List[str]:
        """Get list of available agents for this company."""
        try:
            with get_session() as session:
                from DB import User

                user = session.query(User).filter_by(company_id=self.company_id).first()
                if not user:
                    return ["XT"]
                user_id = str(user.id)

            token = impersonate_user(user_id)
            agents = self.internal_client.get_agents(token=token)
            return [a.get("name", "XT") for a in agents] if agents else ["XT"]
        except Exception as e:
            logger.error(f"Error getting agents: {e}")
            return ["XT"]

    async def _get_default_agent(self) -> str:
        """Get the default agent for this company."""
        with get_session() as session:
            setting = (
                session.query(CompanyExtensionSetting)
                .filter_by(
                    company_id=self.company_id,
                    setting_name="telegram_default_agent",
                )
                .first()
            )
            if setting and setting.setting_value:
                return setting.setting_value
        return "XT"

    def _get_selected_agent(self, telegram_user_id: str) -> Optional[str]:
        """Get the selected agent for a user, or None for default."""
        return self.user_agents.get(telegram_user_id)

    async def _send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Send a message to a chat.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            reply_to_message_id: Optional message to reply to
            parse_mode: HTML or Markdown

        Returns:
            True if successful
        """
        try:
            # Telegram has a 4096 character limit
            if len(text) > 4096:
                chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
                for chunk in chunks:
                    await self._send_message(
                        chat_id, chunk, reply_to_message_id, parse_mode
                    )
                return True

            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }

            if reply_to_message_id:
                data["reply_to_message_id"] = reply_to_message_id

            result = self._make_request("sendMessage", data)
            return result is not None

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _send_chat_action(self, chat_id: int, action: str = "typing"):
        """Send a chat action (typing indicator)."""
        try:
            self._make_request("sendChatAction", {"chat_id": chat_id, "action": action})
        except:
            pass

    async def _handle_command(
        self,
        chat_id: int,
        user_id: str,
        username: str,
        command: str,
        args: str,
    ) -> Optional[str]:
        """
        Handle bot commands.

        Args:
            chat_id: Chat ID
            user_id: Telegram user ID
            username: Telegram username
            command: Command (e.g., /help)
            args: Command arguments

        Returns:
            Response message or None
        """
        cmd = command.lower()

        if cmd == "/help" or cmd == "/start":
            lines = [
                f"👋 Welcome to {self.company_name} AI Assistant!",
                "",
                "📋 <b>Available Commands:</b>",
            ]
            for cmd_name, cmd_desc in self.ADMIN_COMMANDS.items():
                lines.append(f"• {cmd_name} - {cmd_desc}")
            lines.append("")
            lines.append("Just send me a message to chat with the AI!")
            return "\n".join(lines)

        elif cmd == "/list":
            agents = await self._get_available_agents()
            current = (
                self._get_selected_agent(user_id) or await self._get_default_agent()
            )
            lines = ["🤖 <b>Available Agents:</b>"]
            for agent in agents:
                marker = "✓ " if agent == current else "  "
                lines.append(f"{marker}{agent}")
            lines.append(f"\n📍 Current: {current}")
            lines.append("Use /select &lt;agent&gt; to switch")
            return "\n".join(lines)

        elif cmd == "/select":
            if not args:
                return "❌ Please specify an agent name. Use /list to see available agents."

            agent_name = args.strip()
            agents = await self._get_available_agents()

            matched = None
            for agent in agents:
                if agent.lower() == agent_name.lower():
                    matched = agent
                    break

            if matched:
                self.user_agents[user_id] = matched
                return f"✓ Switched to agent: {matched}"
            else:
                return f"❌ Agent '{agent_name}' not found. Use /list to see available agents."

        elif cmd == "/clear":
            if user_id in self.user_agents:
                del self.user_agents[user_id]
            return "✓ Conversation cleared. Your next message will start fresh."

        elif cmd == "/status":
            uptime = ""
            if self.started_at:
                delta = datetime.utcnow() - self.started_at
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime = f"{hours}h {minutes}m {seconds}s"

            current_agent = (
                self._get_selected_agent(user_id) or await self._get_default_agent()
            )
            linked = "Yes" if self._get_agixt_user_id(user_id) else "No"

            return (
                f"📊 <b>Bot Status</b>\n"
                f"Bot: @{self.bot_username}\n"
                f"Company: {self.company_name}\n"
                f"Uptime: {uptime}\n"
                f"Messages: {self.messages_processed}\n"
                f"Your Agent: {current_agent}\n"
                f"Account Linked: {linked}"
            )

        elif cmd == "/link":
            # Provide instructions for linking accounts
            return (
                "🔗 <b>Link Your Account</b>\n\n"
                "To link your Telegram account to AGiXT:\n\n"
                "1. Log in to your AGiXT account\n"
                "2. Go to Settings → Integrations\n"
                "3. Click 'Link Telegram'\n"
                "4. Enter this info:\n"
                f"   • Telegram ID: <code>{user_id}</code>\n"
                f"   • Username: @{username}\n\n"
                "Once linked, the AI will remember your preferences!"
            )

        return None

    async def _process_message(self, message: dict):
        """
        Process an incoming message.

        Args:
            message: Telegram message object
        """
        try:
            chat_id = message.get("chat", {}).get("id")
            user_id = str(message.get("from", {}).get("id", ""))
            username = message.get("from", {}).get("username", "")
            text = message.get("text", "")
            message_id = message.get("message_id")

            if not text or not chat_id:
                return

            logger.info(
                f"Processing message from {username or user_id}: {text[:100]}..."
            )
            self.messages_processed += 1
            self._unsaved_message_count += 1
            # Save every 5 messages or on first message to batch DB writes
            if self._unsaved_message_count >= 5 or self.messages_processed == 1:
                self._save_messages_processed()

            # Get AGiXT user ID for permission checks
            agixt_user_id = self._get_agixt_user_id(user_id)
            use_owner_context = False

            # Apply permission mode checks
            if self.bot_permission_mode == "owner_only":
                # Only the owner can interact
                if not agixt_user_id or agixt_user_id != self.bot_owner_id:
                    return
            elif self.bot_permission_mode == "allowlist":
                # Only users in the allowlist can interact
                if str(user_id) not in self.bot_allowlist:
                    logger.debug(f"Telegram user {user_id} not in allowlist, ignoring")
                    return
                # For allowlist mode, use owner context if no linked account
                if not agixt_user_id:
                    use_owner_context = True
            elif self.bot_permission_mode == "recognized_users":
                # Default behavior - only users with linked accounts
                if not agixt_user_id:
                    return
            elif self.bot_permission_mode == "anyone":
                # Anyone can interact
                if not agixt_user_id:
                    use_owner_context = True
            else:
                # Unknown permission mode, default to recognized_users behavior
                if not agixt_user_id:
                    return

            # Check for commands - only allow for recognized users (not anonymous)
            if text.startswith("/") and not use_owner_context:
                parts = text.split(None, 1)
                command = parts[0].split("@")[0]  # Remove @botusername if present
                args = parts[1] if len(parts) > 1 else ""

                response = await self._handle_command(
                    chat_id, user_id, username, command, args
                )
                if response:
                    await self._send_message(chat_id, response, message_id)
                return

            # Show typing indicator
            await self._send_chat_action(chat_id, "typing")

            # Determine which agent to use
            agent_name = None

            # If bot has a configured agent, use it
            if self.bot_agent_id:
                # We'll set agent_name later when we have token
                pass
            else:
                # Get user's selected agent
                agent_name = self._get_selected_agent(user_id)
                if not agent_name:
                    agent_name = await self._get_default_agent()

            # Try to get user's token
            user_token = None
            if use_owner_context and self.bot_owner_id:
                user_token = impersonate_user(self.bot_owner_id)
            else:
                user_token = await self._get_user_token(user_id)

            # Build conversation name
            conversation_name = f"telegram-{user_id}-{self.company_id[:8]}"

            # If bot has configured agent, resolve agent name
            if self.bot_agent_id and user_token:
                try:
                    from InternalClient import InternalClient

                    agixt = InternalClient(api_key=user_token)
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
                        agent_name = await self._get_default_agent()
                except Exception as e:
                    logger.warning(f"Could not lookup configured agent: {e}")
                    agent_name = await self._get_default_agent()

            if user_token:
                chat = ChatCompletions(
                    agent_name=agent_name,
                    api_key=user_token,
                )
            else:
                with get_session() as session:
                    from DB import User

                    user = (
                        session.query(User)
                        .filter_by(company_id=self.company_id)
                        .first()
                    )
                    if user:
                        default_token = impersonate_user(str(user.id))
                        # If bot has configured agent, resolve agent name
                        if self.bot_agent_id and not agent_name:
                            try:
                                from InternalClient import InternalClient

                                agixt = InternalClient(api_key=default_token)
                                agents = agixt.get_agents()
                                for agent in agents:
                                    if isinstance(agent, dict) and str(
                                        agent.get("id")
                                    ) == str(self.bot_agent_id):
                                        agent_name = agent.get("name", "XT")
                                        break
                                if not agent_name:
                                    agent_name = await self._get_default_agent()
                            except Exception as e:
                                logger.warning(
                                    f"Could not lookup configured agent: {e}"
                                )
                                agent_name = await self._get_default_agent()
                        chat = ChatCompletions(
                            agent_name=agent_name,
                            api_key=default_token,
                        )
                    else:
                        logger.error(f"No users found for company {self.company_id}")
                        await self._send_message(
                            chat_id,
                            "Sorry, I'm having trouble connecting to my AI backend.",
                            message_id,
                        )
                        return

            # Generate response
            response = await chat.chat_completions(
                messages=[{"role": "user", "content": text}],
                conversation_name=conversation_name,
                context_results=10,
            )

            if response and isinstance(response, dict):
                content = (
                    response.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if content:
                    # Convert markdown to HTML for Telegram
                    content = content.replace("**", "<b>").replace("__", "<i>")
                    await self._send_message(chat_id, content, message_id)
                else:
                    await self._send_message(
                        chat_id,
                        "I apologize, but I couldn't generate a response.",
                        message_id,
                    )
            else:
                await self._send_message(
                    chat_id,
                    "I apologize, but I couldn't generate a response.",
                    message_id,
                )

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def _poll_updates(self):
        """Poll for updates using long polling."""
        while self.is_running:
            try:
                data = {
                    "offset": self.last_update_id + 1,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"],
                }

                result = self._make_request("getUpdates", data)

                if result:
                    for update in result:
                        update_id = update.get("update_id", 0)
                        if update_id > self.last_update_id:
                            self.last_update_id = update_id

                        if "message" in update:
                            await self._process_message(update["message"])

                # Small delay between polls
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error polling updates: {e}")
                await asyncio.sleep(5)  # Wait before retry

    async def start(self):
        """Start the bot."""
        logger.info(f"Starting Telegram bot for {self.company_name}")

        # Fetch bot info
        if not await self._fetch_bot_info():
            logger.error("Failed to fetch bot info - invalid token?")
            return

        self.is_running = True
        self.started_at = datetime.utcnow()

        # Start polling loop
        try:
            await self._poll_updates()
        except asyncio.CancelledError:
            logger.info(f"Telegram bot for {self.company_name} cancelled")
        except Exception as e:
            logger.error(f"Telegram bot error for {self.company_name}: {e}")
        finally:
            self.is_running = False

    async def stop(self):
        """Stop the bot."""
        logger.info(f"Stopping Telegram bot for {self.company_name}")
        # Save any unsaved message count before stopping
        if self._unsaved_message_count > 0:
            self._save_messages_processed()
        self.is_running = False

    def get_status(self) -> TelegramBotStatus:
        """Get current bot status."""
        return TelegramBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            bot_username=self.bot_username,
            started_at=self.started_at,
            is_running=self.is_running,
            last_update_id=self.last_update_id,
            messages_processed=self.messages_processed,
        )


class TelegramBotManager:
    """
    Manager for all company Telegram bots.

    Handles:
    - Starting/stopping bots based on company settings
    - Monitoring bot health
    - Syncing with database configuration
    """

    def __init__(self):
        self.bots: Dict[str, CompanyTelegramBot] = {}
        self.bot_tasks: Dict[str, asyncio.Task] = {}
        self._sync_lock = asyncio.Lock()
        self._running = False

        logger.info("Telegram Bot Manager initialized")

    async def _get_companies_with_telegram_bot(self) -> List[Dict]:
        """Get all companies that have Telegram bot configuration."""
        companies = []

        with get_session() as session:
            settings = (
                session.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.setting_name == "telegram_bot_token",
                    CompanyExtensionSetting.setting_value.isnot(None),
                    CompanyExtensionSetting.setting_value != "",
                )
                .all()
            )

            for setting in settings:
                company = (
                    session.query(Company).filter_by(id=setting.company_id).first()
                )
                if not company:
                    continue

                # Check if enabled
                enabled_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="telegram_bot_enabled",
                    )
                    .first()
                )

                is_enabled = True
                if enabled_setting and enabled_setting.setting_value:
                    is_enabled = enabled_setting.setting_value.lower() in (
                        "true",
                        "1",
                        "yes",
                    )

                if not is_enabled:
                    continue

                # Get new permission settings
                agent_id_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="telegram_bot_agent_id",
                    )
                    .first()
                )
                permission_mode_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="telegram_bot_permission_mode",
                    )
                    .first()
                )
                owner_id_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="telegram_bot_owner_id",
                    )
                    .first()
                )
                allowlist_setting = (
                    session.query(CompanyExtensionSetting)
                    .filter_by(
                        company_id=setting.company_id,
                        setting_name="telegram_bot_allowlist",
                    )
                    .first()
                )

                companies.append(
                    {
                        "company_id": str(setting.company_id),
                        "company_name": company.name,
                        "bot_token": setting.setting_value,
                        "bot_agent_id": (
                            agent_id_setting.setting_value if agent_id_setting else None
                        ),
                        "bot_permission_mode": (
                            permission_mode_setting.setting_value
                            if permission_mode_setting
                            else "recognized_users"
                        ),
                        "bot_owner_id": (
                            owner_id_setting.setting_value if owner_id_setting else None
                        ),
                        "bot_allowlist": (
                            allowlist_setting.setting_value
                            if allowlist_setting
                            else None
                        ),
                    }
                )

        return companies

    async def sync_bots(self):
        """Synchronize running bots with database configuration."""
        async with self._sync_lock:
            try:
                companies = await self._get_companies_with_telegram_bot()
                company_ids = {c["company_id"] for c in companies}

                # Stop bots for companies that no longer have config
                for company_id in list(self.bots.keys()):
                    if company_id not in company_ids:
                        await self._stop_bot(company_id)

                # Start or update bots
                for company_config in companies:
                    company_id = company_config["company_id"]

                    if company_id in self.bots:
                        # Check if token changed
                        bot = self.bots[company_id]
                        if bot.bot_token != company_config["bot_token"]:
                            await self._stop_bot(company_id)
                            await self._start_bot(company_config)
                    else:
                        await self._start_bot(company_config)

            except Exception as e:
                logger.error(f"Error syncing Telegram bots: {e}")

    async def _start_bot(self, config: Dict):
        """Start a bot for a company."""
        company_id = config["company_id"]

        try:
            bot = CompanyTelegramBot(
                company_id=company_id,
                company_name=config["company_name"],
                bot_token=config["bot_token"],
                bot_agent_id=config.get("bot_agent_id"),
                bot_permission_mode=config.get(
                    "bot_permission_mode", "recognized_users"
                ),
                bot_owner_id=config.get("bot_owner_id"),
                bot_allowlist=config.get("bot_allowlist"),
            )

            self.bots[company_id] = bot
            self.bot_tasks[company_id] = asyncio.create_task(bot.start())

            logger.info(f"Started Telegram bot for {config['company_name']}")

        except Exception as e:
            logger.error(f"Error starting Telegram bot for {company_id}: {e}")

    async def _stop_bot(self, company_id: str):
        """Stop a bot for a company."""
        try:
            if company_id in self.bots:
                bot = self.bots[company_id]
                await bot.stop()

            if company_id in self.bot_tasks:
                task = self.bot_tasks[company_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.bot_tasks[company_id]

            if company_id in self.bots:
                del self.bots[company_id]

            logger.info(f"Stopped Telegram bot for company {company_id}")

        except Exception as e:
            logger.error(f"Error stopping Telegram bot for {company_id}: {e}")

    async def start(self):
        """Start the bot manager."""
        self._running = True
        logger.info("Starting Telegram Bot Manager")

        # Initial sync
        await self.sync_bots()

        # Periodic sync loop
        while self._running:
            await asyncio.sleep(60)
            await self.sync_bots()

    async def stop(self):
        """Stop all bots and the manager."""
        self._running = False
        logger.info("Stopping Telegram Bot Manager")

        for company_id in list(self.bots.keys()):
            await self._stop_bot(company_id)

    def get_all_status(self) -> List[TelegramBotStatus]:
        """Get status of all bots."""
        return [bot.get_status() for bot in self.bots.values()]

    def get_bot_status(self, company_id: str) -> Optional[TelegramBotStatus]:
        """Get status of a specific company's bot."""
        bot = self.bots.get(company_id)
        return bot.get_status() if bot else None


# Global manager instance
_manager: Optional[TelegramBotManager] = None


def get_telegram_bot_manager() -> Optional[TelegramBotManager]:
    """Get the global Telegram bot manager instance."""
    return _manager


async def start_telegram_bot_manager():
    """Start the global Telegram bot manager."""
    global _manager

    if _manager is not None:
        logger.warning("Telegram Bot Manager already running")
        return

    _manager = TelegramBotManager()
    await _manager.start()


async def stop_telegram_bot_manager():
    """Stop the global Telegram bot manager."""
    global _manager

    if _manager is None:
        return

    await _manager.stop()
    _manager = None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async def main():
        try:
            await start_telegram_bot_manager()
        except KeyboardInterrupt:
            await stop_telegram_bot_manager()

    asyncio.run(main())
