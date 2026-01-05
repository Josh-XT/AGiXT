"""
Twilio SMS Extension for AGiXT
This extension provides SMS capabilities via Twilio with webhook support,
whitelist/blacklist management, and conversation persistence.
"""

import json
import logging
import asyncio
import warnings
import os
import re
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    Boolean,
    UniqueConstraint,
    func,
    or_,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import SAWarning
from Extensions import Extensions
from DB import (
    get_session,
    ExtensionDatabaseMixin,
    Base,
    UserPreferences,
    Agent as AgentModel,
)
from fastapi import APIRouter, HTTPException, Depends, Query, Form, Request
from pydantic import BaseModel
from MagicalAuth import verify_api_key, get_user_id
from Globals import DEFAULT_USER
from Conversations import get_conversation_id_by_name
from WebhookManager import webhook_emitter
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

# Suppress SQLAlchemy warning about duplicate class registration
warnings.filterwarnings(
    "ignore",
    message=".*This declarative base already contains a class with the same class name.*",
    category=SAWarning,
)


# Pydantic models for API requests/responses
class PhoneNumberRequest(BaseModel):
    phone_number: str
    note: Optional[str] = None


class SmsMessageRequest(BaseModel):
    to_number: str
    message: str


class SmsHistoryResponse(BaseModel):
    id: int
    from_number: str
    to_number: str
    message: str
    direction: str  # 'inbound' or 'outbound'
    timestamp: str
    twilio_sid: Optional[str]


# Database Models
class SmsWhitelist(Base):
    """Database model for whitelisted phone numbers"""

    __tablename__ = "sms_whitelist"
    __table_args__ = (
        UniqueConstraint("user_id", "phone_number", name="uq_whitelist_user_phone"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    note = Column(String(500), default="")
    added_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "note": self.note,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


class SmsBlacklist(Base):
    """Database model for blacklisted phone numbers"""

    __tablename__ = "sms_blacklist"
    __table_args__ = (
        UniqueConstraint("user_id", "phone_number", name="uq_blacklist_user_phone"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    note = Column(String(500), default="")
    added_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "note": self.note,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


class SmsConversation(Base):
    """Database model for SMS conversation history"""

    __tablename__ = "sms_conversations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    from_number = Column(String(20), nullable=False, index=True)
    to_number = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)
    direction = Column(String(10), nullable=False)  # 'inbound' or 'outbound'
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    twilio_sid = Column(String(100), nullable=True)  # Twilio message SID
    status = Column(String(20), default="sent")  # sent, delivered, failed, etc.
    media_urls = Column(Text, nullable=True)  # JSON string of media URLs/files
    has_media = Column(Boolean, default=False)  # Quick check for media attachments

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "from_number": self.from_number,
            "to_number": self.to_number,
            "message": self.message,
            "direction": self.direction,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "twilio_sid": self.twilio_sid,
            "status": self.status,
            "media_urls": json.loads(self.media_urls) if self.media_urls else [],
            "has_media": self.has_media,
        }


class twilio_sms(Extensions, ExtensionDatabaseMixin):
    """
    Twilio SMS Extension for AGiXT

    This extension enables AI agents to send and receive SMS messages via Twilio.
    It includes whitelist/blacklist management for phone number filtering and
    conversation history tracking.

    Key Features:
    - Send SMS messages to any phone number
    - Receive SMS via webhook and process with agent
    - Whitelist/blacklist management for access control
    - Conversation history persistence
    - Automatic spam filtering

    Security Model:
    - If whitelist is empty, all numbers are allowed (except blacklisted)
    - If whitelist has entries, only whitelisted numbers are allowed
    - Blacklist always takes precedence over whitelist

    Extension Parameters Required:
    - TWILIO_ACCOUNT_SID: Your Twilio Account SID
    - TWILIO_AUTH_TOKEN: Your Twilio Auth Token
    - TWILIO_PHONE_NUMBER: Your Twilio phone number (E.164 format, e.g., +1234567890)

    Each agent can have its own Twilio account and phone number by configuring
    these parameters in the agent's extension settings.
    """

    CATEGORY = "Communication"
    friendly_name = "Twilio SMS"

    # Register extension models for automatic table creation
    extension_models = [SmsWhitelist, SmsBlacklist, SmsConversation]

    # Define webhook events
    webhook_events = [
        {
            "type": "sms.received",
            "description": "Triggered when an SMS message is received",
        },
        {"type": "sms.sent", "description": "Triggered when an SMS message is sent"},
        {
            "type": "sms.blocked",
            "description": "Triggered when a message is blocked by whitelist/blacklist",
        },
        {
            "type": "whitelist.added",
            "description": "Triggered when a number is added to whitelist",
        },
        {
            "type": "whitelist.removed",
            "description": "Triggered when a number is removed from whitelist",
        },
        {
            "type": "blacklist.added",
            "description": "Triggered when a number is added to blacklist",
        },
        {
            "type": "blacklist.removed",
            "description": "Triggered when a number is removed from blacklist",
        },
    ]

    PROMPT_AGENT_TIMEOUT = 120  # seconds

    def __init__(
        self,
        TWILIO_ACCOUNT_SID: str = "",
        TWILIO_AUTH_TOKEN: str = "",
        TWILIO_PHONE_NUMBER: str = "",
        **kwargs,
    ):
        self.AGENT = kwargs
        raw_user_id = kwargs.get("user_id")
        self.user_id = str(raw_user_id) if raw_user_id else None
        self.user_email = kwargs.get("user_email") or kwargs.get("user")
        if self.user_email in (None, "", "None"):
            default_user = (
                DEFAULT_USER if DEFAULT_USER not in (None, "", "None") else None
            )
            self.user_email = default_user
        if (
            not self.user_id
            and self.user_email
            and isinstance(self.user_email, str)
            and "@" in self.user_email
        ):
            try:
                self.user_id = str(get_user_id(self.user_email))
            except Exception as e:
                logging.debug(f"Unable to resolve user ID for {self.user_email}: {e}")
        self.ApiClient = kwargs.get("ApiClient", None)
        self.agent_name = kwargs.get("agent_name", "AGiXT")
        raw_agent_id = kwargs.get("agent_id")
        self.agent_id = str(raw_agent_id) if raw_agent_id else None
        self._agent_metadata = None
        self._workspace_cache = {}

        # Get Twilio credentials from extension parameters
        self.account_sid = TWILIO_ACCOUNT_SID
        self.auth_token = TWILIO_AUTH_TOKEN
        self.twilio_number = TWILIO_PHONE_NUMBER

        # Initialize Twilio client if credentials are available
        self.twilio_client = None
        if self.account_sid and self.auth_token:
            try:
                self.twilio_client = Client(self.account_sid, self.auth_token)
            except Exception as e:
                logging.error(f"Failed to initialize Twilio client: {e}")

        # Register models with ExtensionDatabaseMixin
        self.register_models()

        # Auto-whitelist user's phone number from preferences if available
        self._auto_whitelist_user_phone()

        # Define available commands for agent interaction
        self.commands = {
            "Send SMS": self.send_sms,
            "Get SMS History": self.get_sms_history,
            "Add Number to Whitelist": self.add_to_whitelist,
            "Remove Number from Whitelist": self.remove_from_whitelist,
            "List Whitelisted Numbers": self.list_whitelist,
            "Add Number to Blacklist": self.add_to_blacklist,
            "Remove Number from Blacklist": self.remove_from_blacklist,
            "List Blacklisted Numbers": self.list_blacklist,
            "Check Number Status": self.check_number_status,
        }

        # Set up FastAPI router for REST endpoints
        self.router = APIRouter(prefix="/twilio", tags=["Twilio SMS"])
        self._setup_routes()

    def _get_user_phone_number(self) -> Optional[str]:
        """
        Get the user's phone number from their preferences.

        Returns:
            Optional[str]: Phone number in E.164 format or None
        """
        from DB import UserPreferences

        session = get_session()
        try:
            phone_pref = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == self.user_id)
                .filter(UserPreferences.pref_key == "phone_number")
                .first()
            )

            if phone_pref and phone_pref.pref_value:
                phone = phone_pref.pref_value.strip()
                # Validate it's a reasonable phone number (at least 10 digits)
                if len(phone) >= 10:
                    # Add + prefix if not present and it's a valid number
                    if not phone.startswith("+"):
                        phone = f"+{phone}"
                    return phone
            return None
        except Exception as e:
            logging.error(f"Error getting user phone number: {e}")
            return None
        finally:
            session.close()

    def _auto_whitelist_user_phone(self):
        """
        Automatically whitelist the user's phone number from their preferences.
        This runs during initialization to ensure the user can always text their agent.
        """
        if not self.user_id:
            return

        user_phone = self._get_user_phone_number()
        if not user_phone:
            return

        session = get_session()
        try:
            # Check if already whitelisted
            existing = (
                session.query(SmsWhitelist)
                .filter_by(user_id=self.user_id, phone_number=user_phone)
                .first()
            )

            if not existing:
                # Auto-whitelist with note
                whitelist_entry = SmsWhitelist(
                    user_id=self.user_id,
                    phone_number=user_phone,
                    note="Auto-whitelisted from user preferences",
                )
                session.add(whitelist_entry)
                session.commit()
                logging.info(f"Auto-whitelisted user phone number: {user_phone}")
        except Exception as e:
            session.rollback()
            logging.error(f"Error auto-whitelisting user phone: {e}")
        finally:
            session.close()

    def _get_agent_metadata(self) -> Optional[dict]:
        """Retrieve agent metadata including IDs for workspace operations."""
        if self._agent_metadata:
            return self._agent_metadata

        session = get_session()
        try:
            query = session.query(AgentModel).filter(AgentModel.name == self.agent_name)
            if self.user_id:
                query = query.filter(AgentModel.user_id == self.user_id)

            agent = query.first()
            if not agent:
                logging.debug(
                    f"No agent record found for name '{self.agent_name}' with user_id '{self.user_id}'"
                )
                return None

            metadata = {
                "id": str(agent.id),
                "user_id": str(agent.user_id) if agent.user_id else None,
            }
            self._agent_metadata = metadata

            if not self.agent_id:
                self.agent_id = metadata["id"]
            if not self.user_id and metadata["user_id"]:
                self.user_id = metadata["user_id"]

            return metadata
        except Exception as e:
            logging.error(f"Error retrieving agent metadata: {e}")
            return None
        finally:
            session.close()

    def _ensure_conversation_workspace(
        self, conversation_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Ensure the conversation workspace exists and return (conversation_id, path)."""

        normalized_name = conversation_name or "-"
        if normalized_name in self._workspace_cache:
            return self._workspace_cache[normalized_name]

        metadata = self._get_agent_metadata()
        if not metadata:
            logging.debug("Unable to resolve agent metadata for workspace access")
            result = (None, None)
            self._workspace_cache[normalized_name] = result
            return result

        user_id = metadata.get("user_id") or self.user_id
        if not user_id:
            logging.debug("Unable to resolve user_id for workspace access")
            result = (None, None)
            self._workspace_cache[normalized_name] = result
            return result

        try:
            conversation_id = get_conversation_id_by_name(normalized_name, user_id)
        except Exception as e:
            logging.error(
                f"Error resolving conversation ID for '{normalized_name}': {e}"
            )
            result = (None, None)
            self._workspace_cache[normalized_name] = result
            return result

        workspace_root = os.path.join(os.getcwd(), "WORKSPACE", metadata["id"])
        conversation_dir = os.path.join(workspace_root, conversation_id)

        try:
            os.makedirs(conversation_dir, exist_ok=True)
        except Exception as e:
            logging.error(
                f"Error ensuring workspace directory for conversation '{conversation_id}': {e}"
            )
            conversation_dir = None

        result = (conversation_id, conversation_dir)
        self._workspace_cache[normalized_name] = result
        return result

    def _setup_routes(self):
        """Set up FastAPI routes for the Twilio extension"""

        @self.router.post("/webhook")
        async def twilio_webhook(request: Request):
            """
            Webhook endpoint for receiving SMS/MMS from Twilio
            Configure this URL in your Twilio phone number settings
            """
            try:
                # Get form data from Twilio
                form_data = await request.form()
                from_number = form_data.get("From", "")
                to_number = form_data.get("To", "")
                message_body = form_data.get("Body", "")
                message_sid = form_data.get("MessageSid", "")
                num_media = int(form_data.get("NumMedia", "0"))

                logging.info(
                    f"Received SMS from {from_number} to {to_number}: {message_body}"
                )

                today = datetime.utcnow().strftime("%Y-%m-%d")
                conversation_name = f"SMS on {today}"
                conversation_id: Optional[str] = None
                conversation_workspace: Optional[str] = None

                # Handle MMS attachments (images, videos, etc.)
                media_urls = []
                media_files = []
                media_details = []
                if num_media > 0:
                    logging.info(f"Message contains {num_media} media attachment(s)")

                    try:
                        import requests
                    except Exception as e:
                        logging.error(
                            f"Requests library not available for media download: {e}"
                        )
                        requests = None

                    conversation_id, conversation_workspace = (
                        self._ensure_conversation_workspace(conversation_name)
                    )

                    for i in range(num_media):
                        media_url = form_data.get(f"MediaUrl{i}")
                        media_content_type = form_data.get(f"MediaContentType{i}")

                        if not media_url:
                            continue

                        media_urls.append(
                            {"url": media_url, "content_type": media_content_type}
                        )
                        if not requests or not conversation_workspace:
                            logging.debug(
                                "Skipping media download due to missing requests library or workspace path"
                            )
                            continue

                        try:
                            parsed_url = requests.utils.urlparse(media_url)
                            if parsed_url.scheme != "https":
                                logging.warning(
                                    f"Skipping media download with invalid scheme: {media_url}"
                                )
                                continue
                            host = parsed_url.netloc.lower()
                            if not (
                                host == "twilio.com" or host.endswith(".twilio.com")
                            ):
                                logging.warning(
                                    f"Skipping media download from untrusted host: {media_url}"
                                )
                                continue
                            response = requests.get(
                                media_url,
                                auth=(self.account_sid, self.auth_token),
                                timeout=10,
                                allow_redirects=False,
                            )
                            if response.status_code == 200:
                                ext_map = {
                                    "image/jpeg": ".jpg",
                                    "image/jpg": ".jpg",
                                    "image/png": ".png",
                                    "image/gif": ".gif",
                                    "video/mp4": ".mp4",
                                    "audio/mpeg": ".mp3",
                                    "audio/ogg": ".ogg",
                                }
                                ext = ext_map.get(media_content_type, ".bin")

                                sanitized_from_number = re.sub(
                                    r"[^0-9A-Za-z]", "_", from_number or ""
                                )[:32]
                                if not sanitized_from_number:
                                    sanitized_from_number = "unknown"
                                filename = (
                                    f"{datetime.utcnow().strftime('%H%M%S')}"
                                    f"_{sanitized_from_number}_{i}{ext}"
                                )
                                filename = os.path.basename(filename)
                                filepath = os.path.join(
                                    conversation_workspace, filename
                                )

                                with open(filepath, "wb") as f:
                                    f.write(response.content)

                                media_files.append(filename)
                                media_details.append(
                                    {
                                        "filename": filename,
                                        "content_type": media_content_type,
                                    }
                                )
                                logging.info(
                                    f"Saved media to conversation workspace: {filename}"
                                )

                                if not message_body:
                                    message_body = f"[Media: {media_content_type}]"
                                else:
                                    message_body += f"\n[Attachment: {filename}]"
                            else:
                                logging.error(
                                    f"Failed to download media {i}: HTTP {response.status_code}"
                                )
                        except Exception as e:
                            logging.error(f"Error downloading media {i}: {e}")

                # Check if number is allowed
                is_allowed, reason, number_status = await self._check_number_allowed(
                    from_number
                )

                if not is_allowed:
                    logging.warning(f"Blocked SMS from {from_number}: {reason}")

                    # Emit blocked event
                    asyncio.create_task(
                        webhook_emitter.emit_event(
                            event_type="sms.blocked",
                            user_id=self.user_id,
                            data={
                                "from_number": from_number,
                                "to_number": to_number,
                                "message": message_body[:100],
                                "reason": reason,
                                "conversation_name": conversation_name,
                                "conversation_id": conversation_id,
                            },
                            metadata={"message_sid": message_sid},
                        )
                    )

                    # Return empty response (no reply to blocked numbers)
                    resp = MessagingResponse()
                    return str(resp)

                if conversation_id is None:
                    conversation_id, conversation_workspace = (
                        self._ensure_conversation_workspace(conversation_name)
                    )

                # Store the received message in conversation history
                session = get_session()
                try:
                    # Prepare media data for storage
                    media_data = None
                    if media_files:
                        media_data = json.dumps(
                            [
                                {
                                    "url": media["url"],
                                    "content_type": media["content_type"],
                                    "local_file": file,
                                }
                                for media, file in zip(media_urls, media_files)
                            ]
                        )

                    conversation = SmsConversation(
                        user_id=self.user_id,
                        from_number=from_number,
                        to_number=to_number,
                        message=message_body,
                        direction="inbound",
                        twilio_sid=message_sid,
                        status="received",
                        media_urls=media_data,
                        has_media=len(media_files) > 0,
                    )
                    session.add(conversation)
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logging.error(f"Error storing SMS conversation: {e}")
                finally:
                    session.close()

                # Emit received event
                asyncio.create_task(
                    webhook_emitter.emit_event(
                        event_type="sms.received",
                        user_id=self.user_id,
                        data={
                            "from_number": from_number,
                            "to_number": to_number,
                            "message": message_body[:100],
                            "timestamp": datetime.utcnow().isoformat(),
                            "has_media": len(media_files) > 0,
                            "num_media": num_media,
                            "conversation_name": conversation_name,
                            "conversation_id": conversation_id,
                        },
                        metadata={
                            "message_sid": message_sid,
                            "conversation_id": conversation_id,
                        },
                    )
                )

                # Process message asynchronously to avoid blocking webhook response
                if self.ApiClient:
                    asyncio.create_task(
                        self._process_incoming_sms_response(
                            from_number=from_number,
                            to_number=to_number,
                            message_body=message_body,
                            conversation_name=conversation_name,
                            conversation_id=conversation_id,
                            number_status=number_status,
                            media_details=media_details,
                            media_urls=media_urls,
                        )
                    )
                else:
                    logging.debug(
                        "ApiClient not configured; skipping automated SMS response."
                    )

                resp = MessagingResponse()
                return str(resp)

            except Exception as e:
                logging.error(f"Error processing Twilio webhook: {e}")
                resp = MessagingResponse()
                return str(resp)

        @self.router.post("/send")
        async def send_sms_endpoint(
            sms_data: SmsMessageRequest, user=Depends(verify_api_key)
        ):
            """Send an SMS message via REST API"""
            result = await self.send_sms(
                to_number=sms_data.to_number, message=sms_data.message
            )
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.post("/whitelist")
        async def add_whitelist_endpoint(
            phone_data: PhoneNumberRequest, user=Depends(verify_api_key)
        ):
            """Add a number to whitelist via REST API"""
            result = await self.add_to_whitelist(
                phone_number=phone_data.phone_number, note=phone_data.note
            )
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.delete("/whitelist/{phone_number}")
        async def remove_whitelist_endpoint(
            phone_number: str, user=Depends(verify_api_key)
        ):
            """Remove a number from whitelist via REST API"""
            result = await self.remove_from_whitelist(phone_number=phone_number)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.get("/whitelist")
        async def list_whitelist_endpoint(user=Depends(verify_api_key)):
            """List all whitelisted numbers via REST API"""
            result = await self.list_whitelist()
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.post("/blacklist")
        async def add_blacklist_endpoint(
            phone_data: PhoneNumberRequest, user=Depends(verify_api_key)
        ):
            """Add a number to blacklist via REST API"""
            result = await self.add_to_blacklist(
                phone_number=phone_data.phone_number, note=phone_data.note
            )
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.delete("/blacklist/{phone_number}")
        async def remove_blacklist_endpoint(
            phone_number: str, user=Depends(verify_api_key)
        ):
            """Remove a number from blacklist via REST API"""
            result = await self.remove_from_blacklist(phone_number=phone_number)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.get("/blacklist")
        async def list_blacklist_endpoint(user=Depends(verify_api_key)):
            """List all blacklisted numbers via REST API"""
            result = await self.list_blacklist()
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

        @self.router.get("/history")
        async def get_history_endpoint(
            phone_number: Optional[str] = Query(None),
            limit: int = Query(50, ge=1, le=500),
            user=Depends(verify_api_key),
        ):
            """Get SMS conversation history via REST API"""
            result = await self.get_sms_history(phone_number=phone_number, limit=limit)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data

    async def _process_incoming_sms_response(
        self,
        *,
        from_number: str,
        to_number: str,
        message_body: str,
        conversation_name: str,
        conversation_id: Optional[str],
        number_status: dict,
        media_details: list,
        media_urls: list,
    ) -> None:
        """Handle prompt_agent call and auto-reply for inbound messages."""

        if not self.ApiClient:
            logging.debug("No ApiClient configured; skipping SMS auto-response.")
            return

        try:
            if not conversation_id:
                conversation_id, _ = self._ensure_conversation_workspace(
                    conversation_name
                )
        except Exception as e:
            logging.debug(
                f"Unable to ensure workspace for conversation '{conversation_name}': {e}"
            )
            conversation_id = conversation_id  # keep whatever we had

        prompt_text = message_body or ""

        attachments_note_lines = []
        if media_details:
            attachments_note_lines.append(
                f"This message includes {len(media_details)} saved attachment(s):"
            )
            for detail in media_details:
                filename = detail.get("filename")
                content_type = detail.get("content_type") or "unknown"
                attachments_note_lines.append(f"- {filename} ({content_type})")

        remaining_remote = max(0, len(media_urls) - len(media_details))
        if remaining_remote:
            attachments_note_lines.append(
                f"There are {remaining_remote} additional attachment(s) accessible via the original Twilio media URLs."
            )

        if attachments_note_lines:
            workspace_hint = "conversation workspace"
            if conversation_id and self.agent_id:
                workspace_hint += (
                    f" for agent {self.agent_id} and conversation {conversation_id}"
                )
            elif conversation_id:
                workspace_hint += f" for conversation {conversation_id}"
            prompt_text += "\n\n[Attachments located in the " + workspace_hint + ":\n"
            prompt_text += "\n".join(attachments_note_lines) + "\n]"

        try:
            agent_response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.ApiClient.prompt_agent,
                    agent_name=self.agent_name,
                    prompt_name="Think About It",
                    prompt_args={
                        "user_input": prompt_text,
                        "conversation_name": conversation_name,
                        "websearch": False,
                        "analyze_user_input": False,
                        "log_user_input": False,
                        "log_output": True,
                        "tts": False,
                    },
                ),
                timeout=self.PROMPT_AGENT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logging.error(
                f"prompt_agent timed out processing SMS from {from_number} (conversation '{conversation_name}')."
            )
            return
        except Exception as e:
            logging.error(
                f"Error invoking prompt_agent for SMS from {from_number}: {e}"
            )
            return

        if not agent_response:
            logging.info(
                f"prompt_agent returned no content for SMS from {from_number}; skipping auto-reply."
            )
            return

        user_phone = self._get_user_phone_number()
        normalized_sender = (from_number or "").strip()
        normalized_user_phone = (user_phone or "").strip() if user_phone else ""
        is_user_phone = (
            normalized_user_phone and normalized_user_phone == normalized_sender
        )

        blacklisted = number_status.get("blacklisted", False)
        whitelisted = number_status.get("whitelisted", False)

        if blacklisted or not (whitelisted or is_user_phone):
            logging.info(
                f"Auto-reply suppressed for {from_number}: Blacklisted={blacklisted}, Whitelisted={whitelisted}, IsUserPhone={is_user_phone}."
            )
            return

        try:
            send_result_raw = await self.send_sms(
                to_number=from_number, message=agent_response
            )
            send_result = json.loads(send_result_raw)
            if not send_result.get("success"):
                logging.error(
                    f"Failed to send auto-reply SMS to {from_number}: {send_result.get('error')}"
                )
        except Exception as e:
            logging.error(f"Error sending auto-reply SMS to {from_number}: {e}")

    async def _check_number_allowed(self, phone_number: str) -> tuple[bool, str, dict]:
        """
        Check if a phone number is allowed to send/receive messages

        Logic:
        1. If in blacklist -> DENY
        2. If whitelist is empty -> ALLOW (open mode)
        3. If in whitelist -> ALLOW
        4. Otherwise -> DENY

        Returns:
            tuple: (is_allowed: bool, reason: str, details: dict)
        """
        session = get_session()
        try:
            # Check blacklist first (highest priority)
            blacklisted = (
                session.query(SmsBlacklist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if blacklisted:
                return (
                    False,
                    "Number is blacklisted",
                    {
                        "blacklisted": True,
                        "whitelisted": False,
                        "whitelist_empty": False,
                    },
                )

            # Check if whitelist is empty
            whitelist_count = (
                session.query(SmsWhitelist).filter_by(user_id=self.user_id).count()
            )

            # If whitelist is empty, allow all (except blacklisted)
            if whitelist_count == 0:
                return (
                    True,
                    "Whitelist is empty (allow all mode)",
                    {
                        "blacklisted": False,
                        "whitelisted": False,
                        "whitelist_empty": True,
                    },
                )

            # Check if number is in whitelist
            whitelisted = (
                session.query(SmsWhitelist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if whitelisted:
                return (
                    True,
                    "Number is whitelisted",
                    {
                        "blacklisted": False,
                        "whitelisted": True,
                        "whitelist_empty": False,
                    },
                )

            return (
                False,
                "Number not in whitelist",
                {
                    "blacklisted": False,
                    "whitelisted": False,
                    "whitelist_empty": False,
                },
            )

        except Exception as e:
            logging.error(f"Error checking number status: {e}")
            return (
                False,
                f"Error: {str(e)}",
                {
                    "blacklisted": False,
                    "whitelisted": False,
                    "whitelist_empty": False,
                },
            )
        finally:
            session.close()

    # Extension Commands for Agent Interaction

    async def send_sms(self, to_number: str = None, message: str = "") -> str:
        """
        Send an SMS message to a phone number.

        **IMPORTANT FOR AI AGENTS**: If no phone number is provided, this will automatically
        send to the authenticated user's phone number from their preferences. This means you
        can send messages to the user without needing to look up their phone number - just
        call send_sms with only the message parameter!

        Args:
            to_number (str, optional): Recipient's phone number (E.164 format, e.g., +1234567890).
                                       If not provided, defaults to user's phone number from preferences.
            message (str): Message content to send (max 1600 chars for single segment)

        Returns:
            str: JSON response with success status and message details

        Examples:
            # Send to specific number
            send_sms(to_number="+1234567890", message="Hello!")

            # Send to the user (their phone number is looked up automatically)
            send_sms(message="Your task is complete!")
        """
        if not self.twilio_client:
            return json.dumps(
                {
                    "success": False,
                    "error": "Twilio client not initialized. Check your credentials.",
                }
            )

        # Default to user's phone number if none provided
        if not to_number:
            to_number = self._get_user_phone_number()
            if not to_number:
                return json.dumps(
                    {
                        "success": False,
                        "error": "No recipient phone number provided and user has no phone number in preferences",
                    }
                )
            logging.info(f"Defaulting to user's phone number: {to_number}")

        if not message:
            return json.dumps(
                {
                    "success": False,
                    "error": "Message content is required",
                }
            )

        try:
            # Send message via Twilio
            twilio_message = self.twilio_client.messages.create(
                body=message, from_=self.twilio_number, to=to_number
            )

            # Store in conversation history
            session = get_session()
            try:
                conversation = SmsConversation(
                    user_id=self.user_id,
                    from_number=self.twilio_number,
                    to_number=to_number,
                    message=message,
                    direction="outbound",
                    twilio_sid=twilio_message.sid,
                    status=twilio_message.status,
                )
                session.add(conversation)
                session.commit()
            except Exception as e:
                session.rollback()
                logging.error(f"Error storing sent SMS: {e}")
            finally:
                session.close()

            # Emit sent event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="sms.sent",
                    user_id=self.user_id,
                    data={
                        "to_number": to_number,
                        "message": message[:100],
                        "timestamp": datetime.utcnow().isoformat(),
                        "status": twilio_message.status,
                    },
                    metadata={"message_sid": twilio_message.sid},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": "SMS sent successfully",
                    "sid": twilio_message.sid,
                    "status": twilio_message.status,
                    "to": to_number,
                }
            )

        except Exception as e:
            logging.error(f"Error sending SMS: {e}")
            return json.dumps({"success": False, "error": str(e)})

    async def get_sms_history(
        self, phone_number: Optional[str] = None, limit: int = 50
    ) -> str:
        """
        Get SMS conversation history, optionally filtered by phone number.

        Args:
            phone_number (Optional[str]): Filter by specific phone number
            limit (int): Maximum number of messages to return (default: 50)

        Returns:
            str: JSON response with conversation history
        """
        session = get_session()
        try:
            query = session.query(SmsConversation).filter_by(user_id=self.user_id)

            if phone_number:
                query = query.filter(
                    or_(
                        SmsConversation.from_number == phone_number,
                        SmsConversation.to_number == phone_number,
                    )
                )

            conversations = (
                query.order_by(SmsConversation.timestamp.desc()).limit(limit).all()
            )

            return json.dumps(
                {
                    "success": True,
                    "conversations": [conv.to_dict() for conv in conversations],
                    "count": len(conversations),
                    "phone_number": phone_number,
                }
            )

        except Exception as e:
            logging.error(f"Error getting SMS history: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def add_to_whitelist(
        self, phone_number: str, note: Optional[str] = None
    ) -> str:
        """
        Add a phone number to the whitelist.

        Args:
            phone_number (str): Phone number to whitelist (E.164 format)
            note (Optional[str]): Optional note about this number

        Returns:
            str: JSON response with success status
        """
        session = get_session()
        try:
            # Check if already in whitelist
            existing = (
                session.query(SmsWhitelist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if existing:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Phone number already in whitelist",
                    }
                )

            # Add to whitelist
            whitelist_entry = SmsWhitelist(
                user_id=self.user_id, phone_number=phone_number, note=note or ""
            )
            session.add(whitelist_entry)
            session.commit()

            # Emit event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="whitelist.added",
                    user_id=self.user_id,
                    data={"phone_number": phone_number, "note": note},
                    metadata={"operation": "add_whitelist"},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Added {phone_number} to whitelist",
                    "entry": whitelist_entry.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            logging.error(f"Error adding to whitelist: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def remove_from_whitelist(self, phone_number: str) -> str:
        """
        Remove a phone number from the whitelist.

        Args:
            phone_number (str): Phone number to remove from whitelist

        Returns:
            str: JSON response with success status
        """
        session = get_session()
        try:
            entry = (
                session.query(SmsWhitelist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if not entry:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Phone number not found in whitelist",
                    }
                )

            session.delete(entry)
            session.commit()

            # Emit event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="whitelist.removed",
                    user_id=self.user_id,
                    data={"phone_number": phone_number},
                    metadata={"operation": "remove_whitelist"},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Removed {phone_number} from whitelist",
                }
            )

        except Exception as e:
            session.rollback()
            logging.error(f"Error removing from whitelist: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_whitelist(self) -> str:
        """
        List all whitelisted phone numbers.

        Returns:
            str: JSON response with list of whitelisted numbers
        """
        session = get_session()
        try:
            entries = (
                session.query(SmsWhitelist)
                .filter_by(user_id=self.user_id)
                .order_by(SmsWhitelist.added_at.desc())
                .all()
            )

            return json.dumps(
                {
                    "success": True,
                    "whitelist": [entry.to_dict() for entry in entries],
                    "count": len(entries),
                }
            )

        except Exception as e:
            logging.error(f"Error listing whitelist: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def add_to_blacklist(
        self, phone_number: str, note: Optional[str] = None
    ) -> str:
        """
        Add a phone number to the blacklist.

        Args:
            phone_number (str): Phone number to blacklist (E.164 format)
            note (Optional[str]): Optional note about why this number is blocked

        Returns:
            str: JSON response with success status
        """
        session = get_session()
        try:
            # Check if already in blacklist
            existing = (
                session.query(SmsBlacklist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if existing:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Phone number already in blacklist",
                    }
                )

            # Add to blacklist
            blacklist_entry = SmsBlacklist(
                user_id=self.user_id, phone_number=phone_number, note=note or ""
            )
            session.add(blacklist_entry)
            session.commit()

            # Emit event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="blacklist.added",
                    user_id=self.user_id,
                    data={"phone_number": phone_number, "note": note},
                    metadata={"operation": "add_blacklist"},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Added {phone_number} to blacklist",
                    "entry": blacklist_entry.to_dict(),
                }
            )

        except Exception as e:
            session.rollback()
            logging.error(f"Error adding to blacklist: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def remove_from_blacklist(self, phone_number: str) -> str:
        """
        Remove a phone number from the blacklist.

        Args:
            phone_number (str): Phone number to remove from blacklist

        Returns:
            str: JSON response with success status
        """
        session = get_session()
        try:
            entry = (
                session.query(SmsBlacklist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if not entry:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Phone number not found in blacklist",
                    }
                )

            session.delete(entry)
            session.commit()

            # Emit event
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="blacklist.removed",
                    user_id=self.user_id,
                    data={"phone_number": phone_number},
                    metadata={"operation": "remove_blacklist"},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Removed {phone_number} from blacklist",
                }
            )

        except Exception as e:
            session.rollback()
            logging.error(f"Error removing from blacklist: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_blacklist(self) -> str:
        """
        List all blacklisted phone numbers.

        Returns:
            str: JSON response with list of blacklisted numbers
        """
        session = get_session()
        try:
            entries = (
                session.query(SmsBlacklist)
                .filter_by(user_id=self.user_id)
                .order_by(SmsBlacklist.added_at.desc())
                .all()
            )

            return json.dumps(
                {
                    "success": True,
                    "blacklist": [entry.to_dict() for entry in entries],
                    "count": len(entries),
                }
            )

        except Exception as e:
            logging.error(f"Error listing blacklist: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def check_number_status(self, phone_number: str) -> str:
        """
        Check the status of a phone number (allowed, whitelisted, blacklisted, etc.)

        Args:
            phone_number (str): Phone number to check

        Returns:
            str: JSON response with number status details
        """
        session = get_session()
        try:
            # Check blacklist
            blacklisted = (
                session.query(SmsBlacklist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            if blacklisted:
                return json.dumps(
                    {
                        "success": True,
                        "phone_number": phone_number,
                        "status": "blacklisted",
                        "allowed": False,
                        "details": blacklisted.to_dict(),
                    }
                )

            # Check whitelist
            whitelisted = (
                session.query(SmsWhitelist)
                .filter_by(user_id=self.user_id, phone_number=phone_number)
                .first()
            )

            # Check if whitelist is empty
            whitelist_count = (
                session.query(SmsWhitelist).filter_by(user_id=self.user_id).count()
            )

            if whitelisted:
                return json.dumps(
                    {
                        "success": True,
                        "phone_number": phone_number,
                        "status": "whitelisted",
                        "allowed": True,
                        "details": whitelisted.to_dict(),
                    }
                )
            elif whitelist_count == 0:
                return json.dumps(
                    {
                        "success": True,
                        "phone_number": phone_number,
                        "status": "allowed (whitelist empty)",
                        "allowed": True,
                        "details": None,
                    }
                )
            else:
                return json.dumps(
                    {
                        "success": True,
                        "phone_number": phone_number,
                        "status": "not whitelisted",
                        "allowed": False,
                        "details": None,
                    }
                )

        except Exception as e:
            logging.error(f"Error checking number status: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
