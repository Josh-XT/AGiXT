"""
WhatsApp Bot Manager for AGiXT

This module manages WhatsApp bots for multiple companies. Each company can have
its own WhatsApp Business account integrated with AGiXT.

The manager:
- Handles incoming webhook events from WhatsApp Cloud API
- Processes messages and generates AI responses
- Manages bot configuration per company/phone number
- Provides APIs for querying bot status

WhatsApp bots work via webhooks - Meta/Facebook sends POST requests when
messages arrive. This manager processes those webhook events.

Required environment variables:
- WHATSAPP_VERIFY_TOKEN: Webhook verification token (you choose this)

Required company settings:
- whatsapp_phone_number_id: WhatsApp Business phone number ID
- whatsapp_access_token: Graph API access token
- whatsapp_bot_enabled: Whether the bot is active (default: true)
- whatsapp_default_agent: Default AI agent to use (default: XT)

Setup Instructions:
1. Create a Meta Business account and WhatsApp Business app
2. Add WhatsApp product to your app
3. Configure webhook URL pointing to your AGiXT instance
4. Subscribe to messages webhook field
5. Get Phone Number ID and access token
6. Configure in company settings
"""

import asyncio
import logging
import hashlib
import hmac
from typing import Dict, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime

import requests

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


def get_whatsapp_user_ids(company_id=None):
    """
    Get mapping of WhatsApp phone numbers to AGiXT user IDs for a company.

    Args:
        company_id: Optional company ID to filter by

    Returns:
        Dict mapping phone number -> AGiXT user ID
    """
    user_ids = {}
    with get_session() as session:
        provider = session.query(OAuthProvider).filter_by(name="whatsapp").first()
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
class WhatsAppBotStatus:
    """Status information for a company's WhatsApp bot."""

    company_id: str
    company_name: str
    phone_number_id: str
    display_phone_number: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    messages_processed: int = 0


class CompanyWhatsAppBot:
    """
    WhatsApp bot instance for a single company.

    Handles:
    - Processing incoming messages from webhooks
    - Responding via WhatsApp Cloud API
    - User impersonation for personalized responses
    - Admin commands for bot management

    Permission modes:
    - owner_only: Only the user who set up the bot can interact
    - recognized_users: Only users with linked AGiXT accounts can interact (default)
    - anyone: Anyone can interact with the bot
    """

    # Admin commands that users can use
    ADMIN_COMMANDS = {
        "!help": "Show available commands",
        "!list": "List available AI agents",
        "!select <agent>": "Select an AI agent to chat with",
        "!clear": "Clear conversation history",
        "!status": "Show bot status",
    }

    def __init__(
        self,
        company_id: str,
        company_name: str,
        phone_number_id: str,
        access_token: str,
        display_phone_number: str = "",
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
    ):
        """
        Initialize the WhatsApp bot for a company.

        Args:
            company_id: The company's UUID
            company_name: Human-readable company name
            phone_number_id: WhatsApp Business phone number ID
            access_token: Graph API access token
            display_phone_number: Human-readable phone number
            bot_agent_id: Specific agent ID to use (None = user's default)
            bot_permission_mode: Permission mode (owner_only, recognized_users, allowlist, anyone)
            bot_owner_id: User ID of who configured this bot
            bot_allowlist: Comma-separated phone numbers for allowlist mode
        """
        self.company_id = company_id
        self.company_name = company_name
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.display_phone_number = display_phone_number

        self.base_url = "https://graph.facebook.com/v18.0"

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        # Parse allowlist - comma-separated phone numbers
        self.bot_allowlist = set()
        if bot_allowlist:
            import re

            for item in bot_allowlist.split(","):
                item = item.strip()
                # Normalize phone number (remove non-digits except +)
                item = re.sub(r"[^\d+]", "", item)
                if not item.startswith("+"):
                    item = "+" + item
                if item:
                    self.bot_allowlist.add(item)

        # Bot state
        self.is_running = True
        self.started_at = datetime.utcnow()
        self.messages_processed = 0

        # Track processed message IDs to avoid duplicates
        self.processed_message_ids: Set[str] = set()

        # User agent selections (phone number -> agent name)
        self.user_agents: Dict[str, str] = {}

        # Internal client for API calls
        self.internal_client = InternalClient()

        # Cache of phone numbers to AGiXT user IDs
        self._user_id_cache: Dict[str, str] = {}

        # Log initialization without exposing sensitive phone number data
        masked_phone = (
            "****" + (display_phone_number or phone_number_id or "")[-4:]
            if (display_phone_number or phone_number_id)
            else "unknown"
        )
        logger.info(
            f"Initialized WhatsApp bot for company {company_name}, "
            f"phone {masked_phone}"
        )

    def _get_headers(self):
        """Get authorization headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _refresh_user_id_cache(self):
        """Refresh the phone number to AGiXT user ID cache."""
        self._user_id_cache = get_whatsapp_user_ids(self.company_id)

    def _get_agixt_user_id(self, phone_number: str) -> Optional[str]:
        """Get the AGiXT user ID for a phone number."""
        if phone_number not in self._user_id_cache:
            self._refresh_user_id_cache()
        return self._user_id_cache.get(phone_number)

    async def _get_user_token(self, phone_number: str) -> Optional[str]:
        """Get an impersonation token for a user."""
        agixt_user_id = self._get_agixt_user_id(phone_number)
        if not agixt_user_id:
            return None

        try:
            return impersonate_user(agixt_user_id)
        except Exception as e:
            # Log error without exposing sensitive phone number
            masked_phone = "****" + phone_number[-4:] if phone_number else "unknown"
            logger.error(f"Error impersonating user {masked_phone}: {type(e).__name__}")
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
                    setting_name="whatsapp_default_agent",
                )
                .first()
            )
            if setting and setting.setting_value:
                return setting.setting_value
        return "XT"

    def _get_selected_agent(self, phone_number: str) -> Optional[str]:
        """Get the selected agent for a user, or None for default."""
        return self.user_agents.get(phone_number)

    async def _send_message(self, recipient_phone: str, text: str) -> bool:
        """
        Send a text message via WhatsApp.

        Args:
            recipient_phone: Recipient's phone number
            text: Message text

        Returns:
            True if successful
        """
        try:
            # WhatsApp has a 4096 character limit
            if len(text) > 4096:
                chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
                for chunk in chunks:
                    await self._send_message(recipient_phone, chunk)
                return True

            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient_phone,
                "type": "text",
                "text": {"body": text},
            }

            response = requests.post(
                f"{self.base_url}/{self.phone_number_id}/messages",
                headers=self._get_headers(),
                json=data,
            )

            if response.status_code == 200:
                return True
            else:
                # Log status code only, not response text which may contain sensitive data
                logger.error(
                    f"Failed to send WhatsApp message: status_code={response.status_code}"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return False

    async def _mark_as_read(self, message_id: str):
        """Mark a message as read."""
        try:
            data = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            }

            requests.post(
                f"{self.base_url}/{self.phone_number_id}/messages",
                headers=self._get_headers(),
                json=data,
            )
        except:
            pass

    async def _handle_admin_command(
        self, phone_number: str, command: str
    ) -> Optional[str]:
        """
        Handle admin commands.

        Args:
            phone_number: User's phone number
            command: Command text

        Returns:
            Response message or None if not a command
        """
        cmd = command.lower().strip()

        if cmd == "!help":
            lines = ["📋 *Available Commands:*"]
            for cmd_name, cmd_desc in self.ADMIN_COMMANDS.items():
                lines.append(f"• {cmd_name} - {cmd_desc}")
            return "\n".join(lines)

        elif cmd == "!list":
            agents = await self._get_available_agents()
            current = (
                self._get_selected_agent(phone_number)
                or await self._get_default_agent()
            )
            lines = ["🤖 *Available Agents:*"]
            for agent in agents:
                marker = "✓ " if agent == current else "  "
                lines.append(f"{marker}{agent}")
            lines.append(f"\n📍 Current: {current}")
            lines.append("Use !select <agent> to switch")
            return "\n".join(lines)

        elif cmd.startswith("!select "):
            agent_name = command[8:].strip()
            agents = await self._get_available_agents()

            matched = None
            for agent in agents:
                if agent.lower() == agent_name.lower():
                    matched = agent
                    break

            if matched:
                self.user_agents[phone_number] = matched
                return f"✓ Switched to agent: {matched}"
            else:
                return f"❌ Agent '{agent_name}' not found. Use !list to see available agents."

        elif cmd == "!clear":
            if phone_number in self.user_agents:
                del self.user_agents[phone_number]
            return "✓ Conversation cleared. Your next message will start fresh."

        elif cmd == "!status":
            uptime = ""
            if self.started_at:
                delta = datetime.utcnow() - self.started_at
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime = f"{hours}h {minutes}m {seconds}s"

            current_agent = (
                self._get_selected_agent(phone_number)
                or await self._get_default_agent()
            )

            return (
                f"📊 *Bot Status*\n"
                f"Phone: {self.display_phone_number or self.phone_number_id}\n"
                f"Company: {self.company_name}\n"
                f"Uptime: {uptime}\n"
                f"Messages: {self.messages_processed}\n"
                f"Your Agent: {current_agent}"
            )

        return None

    async def process_message(
        self,
        message_id: str,
        sender_phone: str,
        text: str,
        timestamp: str,
    ):
        """
        Process an incoming WhatsApp message.

        Args:
            message_id: WhatsApp message ID
            sender_phone: Sender's phone number
            text: Message text
            timestamp: Message timestamp
        """
        # Skip if already processed
        if message_id in self.processed_message_ids:
            return

        self.processed_message_ids.add(message_id)

        # Limit processed IDs to prevent memory growth
        if len(self.processed_message_ids) > 10000:
            self.processed_message_ids = set(list(self.processed_message_ids)[-5000:])

        logger.info(f"Processing WhatsApp message from {sender_phone}: {text[:100]}...")
        self.messages_processed += 1

        # Mark as read
        await self._mark_as_read(message_id)

        # Get AGiXT user ID for permission checks
        agixt_user_id = self._get_agixt_user_id(sender_phone)
        use_owner_context = False

        # Apply permission mode checks
        if self.bot_permission_mode == "owner_only":
            # Only the owner can interact
            if not agixt_user_id or agixt_user_id != self.bot_owner_id:
                return
        elif self.bot_permission_mode == "allowlist":
            # Only phone numbers in the allowlist can interact
            import re

            normalized_phone = re.sub(r"[^\d+]", "", sender_phone)
            if not normalized_phone.startswith("+"):
                normalized_phone = "+" + normalized_phone
            if normalized_phone not in self.bot_allowlist:
                logger.debug(
                    f"WhatsApp number {sender_phone} not in allowlist, ignoring"
                )
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

        try:
            # Check for admin commands - only allow for recognized users
            if text.startswith("!") and not use_owner_context:
                response = await self._handle_admin_command(sender_phone, text)
                if response:
                    await self._send_message(sender_phone, response)
                    return

            # Determine which agent to use
            agent_name = None

            if not self.bot_agent_id:
                # Get user's selected agent
                agent_name = self._get_selected_agent(sender_phone)
                if not agent_name:
                    agent_name = await self._get_default_agent()

            # Try to get user's token
            user_token = None
            if use_owner_context and self.bot_owner_id:
                user_token = impersonate_user(self.bot_owner_id)
            else:
                user_token = await self._get_user_token(sender_phone)

            # Build conversation name
            conversation_name = f"whatsapp-{sender_phone}-{self.company_id[:8]}"

            if user_token:
                # If bot has configured agent, resolve agent name
                if self.bot_agent_id:
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
                            sender_phone,
                            "Sorry, I'm having trouble connecting to my AI backend.",
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
                    # Convert markdown bold to WhatsApp bold
                    content = content.replace("**", "*")
                    await self._send_message(sender_phone, content)
                else:
                    await self._send_message(
                        sender_phone,
                        "I apologize, but I couldn't generate a response.",
                    )
            else:
                await self._send_message(
                    sender_phone,
                    "I apologize, but I couldn't generate a response.",
                )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._send_message(
                sender_phone,
                "I encountered an error processing your message. Please try again.",
            )

    async def process_button_reply(
        self, sender_phone: str, button_id: str, button_title: str
    ):
        """
        Process an interactive button reply.

        Args:
            sender_phone: Sender's phone number
            button_id: Button ID
            button_title: Button title text
        """
        logger.info(f"Processing button reply from {sender_phone}: {button_title}")
        # Treat button replies as regular messages with the button title
        await self.process_message(
            f"button_{button_id}_{datetime.utcnow().timestamp()}",
            sender_phone,
            button_title,
            str(datetime.utcnow().timestamp()),
        )

    async def process_list_reply(self, sender_phone: str, row_id: str, row_title: str):
        """
        Process an interactive list selection.

        Args:
            sender_phone: Sender's phone number
            row_id: Selected row ID
            row_title: Selected row title
        """
        logger.info(f"Processing list reply from {sender_phone}: {row_title}")
        await self.process_message(
            f"list_{row_id}_{datetime.utcnow().timestamp()}",
            sender_phone,
            row_title,
            str(datetime.utcnow().timestamp()),
        )

    def get_status(self) -> WhatsAppBotStatus:
        """Get current bot status."""
        return WhatsAppBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            phone_number_id=self.phone_number_id,
            display_phone_number=self.display_phone_number,
            started_at=self.started_at,
            is_running=self.is_running,
            messages_processed=self.messages_processed,
        )


class WhatsAppBotManager:
    """
    Manager for all company WhatsApp bots.

    Handles:
    - Webhook verification
    - Routing incoming webhook events to correct company bot
    - Managing bot configuration per phone number
    """

    def __init__(self):
        # Map phone_number_id -> CompanyWhatsAppBot
        self.bots: Dict[str, CompanyWhatsAppBot] = {}
        self._sync_lock = asyncio.Lock()

        # Webhook config
        self.verify_token = getenv("WHATSAPP_VERIFY_TOKEN")
        self.app_secret = getenv(
            "FACEBOOK_APP_SECRET"
        )  # Used for signature verification

        logger.info("WhatsApp Bot Manager initialized")

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify webhook subscription from WhatsApp/Meta.

        Args:
            mode: Should be 'subscribe'
            token: Verification token
            challenge: Challenge string to return

        Returns:
            Challenge string if valid, None if invalid
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return challenge
        else:
            logger.warning(f"WhatsApp webhook verification failed")
            return None

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify the X-Hub-Signature-256 header.

        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid
        """
        if not signature or not self.app_secret:
            return False

        expected = (
            "sha256="
            + hmac.new(
                self.app_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(signature, expected)

    async def sync_bots(self):
        """Synchronize running bots with database configuration."""
        async with self._sync_lock:
            try:
                with get_session() as session:
                    settings = (
                        session.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.setting_name
                            == "whatsapp_access_token",
                            CompanyExtensionSetting.setting_value.isnot(None),
                            CompanyExtensionSetting.setting_value != "",
                        )
                        .all()
                    )

                    active_phone_ids = set()

                    for setting in settings:
                        company = (
                            session.query(Company)
                            .filter_by(id=setting.company_id)
                            .first()
                        )
                        if not company:
                            continue

                        # Get phone number ID
                        phone_id_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="whatsapp_phone_number_id",
                            )
                            .first()
                        )

                        if not phone_id_setting or not phone_id_setting.setting_value:
                            continue

                        phone_number_id = phone_id_setting.setting_value
                        active_phone_ids.add(phone_number_id)

                        # Get display phone number
                        display_phone_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="whatsapp_display_phone_number",
                            )
                            .first()
                        )

                        display_phone = (
                            display_phone_setting.setting_value
                            if display_phone_setting
                            else ""
                        )

                        # Check if enabled
                        enabled_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="whatsapp_bot_enabled",
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
                            active_phone_ids.discard(phone_number_id)
                            continue

                        # Get new permission settings
                        agent_id_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="whatsapp_bot_agent_id",
                            )
                            .first()
                        )
                        permission_mode_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="whatsapp_bot_permission_mode",
                            )
                            .first()
                        )
                        owner_id_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="whatsapp_bot_owner_id",
                            )
                            .first()
                        )

                        # Create or update bot
                        if phone_number_id not in self.bots:
                            self.bots[phone_number_id] = CompanyWhatsAppBot(
                                company_id=str(setting.company_id),
                                company_name=company.name,
                                phone_number_id=phone_number_id,
                                access_token=setting.setting_value,
                                display_phone_number=display_phone,
                                bot_agent_id=(
                                    agent_id_setting.setting_value
                                    if agent_id_setting
                                    else None
                                ),
                                bot_permission_mode=(
                                    permission_mode_setting.setting_value
                                    if permission_mode_setting
                                    else "recognized_users"
                                ),
                                bot_owner_id=(
                                    owner_id_setting.setting_value
                                    if owner_id_setting
                                    else None
                                ),
                            )
                        else:
                            # Update token and settings if changed
                            bot = self.bots[phone_number_id]
                            if bot.access_token != setting.setting_value:
                                bot.access_token = setting.setting_value
                            # Update permission settings
                            bot.bot_agent_id = (
                                agent_id_setting.setting_value
                                if agent_id_setting
                                else None
                            )
                            bot.bot_permission_mode = (
                                permission_mode_setting.setting_value
                                if permission_mode_setting
                                else "recognized_users"
                            )
                            bot.bot_owner_id = (
                                owner_id_setting.setting_value
                                if owner_id_setting
                                else None
                            )

                    # Remove bots for phone numbers no longer configured
                    for phone_id in list(self.bots.keys()):
                        if phone_id not in active_phone_ids:
                            del self.bots[phone_id]
                            logger.info(f"Removed WhatsApp bot for phone {phone_id}")

            except Exception as e:
                logger.error(f"Error syncing WhatsApp bots: {e}")

    async def process_webhook(self, data: Dict):
        """
        Process incoming webhook event from WhatsApp.

        Args:
            data: Webhook payload
        """
        try:
            # Sync bots on each webhook
            await self.sync_bots()

            # WhatsApp sends events in a specific structure
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") != "messages":
                        continue

                    value = change.get("value", {})
                    metadata = value.get("metadata", {})
                    phone_number_id = metadata.get("phone_number_id")

                    # Find the bot for this phone number
                    bot = self.bots.get(phone_number_id)
                    if not bot:
                        # Log warning without exposing full phone number ID
                        masked_id = (
                            "****" + (phone_number_id or "")[-4:]
                            if phone_number_id
                            else "unknown"
                        )
                        logger.warning(f"No bot configured for phone {masked_id}")
                        continue

                    # Process messages
                    for message in value.get("messages", []):
                        message_id = message.get("id")
                        sender_phone = message.get("from")
                        timestamp = message.get("timestamp")
                        msg_type = message.get("type")

                        if msg_type == "text":
                            text = message.get("text", {}).get("body", "")
                            await bot.process_message(
                                message_id, sender_phone, text, timestamp
                            )

                        elif msg_type == "interactive":
                            interactive = message.get("interactive", {})
                            interactive_type = interactive.get("type")

                            if interactive_type == "button_reply":
                                button = interactive.get("button_reply", {})
                                await bot.process_button_reply(
                                    sender_phone,
                                    button.get("id", ""),
                                    button.get("title", ""),
                                )

                            elif interactive_type == "list_reply":
                                row = interactive.get("list_reply", {})
                                await bot.process_list_reply(
                                    sender_phone,
                                    row.get("id", ""),
                                    row.get("title", ""),
                                )

                        # Handle other message types as needed
                        # (image, document, audio, video, location, contacts, etc.)

        except Exception as e:
            logger.error(f"Error processing WhatsApp webhook: {e}")

    def get_all_status(self) -> List[WhatsAppBotStatus]:
        """Get status of all bots."""
        return [bot.get_status() for bot in self.bots.values()]

    def get_bot_status(self, phone_number_id: str) -> Optional[WhatsAppBotStatus]:
        """Get status of a specific phone number's bot."""
        bot = self.bots.get(phone_number_id)
        return bot.get_status() if bot else None


# Global manager instance
_manager: Optional[WhatsAppBotManager] = None


def get_whatsapp_bot_manager() -> Optional[WhatsAppBotManager]:
    """Get the global WhatsApp bot manager instance."""
    global _manager
    if _manager is None:
        _manager = WhatsAppBotManager()
    return _manager


async def process_whatsapp_webhook(data: Dict):
    """
    Process a WhatsApp webhook event.

    This should be called from your webhook endpoint.

    Args:
        data: Webhook payload from WhatsApp/Meta
    """
    manager = get_whatsapp_bot_manager()
    await manager.process_webhook(data)


def verify_whatsapp_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    """
    Verify WhatsApp webhook subscription.

    This should be called from your GET webhook endpoint.

    Args:
        mode: hub.mode parameter
        token: hub.verify_token parameter
        challenge: hub.challenge parameter

    Returns:
        Challenge string if valid, None if invalid
    """
    manager = get_whatsapp_bot_manager()
    return manager.verify_webhook(mode, token, challenge)


def verify_whatsapp_signature(payload: bytes, signature: str) -> bool:
    """
    Verify WhatsApp webhook signature.

    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header

    Returns:
        True if valid
    """
    manager = get_whatsapp_bot_manager()
    return manager.verify_signature(payload, signature)
