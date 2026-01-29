"""
Microsoft Email Bot Manager for AGiXT

This module manages Microsoft Email (Outlook) bots for multiple companies.
Each company can have its own email bot that monitors their inbox and responds
to emails using their configured AI agent.

The manager:
- Polls for new emails at configurable intervals
- Processes incoming emails and generates AI responses
- Sends replies via Microsoft Graph API
- Handles graceful shutdown
"""

import asyncio
import logging
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import requests

from DB import get_session, CompanyExtensionSetting, Company, User
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient

logger = logging.getLogger(__name__)


@dataclass
class BotStatus:
    """Status information for a company's Microsoft Email bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    messages_processed: int = 0
    last_check: Optional[datetime] = None


class CompanyMicrosoftEmailBot:
    """
    A Microsoft Email bot instance for a specific company.
    Polls for new emails and responds using the configured AI agent.

    Permission modes:
    - owner_only: Only emails from the owner's address are processed
    - recognized_users: Only emails from users with linked AGiXT accounts are processed
    - anyone: All incoming emails are processed
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        access_token: str,
        refresh_token: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        poll_interval: int = 60,
        bot_allowlist: str = None,
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.access_token = access_token
        self.refresh_token = refresh_token

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        self.poll_interval = poll_interval
        # Parse allowlist - comma-separated email addresses
        self.bot_allowlist = set()
        if bot_allowlist:
            for item in bot_allowlist.split(","):
                item = item.strip().lower()  # Normalize to lowercase
                if item:
                    self.bot_allowlist.add(item)

        self._is_running = False
        self._started_at: Optional[datetime] = None
        self._messages_processed = 0
        self._last_check: Optional[datetime] = None
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

        # Track processed message IDs to avoid duplicates
        self._processed_ids: set = set()

        # Microsoft Graph API settings
        self.client_id = getenv("MICROSOFT_CLIENT_ID")
        self.client_secret = getenv("MICROSOFT_CLIENT_SECRET")
        self.graph_base_url = "https://graph.microsoft.com/v1.0/me"

    def _refresh_access_token(self) -> bool:
        """Refresh the Microsoft access token."""
        try:
            response = requests.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "offline_access https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send",
                },
            )
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                if "refresh_token" in data:
                    self.refresh_token = data["refresh_token"]
                return True
            else:
                logger.error(f"Token refresh failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False

    def _make_graph_request(
        self, method: str, endpoint: str, **kwargs
    ) -> Optional[dict]:
        """Make a request to Microsoft Graph API with automatic token refresh."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        url = f"{self.graph_base_url}{endpoint}"
        response = requests.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            # Token expired, try to refresh
            if self._refresh_access_token():
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = requests.request(method, url, headers=headers, **kwargs)
            else:
                return None

        if response.status_code >= 200 and response.status_code < 300:
            if response.text:
                return response.json()
            return {}
        else:
            logger.error(f"Graph API error: {response.status_code} - {response.text}")
            return None

    def _get_unread_emails(self) -> list:
        """Get unread emails from inbox."""
        result = self._make_graph_request(
            "GET",
            "/mailFolders/inbox/messages",
            params={
                "$filter": "isRead eq false",
                "$top": 10,
                "$orderby": "receivedDateTime desc",
                "$select": "id,from,subject,body,receivedDateTime,conversationId",
            },
        )
        return result.get("value", []) if result else []

    def _mark_as_read(self, message_id: str):
        """Mark an email as read."""
        self._make_graph_request(
            "PATCH", f"/messages/{message_id}", json={"isRead": True}
        )

    def _send_reply(self, message_id: str, reply_content: str):
        """Send a reply to an email."""
        self._make_graph_request(
            "POST",
            f"/messages/{message_id}/reply",
            json={
                "message": {"body": {"contentType": "HTML", "content": reply_content}}
            },
        )

    def _get_sender_email(self, message: dict) -> str:
        """Extract sender email from message."""
        from_field = message.get("from", {})
        email_address = from_field.get("emailAddress", {})
        return email_address.get("address", "").lower()

    def _is_sender_allowed(self, sender_email: str) -> tuple:
        """
        Check if sender is allowed based on permission mode.
        Returns (allowed: bool, user_email: str or None)
        """
        sender_email_lower = sender_email.lower() if sender_email else ""
        
        if self.bot_permission_mode == "owner_only":
            if not self.bot_owner_id:
                return False, None
            # Check if sender is the owner
            with get_session() as db:
                owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                if owner and owner.email.lower() == sender_email_lower:
                    return True, owner.email
            return False, None

        elif self.bot_permission_mode == "allowlist":
            # Only emails from addresses in the allowlist are processed
            if sender_email_lower not in self.bot_allowlist:
                return False, None
            # Use owner context for allowlist users
            if self.bot_owner_id:
                with get_session() as db:
                    owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                    if owner:
                        return True, owner.email
            return False, None

        elif self.bot_permission_mode == "recognized_users":
            # Check if sender has an AGiXT account
            with get_session() as db:
                user = db.query(User).filter(User.email == sender_email).first()
                if user:
                    return True, user.email
            return False, None

        elif self.bot_permission_mode == "anyone":
            # Anyone can interact - use owner's context
            if self.bot_owner_id:
                with get_session() as db:
                    owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                    if owner:
                        return True, owner.email
            return False, None

        return False, None

    async def _process_email(self, message: dict):
        """Process a single email and generate a response."""
        message_id = message.get("id")
        if message_id in self._processed_ids:
            return

        sender_email = self._get_sender_email(message)
        allowed, user_email = self._is_sender_allowed(sender_email)

        if not allowed:
            logger.debug(f"Email from {sender_email} not allowed by permission mode")
            self._mark_as_read(message_id)
            self._processed_ids.add(message_id)
            return

        try:
            # Get the email content
            subject = message.get("subject", "No Subject")
            body = message.get("body", {}).get("content", "")

            # Clean HTML from body if needed
            import re

            body_text = re.sub(r"<[^>]+>", "", body).strip()

            # Create prompt from email
            prompt = f"Subject: {subject}\n\nMessage:\n{body_text}"

            # Get JWT for the user
            user_jwt = impersonate_user(user_email)
            agixt = InternalClient(api_key=user_jwt, user=user_email)

            # Determine agent to use
            agent_name = None
            if self.bot_agent_id:
                agents = agixt.get_agents()
                for agent in agents:
                    if isinstance(agent, dict) and str(agent.get("id")) == str(
                        self.bot_agent_id
                    ):
                        agent_name = agent.get("name")
                        break

            if not agent_name:
                agents = agixt.get_agents()
                if agents:
                    agent_name = (
                        agents[0].get("name", "XT")
                        if isinstance(agents[0], dict)
                        else agents[0]
                    )
                else:
                    agent_name = "XT"

            # Create conversation name
            conversation_name = (
                f"Email-{sender_email}-{message.get('conversationId', message_id)[:8]}"
            )

            # Get response from agent
            response = agixt.chat(
                agent_name=agent_name,
                user_input=prompt,
                conversation_name=conversation_name,
            )

            if response:
                # Format response as HTML
                html_response = f"<p>{response.replace(chr(10), '<br>')}</p>"
                self._send_reply(message_id, html_response)
                self._messages_processed += 1
                logger.info(f"Replied to email from {sender_email}")

            self._mark_as_read(message_id)
            self._processed_ids.add(message_id)

        except Exception as e:
            logger.error(f"Error processing email {message_id}: {e}")
            self._mark_as_read(message_id)
            self._processed_ids.add(message_id)

    async def _poll_loop(self):
        """Main polling loop for checking emails."""
        while not self._stop_event.is_set():
            try:
                self._last_check = datetime.now()
                emails = self._get_unread_emails()

                for email in emails:
                    if self._stop_event.is_set():
                        break
                    await self._process_email(email)

            except Exception as e:
                logger.error(f"Error in email poll loop for {self.company_name}: {e}")

            # Wait for next poll interval
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.poll_interval
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                continue  # Timeout, continue polling

    async def start(self):
        """Start the email bot."""
        if self._is_running:
            return

        self._is_running = True
        self._started_at = datetime.now()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"Microsoft Email bot started for {self.company_name}")

    async def stop(self):
        """Stop the email bot."""
        self._stop_event.set()
        self._is_running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

        logger.info(f"Microsoft Email bot stopped for {self.company_name}")

    def get_status(self) -> BotStatus:
        """Get current bot status."""
        return BotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            started_at=self._started_at,
            is_running=self._is_running,
            messages_processed=self._messages_processed,
            last_check=self._last_check,
        )


class MicrosoftEmailBotManager:
    """
    Manages Microsoft Email bots for all companies.
    Singleton pattern ensures only one manager exists.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._bots: Dict[str, CompanyMicrosoftEmailBot] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False
        logger.info("Microsoft Email Bot Manager initialized")

    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop."""
        try:
            loop = asyncio.get_running_loop()
            return loop
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def get_company_bot_config(self, company_id: str) -> Optional[dict]:
        """Get Microsoft Email bot configuration for a company."""
        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == "microsoft_email",
                )
                .all()
            )

            if not settings:
                return None

            config = {}
            for setting in settings:
                config[setting.setting_name] = setting.setting_value

            # Check if bot is enabled
            if config.get("microsoft_email_bot_enabled", "").lower() != "true":
                return None

            # Need access token and refresh token
            access_token = config.get("MICROSOFT_EMAIL_ACCESS_TOKEN")
            refresh_token = config.get("MICROSOFT_EMAIL_REFRESH_TOKEN")

            if not access_token or not refresh_token:
                return None

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "agent_id": config.get("microsoft_email_bot_agent_id"),
                "permission_mode": config.get(
                    "microsoft_email_bot_permission_mode", "recognized_users"
                ),
                "owner_id": config.get("microsoft_email_bot_owner_id"),
            }

    async def start_bot_for_company(self, company_id: str, company_name: str = None):
        """Start Microsoft Email bot for a specific company."""
        if company_id in self._bots:
            logger.debug(
                f"Microsoft Email bot already running for company {company_id}"
            )
            return

        config = self.get_company_bot_config(company_id)
        if not config:
            logger.debug(f"No valid Microsoft Email config for company {company_id}")
            return

        if not company_name:
            with get_session() as db:
                company = db.query(Company).filter(Company.id == company_id).first()
                company_name = company.name if company else "Unknown"

        bot = CompanyMicrosoftEmailBot(
            company_id=company_id,
            company_name=company_name,
            access_token=config["access_token"],
            refresh_token=config["refresh_token"],
            bot_agent_id=config.get("agent_id"),
            bot_permission_mode=config.get("permission_mode", "recognized_users"),
            bot_owner_id=config.get("owner_id"),
        )

        self._bots[company_id] = bot
        await bot.start()

    async def stop_bot_for_company(self, company_id: str):
        """Stop Microsoft Email bot for a specific company."""
        if company_id not in self._bots:
            return

        bot = self._bots[company_id]
        await bot.stop()
        del self._bots[company_id]

    async def sync_bots(self):
        """Sync bots with database configuration."""
        with get_session() as db:
            # Get all companies with Microsoft Email bot enabled
            enabled_settings = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.extension_name == "microsoft_email",
                    CompanyExtensionSetting.setting_name
                    == "microsoft_email_bot_enabled",
                    CompanyExtensionSetting.setting_value == "true",
                )
                .all()
            )

            enabled_company_ids = {s.company_id for s in enabled_settings}

        # Start bots for newly enabled companies
        for company_id in enabled_company_ids:
            if company_id not in self._bots:
                await self.start_bot_for_company(company_id)

        # Stop bots for disabled companies
        for company_id in list(self._bots.keys()):
            if company_id not in enabled_company_ids:
                await self.stop_bot_for_company(company_id)

    async def _periodic_sync(self):
        """Periodically sync bot configuration."""
        while self._running:
            try:
                await self.sync_bots()
            except Exception as e:
                logger.error(f"Error syncing Microsoft Email bots: {e}")

            await asyncio.sleep(60)  # Sync every minute

    async def start(self):
        """Start the bot manager."""
        if self._running:
            return

        self._running = True
        await self.sync_bots()
        self._sync_task = asyncio.create_task(self._periodic_sync())
        logger.info("Microsoft Email Bot Manager started")

    async def stop(self):
        """Stop all bots and the manager."""
        self._running = False

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        # Stop all bots
        for company_id in list(self._bots.keys()):
            await self.stop_bot_for_company(company_id)

        logger.info("Microsoft Email Bot Manager stopped")

    def get_bot_status(self, company_id: str) -> Optional[BotStatus]:
        """Get status for a specific company's bot."""
        bot = self._bots.get(company_id)
        if bot:
            return bot.get_status()
        return None

    def get_all_statuses(self) -> Dict[str, BotStatus]:
        """Get status for all running bots."""
        return {cid: bot.get_status() for cid, bot in self._bots.items()}


# Singleton instance
_manager: Optional[MicrosoftEmailBotManager] = None
_manager_lock = threading.Lock()


def get_microsoft_email_bot_manager() -> MicrosoftEmailBotManager:
    """Get or create the Microsoft Email bot manager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = MicrosoftEmailBotManager()
        return _manager


async def start_microsoft_email_bot_manager():
    """Start the Microsoft Email bot manager."""
    manager = get_microsoft_email_bot_manager()
    await manager.start()


async def stop_microsoft_email_bot_manager():
    """Stop the Microsoft Email bot manager."""
    global _manager
    if _manager:
        await _manager.stop()
        _manager = None
