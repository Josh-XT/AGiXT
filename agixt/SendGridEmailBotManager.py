"""
SendGrid Email Bot Manager for AGiXT

This module manages SendGrid Email bots for multiple companies.
SendGrid uses inbound parse webhooks to receive emails, so this manager
primarily coordinates webhook handling and maintains state.

The manager:
- Processes incoming emails via SendGrid Inbound Parse webhook
- Generates AI responses and sends replies
- Tracks email processing status
"""

import asyncio
import logging
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from DB import get_session, CompanyExtensionSetting, Company, User
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from fastapi import APIRouter, Request, Form, HTTPException
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger(__name__)


@dataclass
class BotStatus:
    """Status information for a company's SendGrid Email bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    messages_processed: int = 0


class CompanySendGridEmailBot:
    """
    A SendGrid Email bot instance for a specific company.
    Handles incoming emails via webhook and responds using the configured AI agent.

    Permission modes:
    - owner_only: Only emails from the owner's address are processed
    - recognized_users: Only emails from users with linked AGiXT accounts are processed
    - anyone: All incoming emails are processed
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        api_key: str,
        from_email: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.api_key = api_key
        self.from_email = from_email

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
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

        # SendGrid client
        self.sg_client = SendGridAPIClient(api_key)

    def _is_sender_allowed(self, sender_email: str) -> tuple:
        """
        Check if sender is allowed based on permission mode.
        Returns (allowed: bool, user_email: str or None)
        """
        sender_email = sender_email.lower()

        if self.bot_permission_mode == "owner_only":
            if not self.bot_owner_id:
                return False, None
            with get_session() as db:
                owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                if owner and owner.email.lower() == sender_email:
                    return True, owner.email
            return False, None

        elif self.bot_permission_mode == "allowlist":
            # Only emails from addresses in the allowlist are processed
            if sender_email not in self.bot_allowlist:
                return False, None
            # Use owner context for allowlist users
            if self.bot_owner_id:
                with get_session() as db:
                    owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                    if owner:
                        return True, owner.email
            return False, None

        elif self.bot_permission_mode == "recognized_users":
            with get_session() as db:
                user = db.query(User).filter(User.email == sender_email).first()
                if user:
                    return True, user.email
            return False, None

        elif self.bot_permission_mode == "anyone":
            if self.bot_owner_id:
                with get_session() as db:
                    owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                    if owner:
                        return True, owner.email
            return False, None

        return False, None

    def _send_reply(self, to_email: str, subject: str, content: str):
        """Send a reply email via SendGrid."""
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        message = Mail(
            from_email=self.from_email,
            to_emails=to_email,
            subject=subject,
            html_content=content,
        )

        try:
            response = self.sg_client.send(message)
            logger.info(
                f"SendGrid reply sent to {to_email}, status: {response.status_code}"
            )
        except Exception as e:
            logger.error(f"Failed to send SendGrid reply: {e}")

    async def process_incoming_email(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body_text: str,
    ):
        """Process an incoming email received via webhook."""
        allowed, user_email = self._is_sender_allowed(from_email)

        if not allowed:
            logger.debug(f"Email from {from_email} not allowed by permission mode")
            return

        try:
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
            conversation_name = f"SendGrid-{from_email}-{subject[:20]}"

            # Get response from agent
            response = agixt.chat(
                agent_name=agent_name,
                user_input=prompt,
                conversation_name=conversation_name,
            )

            if response:
                html_response = f"<p>{response.replace(chr(10), '<br>')}</p>"
                self._send_reply(from_email, subject, html_response)
                self._messages_processed += 1
                logger.info(f"Replied to SendGrid email from {from_email}")

        except Exception as e:
            logger.error(f"Error processing SendGrid email: {e}")

    def start(self):
        """Mark the bot as running."""
        self._is_running = True
        self._started_at = datetime.now()
        logger.info(f"SendGrid Email bot started for {self.company_name}")

    def stop(self):
        """Mark the bot as stopped."""
        self._is_running = False
        logger.info(f"SendGrid Email bot stopped for {self.company_name}")

    def get_status(self) -> BotStatus:
        """Get current bot status."""
        return BotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            started_at=self._started_at,
            is_running=self._is_running,
            messages_processed=self._messages_processed,
        )


class SendGridEmailBotManager:
    """
    Manages SendGrid Email bots for all companies.
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
        self._bots: Dict[str, CompanySendGridEmailBot] = {}
        self._running = False

        # Map from to_email to company_id for webhook routing
        self._email_to_company: Dict[str, str] = {}

        logger.info("SendGrid Email Bot Manager initialized")

    def get_company_bot_config(self, company_id: str) -> Optional[dict]:
        """Get SendGrid Email bot configuration for a company."""
        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == "sendgrid_email",
                )
                .all()
            )

            if not settings:
                return None

            config = {}
            for setting in settings:
                config[setting.setting_name] = setting.setting_value

            if config.get("sendgrid_email_bot_enabled", "").lower() != "true":
                return None

            api_key = config.get("SENDGRID_API_KEY")
            from_email = config.get("SENDGRID_EMAIL")

            if not api_key or not from_email:
                return None

            return {
                "api_key": api_key,
                "from_email": from_email,
                "agent_id": config.get("sendgrid_email_bot_agent_id"),
                "permission_mode": config.get(
                    "sendgrid_email_bot_permission_mode", "recognized_users"
                ),
                "owner_id": config.get("sendgrid_email_bot_owner_id"),
            }

    def start_bot_for_company(self, company_id: str, company_name: str = None):
        """Start SendGrid Email bot for a specific company."""
        if company_id in self._bots:
            logger.debug(f"SendGrid Email bot already running for company {company_id}")
            return

        config = self.get_company_bot_config(company_id)
        if not config:
            logger.debug(f"No valid SendGrid Email config for company {company_id}")
            return

        if not company_name:
            with get_session() as db:
                company = db.query(Company).filter(Company.id == company_id).first()
                company_name = company.name if company else "Unknown"

        bot = CompanySendGridEmailBot(
            company_id=company_id,
            company_name=company_name,
            api_key=config["api_key"],
            from_email=config["from_email"],
            bot_agent_id=config.get("agent_id"),
            bot_permission_mode=config.get("permission_mode", "recognized_users"),
            bot_owner_id=config.get("owner_id"),
        )

        self._bots[company_id] = bot
        self._email_to_company[config["from_email"].lower()] = company_id
        bot.start()

    def stop_bot_for_company(self, company_id: str):
        """Stop SendGrid Email bot for a specific company."""
        if company_id not in self._bots:
            return

        bot = self._bots[company_id]

        # Remove email mapping
        for email, cid in list(self._email_to_company.items()):
            if cid == company_id:
                del self._email_to_company[email]

        bot.stop()
        del self._bots[company_id]

    def sync_bots(self):
        """Sync bots with database configuration."""
        with get_session() as db:
            enabled_settings = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.extension_name == "sendgrid_email",
                    CompanyExtensionSetting.setting_name
                    == "sendgrid_email_bot_enabled",
                    CompanyExtensionSetting.setting_value == "true",
                )
                .all()
            )

            enabled_company_ids = {s.company_id for s in enabled_settings}

        for company_id in enabled_company_ids:
            if company_id not in self._bots:
                self.start_bot_for_company(company_id)

        for company_id in list(self._bots.keys()):
            if company_id not in enabled_company_ids:
                self.stop_bot_for_company(company_id)

    def get_bot_for_email(self, to_email: str) -> Optional[CompanySendGridEmailBot]:
        """Get the bot responsible for handling emails to a specific address."""
        company_id = self._email_to_company.get(to_email.lower())
        if company_id:
            return self._bots.get(company_id)
        return None

    async def handle_inbound_webhook(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body_text: str,
    ):
        """Handle incoming email from SendGrid Inbound Parse webhook."""
        bot = self.get_bot_for_email(to_email)
        if not bot:
            logger.warning(f"No bot configured for email: {to_email}")
            return

        await bot.process_incoming_email(from_email, to_email, subject, body_text)

    def start(self):
        """Start the bot manager."""
        if self._running:
            return

        self._running = True
        self.sync_bots()
        logger.info("SendGrid Email Bot Manager started")

    def stop(self):
        """Stop all bots and the manager."""
        self._running = False

        for company_id in list(self._bots.keys()):
            self.stop_bot_for_company(company_id)

        logger.info("SendGrid Email Bot Manager stopped")

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
_manager: Optional[SendGridEmailBotManager] = None
_manager_lock = threading.Lock()


def get_sendgrid_email_bot_manager() -> SendGridEmailBotManager:
    """Get or create the SendGrid Email bot manager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = SendGridEmailBotManager()
        return _manager


def start_sendgrid_email_bot_manager():
    """Start the SendGrid Email bot manager."""
    manager = get_sendgrid_email_bot_manager()
    manager.start()


def stop_sendgrid_email_bot_manager():
    """Stop the SendGrid Email bot manager."""
    global _manager
    if _manager:
        _manager.stop()
        _manager = None


# FastAPI router for SendGrid Inbound Parse webhook
sendgrid_webhook_router = APIRouter(
    prefix="/webhooks/sendgrid", tags=["SendGrid Webhooks"]
)


@sendgrid_webhook_router.post("/inbound")
async def sendgrid_inbound_webhook(
    request: Request,
    from_email: str = Form(..., alias="from"),
    to: str = Form(...),
    subject: str = Form(default=""),
    text: str = Form(default=""),
    html: str = Form(default=""),
):
    """
    Handle incoming email from SendGrid Inbound Parse webhook.

    SendGrid sends POST requests with form data containing:
    - from: Sender email
    - to: Recipient email
    - subject: Email subject
    - text: Plain text body
    - html: HTML body (optional)
    """
    manager = get_sendgrid_email_bot_manager()

    # Use text body, or extract from HTML if not available
    body_text = text
    if not body_text and html:
        import re

        body_text = re.sub(r"<[^>]+>", "", html).strip()

    await manager.handle_inbound_webhook(
        from_email=from_email,
        to_email=to,
        subject=subject,
        body_text=body_text,
    )

    return {"status": "ok"}
