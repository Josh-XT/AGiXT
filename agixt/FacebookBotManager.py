"""
Facebook Messenger Bot Manager for AGiXT

This module manages Facebook Messenger bots for multiple companies. Each company
can have its own Messenger bot instance running on their Facebook Page.

The manager:
- Handles incoming webhook events from Facebook
- Processes messages and generates AI responses
- Manages bot configuration per company/page
- Provides APIs for querying bot status

Facebook Messenger bots work via webhooks - Facebook sends POST requests when
messages arrive. This manager processes those webhook events.

Required environment variables:
- FACEBOOK_APP_ID: Facebook App ID
- FACEBOOK_APP_SECRET: Facebook App Secret
- FACEBOOK_VERIFY_TOKEN: Webhook verification token (you choose this)

Required setup:
1. Create Facebook App at developers.facebook.com
2. Add Messenger product to the app
3. Configure webhook URL pointing to your AGiXT instance
4. Subscribe webhook to messages, messaging_postbacks events
5. Get Page Access Token and configure in company settings
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
    ServerExtensionSetting,
    Company,
    UserOAuth,
    OAuthProvider,
)
from Globals import getenv
from MagicalAuth import impersonate_user, MagicalAuth
from InternalClient import InternalClient
from Models import ChatCompletions


def get_facebook_user_ids(company_id=None):
    """
    Get mapping of Facebook user IDs to AGiXT user IDs for a company.

    Args:
        company_id: Optional company ID to filter by

    Returns:
        Dict mapping Facebook user ID -> AGiXT user ID
    """
    user_ids = {}
    with get_session() as session:
        provider = session.query(OAuthProvider).filter_by(name="facebook").first()
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
class FacebookBotStatus:
    """Status information for a company's Facebook bot."""

    company_id: str
    company_name: str
    page_id: str
    page_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    messages_processed: int = 0


class CompanyFacebookBot:
    """
    Facebook Messenger bot instance for a single company/page.

    Handles:
    - Processing incoming messages from webhooks
    - Responding via Messenger Send API
    - User impersonation for personalized responses
    - Admin commands for bot management

    Permission modes:
    - owner_only: Only the user who set up the bot can interact
    - recognized_users: Only users with linked AGiXT accounts can interact (default)
    - anyone: Anyone can interact with the bot
    """

    # Admin commands that users can use in Messenger
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
        page_id: str,
        page_name: str,
        page_access_token: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
    ):
        """
        Initialize the Facebook bot for a company/page.

        Args:
            company_id: The company's UUID
            company_name: Human-readable company name
            page_id: Facebook Page ID
            page_name: Facebook Page name
            page_access_token: Page access token for Messenger API
            bot_agent_id: Specific agent ID to use (None = user's default)
            bot_permission_mode: Permission mode (owner_only, recognized_users, allowlist, anyone)
            bot_owner_id: User ID of who configured this bot
            bot_allowlist: Comma-separated Facebook user IDs (PSIDs) for allowlist mode
        """
        self.company_id = company_id
        self.company_name = company_name
        self.page_id = page_id
        self.page_name = page_name
        self.page_access_token = page_access_token

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        # Parse allowlist - comma-separated Facebook user IDs (PSIDs)
        self.bot_allowlist = set()
        if bot_allowlist:
            for item in bot_allowlist.split(","):
                item = item.strip()
                if item:
                    self.bot_allowlist.add(item)

        # Bot state
        self.is_running = True
        self.started_at = datetime.utcnow()
        self.messages_processed = self._load_messages_processed()
        self._unsaved_message_count = 0  # Track unsaved increments for batching

        # Track processed message IDs to avoid duplicates
        self.processed_message_ids: Set[str] = set()

        # User agent selections (Facebook user ID -> agent name)
        self.user_agents: Dict[str, str] = {}

        # Internal client for API calls
        self.internal_client = InternalClient()

        # Cache of Facebook user IDs to AGiXT user IDs
        self._user_id_cache: Dict[str, str] = {}

        logger.info(
            f"Initialized Facebook bot for company {company_name} ({company_id}), "
            f"page {page_name} ({page_id})"
        )

    def _load_messages_processed(self) -> int:
        """Load the messages_processed count from the database."""
        try:
            with get_session() as db:
                if self.company_id == "server":
                    # Server-level bot
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "facebook",
                            ServerExtensionSetting.setting_key
                            == "FACEBOOK_MESSAGES_PROCESSED",
                        )
                        .first()
                    )
                else:
                    # Company-level bot
                    setting = (
                        db.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == self.company_id,
                            CompanyExtensionSetting.extension_name == "facebook",
                            CompanyExtensionSetting.setting_key
                            == "FACEBOOK_MESSAGES_PROCESSED",
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
            with get_session() as db:
                if self.company_id == "server":
                    # Server-level bot
                    setting = (
                        db.query(ServerExtensionSetting)
                        .filter(
                            ServerExtensionSetting.extension_name == "facebook",
                            ServerExtensionSetting.setting_key
                            == "FACEBOOK_MESSAGES_PROCESSED",
                        )
                        .first()
                    )
                    if setting:
                        setting.setting_value = str(self.messages_processed)
                    else:
                        setting = ServerExtensionSetting(
                            extension_name="facebook",
                            setting_key="FACEBOOK_MESSAGES_PROCESSED",
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
                            CompanyExtensionSetting.extension_name == "facebook",
                            CompanyExtensionSetting.setting_key
                            == "FACEBOOK_MESSAGES_PROCESSED",
                        )
                        .first()
                    )
                    if setting:
                        setting.setting_value = str(self.messages_processed)
                    else:
                        setting = CompanyExtensionSetting(
                            company_id=self.company_id,
                            extension_name="facebook",
                            setting_key="FACEBOOK_MESSAGES_PROCESSED",
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

    def _refresh_user_id_cache(self):
        """Refresh the Facebook user ID to AGiXT user ID cache."""
        self._user_id_cache = get_facebook_user_ids(self.company_id)

    def _get_agixt_user_id(self, facebook_user_id: str) -> Optional[str]:
        """
        Get the AGiXT user ID for a Facebook user.

        Args:
            facebook_user_id: Facebook user ID

        Returns:
            AGiXT user ID or None if not found
        """
        if facebook_user_id not in self._user_id_cache:
            self._refresh_user_id_cache()
        return self._user_id_cache.get(facebook_user_id)

    async def _get_user_token(self, facebook_user_id: str) -> Optional[str]:
        """
        Get an impersonation token for a user.

        Args:
            facebook_user_id: Facebook user ID

        Returns:
            JWT token for the user or None
        """
        agixt_user_id = self._get_agixt_user_id(facebook_user_id)
        if not agixt_user_id:
            return None

        try:
            return impersonate_user(agixt_user_id)
        except Exception as e:
            logger.error(f"Error impersonating user {facebook_user_id}: {e}")
            return None

    async def _get_available_agents(self) -> List[str]:
        """Get list of available agents for this company."""
        try:
            with get_session() as session:
                company = session.query(Company).filter_by(id=self.company_id).first()
                if not company:
                    return ["XT"]

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
                    setting_name="facebook_default_agent",
                )
                .first()
            )
            if setting and setting.setting_value:
                return setting.setting_value
        return "XT"

    def _get_selected_agent(self, facebook_user_id: str) -> Optional[str]:
        """Get the selected agent for a user, or None for default."""
        return self.user_agents.get(facebook_user_id)

    async def _send_message(
        self,
        recipient_id: str,
        text: str,
        quick_replies: List[Dict] = None,
    ) -> bool:
        """
        Send a Messenger message.

        Args:
            recipient_id: Facebook user ID to send to
            text: Message text
            quick_replies: Optional quick reply buttons

        Returns:
            True if successful, False otherwise
        """
        try:
            # Messenger has a 2000 character limit per message
            if len(text) > 2000:
                # Split into chunks
                chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
                for i, chunk in enumerate(chunks):
                    # Only add quick replies to the last message
                    qr = quick_replies if i == len(chunks) - 1 else None
                    await self._send_message(recipient_id, chunk, qr)
                return True

            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": text},
                "messaging_type": "RESPONSE",
            }

            if quick_replies:
                payload["message"]["quick_replies"] = quick_replies

            response = requests.post(
                f"https://graph.facebook.com/v18.0/{self.page_id}/messages",
                params={"access_token": self.page_access_token},
                json=payload,
            )

            if response.status_code == 200:
                return True
            else:
                logger.error(
                    f"Failed to send Messenger message: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Error sending Messenger message: {e}")
            return False

    async def _send_typing_indicator(self, recipient_id: str, on: bool = True):
        """
        Send typing indicator to show the bot is processing.

        Args:
            recipient_id: Facebook user ID
            on: True to show typing, False to hide
        """
        try:
            payload = {
                "recipient": {"id": recipient_id},
                "sender_action": "typing_on" if on else "typing_off",
            }

            requests.post(
                f"https://graph.facebook.com/v18.0/{self.page_id}/messages",
                params={"access_token": self.page_access_token},
                json=payload,
            )
        except Exception as e:
            logger.debug(f"Failed to send typing indicator: {e}")

    async def _handle_admin_command(
        self, facebook_user_id: str, command: str
    ) -> Optional[str]:
        """
        Handle admin commands.

        Args:
            facebook_user_id: Facebook user ID who sent the command
            command: Command text

        Returns:
            Response message or None if not a command
        """
        cmd = command.lower().strip()

        if cmd == "!help":
            lines = ["📋 Available Commands:"]
            for cmd_name, cmd_desc in self.ADMIN_COMMANDS.items():
                lines.append(f"• {cmd_name} - {cmd_desc}")
            return "\n".join(lines)

        elif cmd == "!list":
            agents = await self._get_available_agents()
            current = (
                self._get_selected_agent(facebook_user_id)
                or await self._get_default_agent()
            )
            lines = ["🤖 Available Agents:"]
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
                self.user_agents[facebook_user_id] = matched
                return f"✓ Switched to agent: {matched}"
            else:
                return f"❌ Agent '{agent_name}' not found. Use !list to see available agents."

        elif cmd == "!clear":
            if facebook_user_id in self.user_agents:
                del self.user_agents[facebook_user_id]
            return "✓ Conversation cleared. Your next message will start fresh."

        elif cmd == "!status":
            uptime = ""
            if self.started_at:
                delta = datetime.utcnow() - self.started_at
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime = f"{hours}h {minutes}m {seconds}s"

            current_agent = (
                self._get_selected_agent(facebook_user_id)
                or await self._get_default_agent()
            )

            return (
                f"📊 Bot Status\n"
                f"Page: {self.page_name}\n"
                f"Company: {self.company_name}\n"
                f"Uptime: {uptime}\n"
                f"Messages: {self.messages_processed}\n"
                f"Your Agent: {current_agent}"
            )

        return None

    async def process_message(self, sender_id: str, message_id: str, text: str):
        """
        Process an incoming message from Messenger.

        Args:
            sender_id: Facebook user ID of sender
            message_id: Message ID
            text: Message text
        """
        # Skip if already processed
        if message_id in self.processed_message_ids:
            return

        self.processed_message_ids.add(message_id)

        # Limit processed IDs to prevent memory growth
        if len(self.processed_message_ids) > 10000:
            # Keep only the most recent 5000
            self.processed_message_ids = set(list(self.processed_message_ids)[-5000:])

        logger.info(f"Processing Messenger message from {sender_id}: {text[:100]}...")
        self.messages_processed += 1
        self._unsaved_message_count += 1
        # Save every 5 messages or on first message to batch DB writes
        if self._unsaved_message_count >= 5 or self.messages_processed == 1:
            self._save_messages_processed()

        # Get AGiXT user ID for permission checks
        agixt_user_id = self._get_agixt_user_id(sender_id)
        use_owner_context = False

        # Apply permission mode checks
        if self.bot_permission_mode == "owner_only":
            # Only the owner can interact
            if not agixt_user_id or agixt_user_id != self.bot_owner_id:
                return
        elif self.bot_permission_mode == "allowlist":
            # Only users in the allowlist can interact
            if str(sender_id) not in self.bot_allowlist:
                logger.debug(f"Facebook user {sender_id} not in allowlist, ignoring")
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

        # Show typing indicator
        await self._send_typing_indicator(sender_id, True)

        try:
            # Check for admin commands - only allow for recognized users
            if text.startswith("!") and not use_owner_context:
                response = await self._handle_admin_command(sender_id, text)
                if response:
                    await self._send_typing_indicator(sender_id, False)
                    await self._send_message(sender_id, response)
                    return

            # Determine which agent to use
            agent_name = None

            if not self.bot_agent_id:
                # Get user's selected agent
                agent_name = self._get_selected_agent(sender_id)
                if not agent_name:
                    agent_name = await self._get_default_agent()

            # Try to get user's token for personalized responses
            user_token = None
            if use_owner_context and self.bot_owner_id:
                user_token = impersonate_user(self.bot_owner_id)
            else:
                user_token = await self._get_user_token(sender_id)

            # Build conversation name
            conversation_name = f"fb-messenger-{sender_id}-{self.page_id[:8]}"

            if user_token:
                # User is linked - use their token
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
                # User not linked - use company default
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
                        await self._send_typing_indicator(sender_id, False)
                        await self._send_message(
                            sender_id,
                            "Sorry, I'm having trouble connecting to my AI backend.",
                        )
                        return

            # Generate response
            response = await chat.chat_completions(
                messages=[{"role": "user", "content": text}],
                conversation_name=conversation_name,
                context_results=10,
            )

            await self._send_typing_indicator(sender_id, False)

            if response and isinstance(response, dict):
                content = (
                    response.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if content:
                    await self._send_message(sender_id, content)
                else:
                    await self._send_message(
                        sender_id,
                        "I apologize, but I couldn't generate a response.",
                    )
            else:
                await self._send_message(
                    sender_id,
                    "I apologize, but I couldn't generate a response.",
                )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._send_typing_indicator(sender_id, False)
            await self._send_message(
                sender_id,
                "I encountered an error processing your message. Please try again.",
            )

    async def process_postback(self, sender_id: str, payload: str):
        """
        Process a postback event (button click).

        Args:
            sender_id: Facebook user ID
            payload: Postback payload string
        """
        logger.info(f"Processing postback from {sender_id}: {payload}")

        # Handle common postbacks
        if payload == "GET_STARTED":
            await self._send_message(
                sender_id,
                f"👋 Welcome! I'm the AI assistant for {self.company_name}.\n\n"
                f"You can chat with me about anything, or use these commands:\n"
                f"• !help - Show all commands\n"
                f"• !list - See available AI agents\n"
                f"• !select <agent> - Switch agents\n\n"
                f"How can I help you today?",
            )
        else:
            # Treat other postbacks as messages
            await self.process_message(sender_id, f"postback_{payload}", payload)

    def get_status(self) -> FacebookBotStatus:
        """Get current bot status."""
        return FacebookBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            page_id=self.page_id,
            page_name=self.page_name,
            started_at=self.started_at,
            is_running=self.is_running,
            messages_processed=self.messages_processed,
        )


class FacebookBotManager:
    """
    Manager for all company Facebook Messenger bots.

    Handles:
    - Webhook verification
    - Routing incoming webhook events to correct company bot
    - Managing bot configuration per page
    """

    def __init__(self):
        # Map page_id -> CompanyFacebookBot
        self.bots: Dict[str, CompanyFacebookBot] = {}
        self._sync_lock = asyncio.Lock()

        # Facebook app config
        self.app_secret = getenv("FACEBOOK_APP_SECRET")
        self.verify_token = getenv("FACEBOOK_VERIFY_TOKEN")

        logger.info("Facebook Bot Manager initialized")

    def verify_webhook(self, mode: str, token: str, challenge: str) -> Optional[str]:
        """
        Verify webhook subscription from Facebook.

        Args:
            mode: Should be 'subscribe'
            token: Verification token (should match FACEBOOK_VERIFY_TOKEN)
            challenge: Challenge string to return

        Returns:
            Challenge string if valid, None if invalid
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verified successfully")
            return challenge
        else:
            logger.warning(f"Webhook verification failed: mode={mode}, token={token}")
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
        """
        Synchronize running bots with database configuration.
        """
        async with self._sync_lock:
            try:
                with get_session() as session:
                    # Query for companies with Facebook page tokens
                    settings = (
                        session.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.setting_name
                            == "facebook_page_token",
                            CompanyExtensionSetting.setting_value.isnot(None),
                            CompanyExtensionSetting.setting_value != "",
                        )
                        .all()
                    )

                    active_page_ids = set()

                    for setting in settings:
                        company = (
                            session.query(Company)
                            .filter_by(id=setting.company_id)
                            .first()
                        )
                        if not company:
                            continue

                        # Get page ID
                        page_id_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="facebook_page_id",
                            )
                            .first()
                        )

                        if not page_id_setting or not page_id_setting.setting_value:
                            continue

                        page_id = page_id_setting.setting_value
                        active_page_ids.add(page_id)

                        # Get page name
                        page_name_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="facebook_page_name",
                            )
                            .first()
                        )

                        page_name = (
                            page_name_setting.setting_value
                            if page_name_setting
                            else f"Page {page_id}"
                        )

                        # Check if enabled
                        enabled_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="facebook_bot_enabled",
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
                            active_page_ids.discard(page_id)
                            continue

                        # Get new permission settings
                        agent_id_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="facebook_bot_agent_id",
                            )
                            .first()
                        )
                        permission_mode_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="facebook_bot_permission_mode",
                            )
                            .first()
                        )
                        owner_id_setting = (
                            session.query(CompanyExtensionSetting)
                            .filter_by(
                                company_id=setting.company_id,
                                setting_name="facebook_bot_owner_id",
                            )
                            .first()
                        )

                        # Create or update bot
                        if page_id not in self.bots:
                            self.bots[page_id] = CompanyFacebookBot(
                                company_id=str(setting.company_id),
                                company_name=company.name,
                                page_id=page_id,
                                page_name=page_name,
                                page_access_token=setting.setting_value,
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
                            bot = self.bots[page_id]
                            if bot.page_access_token != setting.setting_value:
                                bot.page_access_token = setting.setting_value
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

                    # Remove bots for pages no longer configured
                    for page_id in list(self.bots.keys()):
                        if page_id not in active_page_ids:
                            # Save message count before removing
                            bot = self.bots[page_id]
                            if (
                                hasattr(bot, "_unsaved_message_count")
                                and bot._unsaved_message_count > 0
                            ):
                                bot._save_messages_processed()
                            del self.bots[page_id]
                            logger.info(f"Removed Facebook bot for page {page_id}")

            except Exception as e:
                logger.error(f"Error syncing Facebook bots: {e}")

    async def process_webhook(self, data: Dict):
        """
        Process incoming webhook event from Facebook.

        Args:
            data: Webhook payload
        """
        try:
            # Sync bots on each webhook (lightweight if no changes)
            await self.sync_bots()

            # Facebook sends events in batches
            for entry in data.get("entry", []):
                page_id = entry.get("id")

                # Find the bot for this page
                bot = self.bots.get(page_id)
                if not bot:
                    logger.warning(f"No bot configured for page {page_id}")
                    continue

                # Process messaging events
                for messaging_event in entry.get("messaging", []):
                    sender_id = messaging_event.get("sender", {}).get("id")

                    # Skip messages from the page itself
                    if sender_id == page_id:
                        continue

                    # Handle message
                    if "message" in messaging_event:
                        message = messaging_event["message"]
                        message_id = message.get("mid", "")
                        text = message.get("text", "")

                        if text:
                            await bot.process_message(sender_id, message_id, text)

                    # Handle postback (button clicks)
                    elif "postback" in messaging_event:
                        payload = messaging_event["postback"].get("payload", "")
                        await bot.process_postback(sender_id, payload)

        except Exception as e:
            logger.error(f"Error processing webhook: {e}")

    def get_all_status(self) -> List[FacebookBotStatus]:
        """Get status of all bots."""
        return [bot.get_status() for bot in self.bots.values()]

    def get_bot_status(self, page_id: str) -> Optional[FacebookBotStatus]:
        """Get status of a specific page's bot."""
        bot = self.bots.get(page_id)
        return bot.get_status() if bot else None


# Global manager instance
_manager: Optional[FacebookBotManager] = None


def get_facebook_bot_manager() -> Optional[FacebookBotManager]:
    """Get the global Facebook bot manager instance."""
    global _manager
    if _manager is None:
        _manager = FacebookBotManager()
    return _manager


async def process_facebook_webhook(data: Dict):
    """
    Process a Facebook webhook event.

    This should be called from your webhook endpoint.

    Args:
        data: Webhook payload from Facebook
    """
    manager = get_facebook_bot_manager()
    await manager.process_webhook(data)


def verify_facebook_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    """
    Verify Facebook webhook subscription.

    This should be called from your GET webhook endpoint.

    Args:
        mode: hub.mode parameter
        token: hub.verify_token parameter
        challenge: hub.challenge parameter

    Returns:
        Challenge string if valid, None if invalid
    """
    manager = get_facebook_bot_manager()
    return manager.verify_webhook(mode, token, challenge)


def verify_facebook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Facebook webhook signature.

    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header

    Returns:
        True if valid
    """
    manager = get_facebook_bot_manager()
    return manager.verify_signature(payload, signature)
