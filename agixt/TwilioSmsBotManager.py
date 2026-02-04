"""
Twilio SMS Bot Manager for AGiXT

This module manages Twilio SMS bots for multiple companies.
Each company can have its own SMS bot that handles incoming text messages
and responds using their configured AI agent.

The manager:
- Processes incoming SMS via Twilio webhook
- Generates AI responses and sends replies
- Tracks SMS processing status
- Respects permission modes for access control
"""

import asyncio
import logging
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from DB import get_session, CompanyExtensionSetting, Company, User, UserPreferences
from Globals import getenv
from MagicalAuth import impersonate_user
from InternalClient import InternalClient
from fastapi import APIRouter, Request, Form, Response
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

logger = logging.getLogger(__name__)


@dataclass
class BotStatus:
    """Status information for a company's Twilio SMS bot."""

    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    messages_processed: int = 0


class CompanyTwilioSmsBot:
    """
    A Twilio SMS bot instance for a specific company.
    Handles incoming SMS messages and responds using the configured AI agent.

    Permission modes:
    - owner_only: Only SMS from the owner's phone number are processed
    - recognized_users: Only SMS from users with linked phone numbers are processed
    - anyone: All incoming SMS are processed
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        account_sid: str,
        auth_token: str,
        phone_number: str,
        bot_agent_id: str = None,
        bot_permission_mode: str = "recognized_users",
        bot_owner_id: str = None,
        bot_allowlist: str = None,
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.phone_number = phone_number

        # Bot configuration
        self.bot_agent_id = bot_agent_id
        self.bot_permission_mode = bot_permission_mode
        self.bot_owner_id = bot_owner_id
        # Parse allowlist - comma-separated phone numbers
        self.bot_allowlist = set()
        if bot_allowlist:
            for item in bot_allowlist.split(","):
                item = item.strip()
                if item:
                    self.bot_allowlist.add(self._normalize_phone_static(item))

        self._is_running = False
        self._started_at: Optional[datetime] = None
        self._messages_processed = 0

        # Twilio client
        self.twilio_client = Client(account_sid, auth_token)

    @staticmethod
    def _normalize_phone_static(phone: str) -> str:
        """Static method to normalize phone number for comparison."""
        import re

        phone = re.sub(r"[^\d+]", "", phone)
        if not phone.startswith("+"):
            phone = "+" + phone
        return phone

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for comparison."""
        # Remove all non-digit characters except +
        import re

        phone = re.sub(r"[^\d+]", "", phone)
        if not phone.startswith("+"):
            phone = "+" + phone
        return phone

    def _get_user_by_phone(self, phone_number: str) -> Optional[User]:
        """Find a user by their phone number preference."""
        normalized = self._normalize_phone(phone_number)

        with get_session() as db:
            # Search user preferences for matching phone number
            pref = (
                db.query(UserPreferences)
                .filter(UserPreferences.pref_key == "phone_number")
                .all()
            )

            for p in pref:
                if self._normalize_phone(p.pref_value) == normalized:
                    user = db.query(User).filter(User.id == p.user_id).first()
                    if user:
                        return user

        return None

    def _is_sender_allowed(self, from_phone: str) -> tuple:
        """
        Check if sender is allowed based on permission mode.
        Returns (allowed: bool, user_email: str or None)
        """
        from_phone = self._normalize_phone(from_phone)

        if self.bot_permission_mode == "owner_only":
            if not self.bot_owner_id:
                return False, None

            with get_session() as db:
                owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                if not owner:
                    return False, None

                # Check if owner's phone matches
                owner_phone_pref = (
                    db.query(UserPreferences)
                    .filter(
                        UserPreferences.user_id == self.bot_owner_id,
                        UserPreferences.pref_key == "phone_number",
                    )
                    .first()
                )

                if owner_phone_pref:
                    owner_phone = self._normalize_phone(owner_phone_pref.pref_value)
                    if owner_phone == from_phone:
                        return True, owner.email

            return False, None

        elif self.bot_permission_mode == "allowlist":
            # Only SMS from phone numbers in the allowlist are processed
            if from_phone not in self.bot_allowlist:
                return False, None
            # Use owner context for allowlist users
            if self.bot_owner_id:
                with get_session() as db:
                    owner = db.query(User).filter(User.id == self.bot_owner_id).first()
                    if owner:
                        return True, owner.email
            return False, None

        elif self.bot_permission_mode == "recognized_users":
            user = self._get_user_by_phone(from_phone)
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

    def _send_sms(self, to_phone: str, message: str):
        """Send an SMS reply."""
        try:
            self.twilio_client.messages.create(
                body=message,
                from_=self.phone_number,
                to=to_phone,
            )
            logger.info(f"SMS sent to {to_phone}")
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")

    async def process_incoming_sms(
        self,
        from_phone: str,
        to_phone: str,
        body: str,
    ) -> Optional[str]:
        """
        Process an incoming SMS received via webhook.
        Returns the response message or None if not allowed.
        """
        allowed, user_email = self._is_sender_allowed(from_phone)

        if not allowed:
            logger.debug(f"SMS from {from_phone} not allowed by permission mode")
            return None

        try:
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

            # Create conversation name using phone number
            conversation_name = f"SMS-{from_phone}"

            # Get response from agent
            response = agixt.chat(
                agent_name=agent_name,
                user_input=body,
                conversation_name=conversation_name,
            )

            if response:
                self._messages_processed += 1
                logger.info(f"Replied to SMS from {from_phone}")
                return response

        except Exception as e:
            logger.error(f"Error processing SMS: {e}")

        return None

    def start(self):
        """Mark the bot as running."""
        self._is_running = True
        self._started_at = datetime.now()
        logger.info(f"Twilio SMS bot started for {self.company_name}")

    def stop(self):
        """Mark the bot as stopped."""
        self._is_running = False
        logger.info(f"Twilio SMS bot stopped for {self.company_name}")

    def get_status(self) -> BotStatus:
        """Get current bot status."""
        return BotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            started_at=self._started_at,
            is_running=self._is_running,
            messages_processed=self._messages_processed,
        )


class TwilioSmsBotManager:
    """
    Manages Twilio SMS bots for all companies.
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
        self._bots: Dict[str, CompanyTwilioSmsBot] = {}
        self._running = False

        # Map from phone number to company_id for webhook routing
        self._phone_to_company: Dict[str, str] = {}

        logger.info("Twilio SMS Bot Manager initialized")

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for comparison."""
        import re

        phone = re.sub(r"[^\d+]", "", phone)
        if not phone.startswith("+"):
            phone = "+" + phone
        return phone

    def get_company_bot_config(self, company_id: str) -> Optional[dict]:
        """Get Twilio SMS bot configuration for a company."""
        with get_session() as db:
            settings = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.company_id == company_id,
                    CompanyExtensionSetting.extension_name == "twilio_sms",
                )
                .all()
            )

            if not settings:
                return None

            config = {}
            for setting in settings:
                config[setting.setting_name] = setting.setting_value

            if config.get("twilio_sms_bot_enabled", "").lower() != "true":
                return None

            account_sid = config.get("TWILIO_ACCOUNT_SID")
            auth_token = config.get("TWILIO_AUTH_TOKEN")
            phone_number = config.get("TWILIO_PHONE_NUMBER")

            if not account_sid or not auth_token or not phone_number:
                return None

            return {
                "account_sid": account_sid,
                "auth_token": auth_token,
                "phone_number": phone_number,
                "agent_id": config.get("twilio_sms_bot_agent_id"),
                "permission_mode": config.get(
                    "twilio_sms_bot_permission_mode", "recognized_users"
                ),
                "owner_id": config.get("twilio_sms_bot_owner_id"),
            }

    def start_bot_for_company(self, company_id: str, company_name: str = None):
        """Start Twilio SMS bot for a specific company."""
        if company_id in self._bots:
            logger.debug(f"Twilio SMS bot already running for company {company_id}")
            return

        config = self.get_company_bot_config(company_id)
        if not config:
            logger.debug(f"No valid Twilio SMS config for company {company_id}")
            return

        if not company_name:
            with get_session() as db:
                company = db.query(Company).filter(Company.id == company_id).first()
                company_name = company.name if company else "Unknown"

        bot = CompanyTwilioSmsBot(
            company_id=company_id,
            company_name=company_name,
            account_sid=config["account_sid"],
            auth_token=config["auth_token"],
            phone_number=config["phone_number"],
            bot_agent_id=config.get("agent_id"),
            bot_permission_mode=config.get("permission_mode", "recognized_users"),
            bot_owner_id=config.get("owner_id"),
        )

        self._bots[company_id] = bot
        self._phone_to_company[self._normalize_phone(config["phone_number"])] = (
            company_id
        )
        bot.start()

    def stop_bot_for_company(self, company_id: str):
        """Stop Twilio SMS bot for a specific company."""
        if company_id not in self._bots:
            return

        bot = self._bots[company_id]

        # Remove phone mapping
        for phone, cid in list(self._phone_to_company.items()):
            if cid == company_id:
                del self._phone_to_company[phone]

        bot.stop()
        del self._bots[company_id]

    def sync_bots(self):
        """Sync bots with database configuration."""
        with get_session() as db:
            enabled_settings = (
                db.query(CompanyExtensionSetting)
                .filter(
                    CompanyExtensionSetting.extension_name == "twilio_sms",
                    CompanyExtensionSetting.setting_name == "twilio_sms_bot_enabled",
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

    def get_bot_for_phone(self, to_phone: str) -> Optional[CompanyTwilioSmsBot]:
        """Get the bot responsible for handling SMS to a specific phone number."""
        normalized = self._normalize_phone(to_phone)
        company_id = self._phone_to_company.get(normalized)
        if company_id:
            return self._bots.get(company_id)
        return None

    async def handle_incoming_sms(
        self,
        from_phone: str,
        to_phone: str,
        body: str,
    ) -> Optional[str]:
        """
        Handle incoming SMS from Twilio webhook.
        Returns the response message or None.
        """
        bot = self.get_bot_for_phone(to_phone)
        if not bot:
            logger.warning(f"No bot configured for phone: {to_phone}")
            return None

        return await bot.process_incoming_sms(from_phone, to_phone, body)

    def start(self):
        """Start the bot manager."""
        if self._running:
            return

        self._running = True
        self.sync_bots()
        logger.info("Twilio SMS Bot Manager started")

    def stop(self):
        """Stop all bots and the manager."""
        self._running = False

        for company_id in list(self._bots.keys()):
            self.stop_bot_for_company(company_id)

        logger.info("Twilio SMS Bot Manager stopped")

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
_manager: Optional[TwilioSmsBotManager] = None
_manager_lock = threading.Lock()


def get_twilio_sms_bot_manager() -> TwilioSmsBotManager:
    """Get or create the Twilio SMS bot manager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = TwilioSmsBotManager()
        return _manager


def start_twilio_sms_bot_manager():
    """Start the Twilio SMS bot manager."""
    manager = get_twilio_sms_bot_manager()
    manager.start()


def stop_twilio_sms_bot_manager():
    """Stop the Twilio SMS bot manager."""
    global _manager
    if _manager:
        _manager.stop()
        _manager = None


# FastAPI router for Twilio SMS webhook
twilio_sms_webhook_router = APIRouter(
    prefix="/webhooks/twilio", tags=["Twilio Webhooks"]
)


@twilio_sms_webhook_router.post("/sms")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
):
    """
    Handle incoming SMS from Twilio webhook.

    Twilio sends POST requests with form data containing:
    - From: Sender phone number
    - To: Recipient phone number (your Twilio number)
    - Body: Message text

    Returns TwiML response with optional reply message.
    """
    manager = get_twilio_sms_bot_manager()

    response_text = await manager.handle_incoming_sms(
        from_phone=From,
        to_phone=To,
        body=Body,
    )

    # Create TwiML response
    twiml = MessagingResponse()
    if response_text:
        twiml.message(response_text)

    return Response(content=str(twiml), media_type="application/xml")
