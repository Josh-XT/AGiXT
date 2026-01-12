"""
WebhookManager - Core webhook system for AGiXT
Handles both incoming and outgoing webhooks with retry logic, event emission, and processing
"""

import uuid
import time
import json
import hashlib
import hmac
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
from threading import Lock
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from DB import (
    WebhookIncoming,
    WebhookOutgoing,
    WebhookLog,
    Agent,
    AgentSetting,
    get_session,
)
from Models import (
    WebhookEventPayload,
    WebhookIncomingCreate,
    WebhookOutgoingCreate,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _mask_sensitive_id(identifier: str) -> str:
    """Mask sensitive identifiers for safe logging, showing only first 8 chars"""
    if not identifier:
        return "<empty>"
    identifier_str = str(identifier)
    if len(identifier_str) <= 8:
        return identifier_str[:2] + "***"
    return identifier_str[:8] + "***"


def safe_json_loads(json_str, default=None):
    """Safely load JSON string, returning default value on error"""
    if not json_str:
        return default
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


class WebhookEventEmitter:
    """
    Singleton class responsible for emitting webhook events to registered subscribers
    """

    _instance = None
    _lock = Lock()

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
        self._event_queue = asyncio.Queue()
        self._retry_queue = asyncio.Queue()
        self._rate_limits = defaultdict(lambda: {"count": 0, "reset_time": time.time()})
        self._circuit_breakers = {}  # Track failing endpoints
        self._processing = False

    async def emit_event(
        self,
        event_type: str,
        user_id: str,
        data: Dict[str, Any],
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        company_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Emit a webhook event to all registered subscribers

        Args:
            event_type: Type of event (e.g., "command.executed", "chat.completed")
            user_id: ID of the user triggering the event
            data: Event-specific data payload
            agent_id: Optional agent ID if event is agent-related
            agent_name: Optional agent name
            company_id: Optional company ID - if not provided, will resolve user's default company
            metadata: Optional additional metadata

        Returns:
            Event ID for tracking
        """
        logger.debug(
            f"emit_event parameters: event_type={event_type}, user_id={user_id}, company_id={company_id} (type: {type(company_id)}), agent_id={agent_id}, agent_name={agent_name}"
        )
        event_id = str(uuid.uuid4())

        # Ensure user_id is a string (convert UUID objects to string)
        if user_id:
            logger.debug(
                f"Converting user_id {user_id} (type: {type(user_id)}) to string"
            )
            user_id = str(user_id)

        # Ensure agent_id is a string (convert UUID objects to string)
        if agent_id:
            logger.debug(
                f"Converting agent_id {agent_id} (type: {type(agent_id)}) to string"
            )
            agent_id = str(agent_id)

        # If an agent is provided and no explicit company was supplied, try to derive it from the agent settings
        if agent_id and not company_id:
            agent_company_id = self._get_agent_company_id(agent_id)
            if agent_company_id:
                logger.debug(f"Resolved company_id from agent settings")
                company_id = agent_company_id

        # If agent_name is provided but agent_id is not, try to resolve company from agent name
        if agent_name and not company_id:
            agent_company_id = self._get_agent_company_id_by_name(agent_name, user_id)
            if agent_company_id:
                logger.debug(f"Resolved company_id from agent name")
                company_id = agent_company_id

        # Also check for agent_name in the data payload if not provided as a parameter
        if not company_id and data and isinstance(data, dict):
            data_agent_name = data.get("agent_name")
            data_agent_id = data.get("agent_id")
            if data_agent_id and not company_id:
                agent_company_id = self._get_agent_company_id(data_agent_id)
                if agent_company_id:
                    logger.debug(f"Resolved company_id from data.agent_id")
                    company_id = agent_company_id
            if data_agent_name and not company_id:
                agent_company_id = self._get_agent_company_id_by_name(
                    data_agent_name, user_id
                )
                if agent_company_id:
                    logger.debug(f"Resolved company_id from data.agent_name")
                    company_id = agent_company_id

        # Ensure company_id is a string if provided (handle case where UUID object is passed)
        # Also ensure we don't convert None to string "None"
        if company_id is not None and company_id != "None":
            logger.debug(
                f"Converting initial company_id (type: {type(company_id).__name__}) to string"
            )
            company_id = str(company_id)
        else:
            company_id = None

        # Resolve company_id if not provided
        if not company_id:
            company_id = self._get_user_company_id(user_id)
            if company_id:
                logger.debug(f"Resolved company_id for user")

        # Ensure company_id is a string (convert UUID objects to string)
        # Also ensure we don't convert None to string "None"
        if company_id is not None and company_id != "None":
            logger.debug(
                f"Converting company_id (type: {type(company_id).__name__}) to string"
            )
            company_id = str(company_id)
        else:
            company_id = None

        event_payload = WebhookEventPayload(
            event_id=event_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            company_id=company_id,
            agent_id=agent_id,
            agent_name=agent_name,
            data=data,
            metadata=metadata or {},
        )

        # Queue the event for processing
        await self._event_queue.put(event_payload)

        # Start processing if not already running
        if not self._processing:
            asyncio.create_task(self._process_events())

        return event_id

    def _get_agent_company_id(self, agent_id: str) -> Optional[str]:
        """Attempt to resolve the company associated with a given agent."""
        session: Optional[Session] = None
        try:
            agent_id_str = str(agent_id)
            session = get_session()

            # Look for a cached company_id in the agent settings first
            setting = (
                session.query(AgentSetting)
                .filter(
                    AgentSetting.agent_id == agent_id_str,
                    AgentSetting.name == "company_id",
                )
                .first()
            )
            if setting and setting.value:
                return str(setting.value)

            # Fall back to the agent's owning user to infer the company
            agent = session.query(Agent).filter(Agent.id == agent_id_str).first()
            if agent and agent.user_id:
                inferred_company = self._get_user_company_id(agent.user_id)
                if inferred_company:
                    return inferred_company

            return None
        except Exception as exc:
            logger.warning(
                f"Could not resolve company_id for agent: {type(exc).__name__}"
            )
            return None
        finally:
            if session:
                session.close()

    def _get_agent_company_id_by_name(
        self, agent_name: str, user_id: Optional[str] = None
    ) -> Optional[str]:
        """Attempt to resolve the company associated with an agent by its name."""
        session: Optional[Session] = None
        try:
            session = get_session()

            # Query for agents with this name, optionally filtered by user_id
            query = session.query(Agent).filter(Agent.name == agent_name)
            if user_id:
                query = query.filter(Agent.user_id == str(user_id))
            agent = query.first()

            if not agent:
                logger.debug(
                    "No agent found with specified name"
                    + (" for user" if user_id else "")
                )
                return None

            # Look for company_id in the agent's settings
            setting = (
                session.query(AgentSetting)
                .filter(
                    AgentSetting.agent_id == str(agent.id),
                    AgentSetting.name == "company_id",
                )
                .first()
            )
            if setting and setting.value:
                logger.debug("Found company_id in settings for agent")
                return str(setting.value)

            # Fall back to inferring from the agent's user
            if agent.user_id:
                inferred_company = self._get_user_company_id(agent.user_id)
                if inferred_company:
                    logger.debug("Inferred company_id from agent owner")
                    return inferred_company

            return None
        except Exception as exc:
            logger.warning(
                f"Could not resolve company_id for agent name: {type(exc).__name__}"
            )
            return None
        finally:
            if session:
                session.close()

    def _get_user_company_id(self, user_id: str) -> Optional[str]:
        """Get user's default company_id"""
        try:
            # Check if user_id is a valid UUID format
            import uuid as uuid_lib

            # Ensure user_id is a string
            user_id_str = str(user_id)

            try:
                uuid_lib.UUID(user_id_str)
            except ValueError:
                # user_id is not a valid UUID (e.g., email address), skip company lookup
                logger.debug("User ID is not a valid UUID, skipping company lookup")
                return None

            session = get_session()
            from DB import UserCompany

            user_company = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == user_id_str)
                .first()
            )

            company_id = (
                user_company.company_id
                if user_company and user_company.company_id is not None
                else None
            )
            session.close()

            # Ensure we return a string or None
            return str(company_id) if company_id is not None else None

        except Exception as e:
            logger.warning(f"Could not resolve company_id for user {user_id}: {e}")
            return None

    async def _process_events(self):
        """Process queued events and send to webhook subscribers"""
        self._processing = True

        try:
            while not self._event_queue.empty():
                event = await self._event_queue.get()
                await self._send_to_subscribers(event)
        finally:
            self._processing = False

    async def _send_to_subscribers(self, event: WebhookEventPayload):
        """Send event to all matching webhook subscribers"""
        session = get_session()

        try:
            # If no company_id in the event, skip webhook processing silently
            # This can happen for internal events that don't have a company context
            if not event.company_id or event.company_id == "None":
                logger.debug(
                    f"Event {event.event_type} has no company_id, skipping webhook processing"
                )
                return

            # First, get all active webhooks to see what's available
            all_webhooks = (
                session.query(WebhookOutgoing)
                .filter(WebhookOutgoing.active == True)
                .filter(WebhookOutgoing.company_id == event.company_id)
                .all()
            )

            # Find all active webhooks subscribed to this event type
            # First get all active webhooks for this company, then filter in Python for better compatibility
            all_active_webhooks = (
                session.query(WebhookOutgoing)
                .filter(WebhookOutgoing.active == True)
                .filter(WebhookOutgoing.company_id == event.company_id)
                .all()
            )

            webhooks = []
            for webhook in all_active_webhooks:
                if self._webhook_subscribes_to_event(webhook, event.event_type):
                    webhooks.append(webhook)

            for webhook in webhooks:
                # Check if webhook matches filters
                if self._matches_filters(webhook, event):
                    # Check circuit breaker
                    if self._is_circuit_open(webhook.id):
                        logger.warning(f"Circuit breaker open for webhook {webhook.id}")
                        continue
                    task = asyncio.create_task(self._send_webhook(webhook, event))
                else:
                    logger.info(f"Webhook {webhook.id} does not match filters")

        except Exception as e:
            logger.error(f"Error sending webhooks: {e}")
        finally:
            session.close()

    def _matches_filters(
        self, webhook: WebhookOutgoing, event: WebhookEventPayload
    ) -> bool:
        """Check if event matches webhook filters"""
        if not webhook.filters:
            return True

        # Deserialize filters from JSON
        filters = safe_json_loads(webhook.filters, {})
        logger.debug(f"Webhook {webhook.id} filters: {filters}")

        # Check agent filter
        if "agent_id" in filters and event.agent_id != filters["agent_id"]:
            logger.debug(
                f"Agent ID filter mismatch: {event.agent_id} != {filters['agent_id']}"
            )
            return False
        if "agent_name" in filters and event.agent_name != filters["agent_name"]:
            logger.debug(
                f"Agent name filter mismatch: {event.agent_name} != {filters['agent_name']}"
            )
            return False

        # Check user filter
        if "user_id" in filters and event.user_id != filters["user_id"]:
            logger.debug(
                f"User ID filter mismatch: {event.user_id} != {filters['user_id']}"
            )
            return False

        # Check company filter
        if "company_id" in filters and event.company_id != filters["company_id"]:
            return False

        return True

    def debug_webhook_subscription(
        self, webhook_id: str, event_type: str
    ) -> Dict[str, Any]:
        """Debug method to check if a webhook would receive a specific event type"""
        session = get_session()
        try:
            webhook = session.query(WebhookOutgoing).filter_by(id=webhook_id).first()
            if not webhook:
                return {"error": "Webhook not found"}

            result = {
                "webhook_id": webhook_id,
                "webhook_name": webhook.name,
                "active": webhook.active,
                "event_types": webhook.event_types,
                "filters": webhook.filters,
                "target_url": webhook.target_url,
                "would_match": False,
                "reasons": [],
            }

            # Check if webhook is active
            if not webhook.active:
                result["reasons"].append("Webhook is inactive")
                return result

            # Check event type subscription using the same logic as the main system
            if not self._webhook_subscribes_to_event(webhook, event_type):
                result["reasons"].append(
                    f"Event type '{event_type}' not subscribed. Configured event_types: {webhook.event_types}"
                )
                return result

            result["would_match"] = True
            result["reasons"].append("Webhook would receive this event")
            return result

        finally:
            session.close()

    def _webhook_subscribes_to_event(
        self, webhook: WebhookOutgoing, event_type: str
    ) -> bool:
        """Check if webhook subscribes to the given event type"""
        if not webhook.event_types:
            return True

        event_types_str = webhook.event_types.strip()
        if not event_types_str:
            return True

        # Try to parse as JSON array first
        try:
            if event_types_str.startswith("[") and event_types_str.endswith("]"):
                event_types_list = json.loads(event_types_str)
                if isinstance(event_types_list, list):
                    result = event_type in event_types_list or "*" in event_types_list
                    return result
        except (json.JSONDecodeError, TypeError) as e:
            logger.info(f"Webhook {webhook.id}: Failed to parse as JSON: {e}")
            pass

        # Try comma-separated format
        if "," in event_types_str:
            event_types_list = [
                et.strip().strip("\"'") for et in event_types_str.split(",")
            ]
            result = event_type in event_types_list or "*" in event_types_list
            return result

        # Single event type (remove quotes if present)
        single_event = event_types_str.strip("\"'")
        result = single_event == event_type or single_event == "*"
        return result

    def _is_circuit_open(self, webhook_id: str) -> bool:
        """Check if circuit breaker is open for webhook"""
        if webhook_id not in self._circuit_breakers:
            return False

        breaker = self._circuit_breakers[webhook_id]
        if breaker["failures"] >= 5:  # Open circuit after 5 consecutive failures
            # Check if cooldown period has passed (5 minutes)
            if time.time() - breaker["last_failure"] > 300:
                # Reset circuit breaker
                del self._circuit_breakers[webhook_id]
                return False
            return True
        return False

    async def _send_webhook(
        self, webhook: WebhookOutgoing, event: WebhookEventPayload, retry_count: int = 0
    ):
        """Send webhook with retry logic"""
        session = get_session()
        start_time = time.time()

        try:
            # Prepare payload
            payload = event.model_dump()
            payload["timestamp"] = payload["timestamp"].isoformat()

            # Transform payload for specific platforms
            original_payload = payload.copy()
            payload = self._transform_payload_for_platform(webhook.target_url, payload)

            # Log payload transformation for Discord webhooks
            if "discord.com/api/webhooks" in webhook.target_url:
                logger.debug(
                    f"Original payload: {json.dumps(original_payload, default=str)}"
                )
                logger.debug(f"Discord payload: {json.dumps(payload, default=str)}")

            # Add signature if secret is configured
            headers = safe_json_loads(webhook.headers, {})

            if webhook.secret:
                signature = self._generate_signature(
                    webhook.secret, json.dumps(payload)
                )
                headers["X-Webhook-Signature"] = signature

            # Send HTTP request
            async with httpx.AsyncClient(timeout=webhook.timeout) as client:
                response = await client.post(
                    webhook.target_url, json=payload, headers=headers
                )

            processing_time = int((time.time() - start_time) * 1000)

            log_entry = WebhookLog(
                id=str(uuid.uuid4()),
                webhook_id=webhook.id,
                direction="outgoing",
                payload=json.dumps(payload),
                response=response.text[:1000],  # Limit response size
                status_code=response.status_code,
                retry_count=0,
            )
            session.add(log_entry)

            # Update webhook statistics
            webhook.total_events_sent += 1
            webhook.successful_deliveries += 1
            webhook.consecutive_failures = 0

            # Reset circuit breaker on success
            if webhook.id in self._circuit_breakers:
                del self._circuit_breakers[webhook.id]

            session.commit()

        except Exception as e:
            # Handle failure
            logger.error(f"Webhook {webhook.id} delivery failed: {e}")
            processing_time = int((time.time() - start_time) * 1000)

            # Log failed delivery
            log_entry = WebhookLog(
                id=str(uuid.uuid4()),
                webhook_id=webhook.id,
                direction="outgoing",
                payload=json.dumps(
                    payload if "payload" in locals() else event.model_dump()
                ),
                response=None,
                status_code=None,
                retry_count=retry_count,
                error_message=str(e),
            )
            session.add(log_entry)

            # Update webhook statistics
            webhook.total_events_sent += 1
            webhook.failed_deliveries += 1
            webhook.consecutive_failures += 1

            session.commit()

            # Update circuit breaker
            if webhook.id not in self._circuit_breakers:
                self._circuit_breakers[webhook.id] = {"failures": 0, "last_failure": 0}
            self._circuit_breakers[webhook.id]["failures"] += 1
            self._circuit_breakers[webhook.id]["last_failure"] = time.time()

            # Retry logic
            if retry_count < webhook.retry_count:
                await asyncio.sleep(webhook.retry_delay)
                await self._send_webhook(webhook, event, retry_count + 1)
            else:
                logger.error(
                    f"Failed to deliver webhook {webhook.id} after {retry_count} retries: {e}"
                )

        finally:
            session.close()

    def _generate_signature(self, secret: str, payload: str) -> str:
        """Generate HMAC signature for webhook payload"""
        return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _transform_payload_for_platform(
        self, target_url: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Transform payload based on the target platform"""
        # Discord webhook detection
        if "discord.com/api/webhooks" in target_url:
            return self._transform_for_discord(payload)

        # Add other platform transformations here in the future
        # elif "slack.com" in target_url:
        #     return self._transform_for_slack(payload)
        # elif "teams.microsoft.com" in target_url:
        #     return self._transform_for_teams(payload)

        return payload

    def _transform_for_discord(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Transform payload for Discord webhook format - handles any event type"""
        try:
            event_type = payload.get("event_type", "Unknown Event")
            agent_name = payload.get("agent_name", "XT")
            timestamp = payload.get("timestamp", "")
            data = payload.get("data", {})
            user_id = payload.get("user_id", "Unknown User")

            # Create emoji and message based on event type
            emoji_map = {
                "command.executed": "🤖",
                "chat.completed": "💬",
                "task.completed": "✅",
                "task.started": "🚀",
                "training.completed": "🎓",
                "training.started": "📚",
                "agent.created": "👤",
                "agent.updated": "🔄",
                "error.occurred": "❌",
                "webhook.test": "🧪",
                "conversation.started": "💭",
                "conversation.ended": "🏁",
                "file.processed": "📁",
                "memory.stored": "🧠",
                "extension.executed": "🔧",
            }

            emoji = emoji_map.get(event_type, "ℹ️")

            # Create content message
            if event_type == "command.executed":
                content = f"{emoji} **{agent_name}** executed a command"
                if "command" in data:
                    content += f": `{data['command']}`"
            elif event_type == "chat.completed":
                content = f"{emoji} **{agent_name}** completed a chat"
                if "message" in data:
                    message = str(data["message"])[:100]
                    if len(str(data.get("message", ""))) > 100:
                        message += "..."
                    content += f"\n> {message}"
            elif event_type == "task.completed":
                content = f"{emoji} **{agent_name}** completed a task"
                if "task_name" in data:
                    content += f": {data['task_name']}"
            elif event_type == "webhook.test":
                content = f"{emoji} **Test webhook** from **{agent_name}**"
                if "message" in data:
                    content += f"\n> {data['message']}"
            else:
                content = f"{emoji} **{agent_name}** triggered event: **{event_type}**"
                # Add any key data fields to the message
                if data and isinstance(data, dict):
                    key_fields = ["message", "task_name", "command", "status", "result"]
                    for field in key_fields:
                        if field in data and data[field]:
                            value = str(data[field])[:100]
                            if len(str(data[field])) > 100:
                                value += "..."
                            content += (
                                f"\n**{field.replace('_', ' ').title()}:** {value}"
                            )
                            break  # Only show the first key field found

            # Create Discord-compatible payload
            discord_payload = {
                "content": content,
                "embeds": [
                    {
                        "title": f"AGiXT Event: {event_type}",
                        "color": 3447003,  # Blue color
                        "fields": [
                            {"name": "Agent", "value": agent_name, "inline": True},
                            {"name": "Time", "value": timestamp, "inline": True},
                        ],
                        "footer": {"text": "AGiXT Webhook System"},
                    }
                ],
            }

            # Add additional fields from data
            if data:
                embed_fields = discord_payload["embeds"][0]["fields"]
                for key, value in data.items():
                    if (
                        key not in ["command", "message", "task_name"]
                        and len(embed_fields) < 25
                    ):  # Discord limit
                        embed_fields.append(
                            {
                                "name": key.replace("_", " ").title(),
                                "value": str(value)[:1024],  # Discord field value limit
                                "inline": True,
                            }
                        )

            return discord_payload

        except Exception as e:
            logger.error(f"Error transforming payload for Discord: {e}")
            # Fallback to simple message if transformation fails
            return {
                "content": f"AGiXT Event: {payload.get('event_type', 'Unknown')} from {payload.get('agent_name', 'Unknown Agent')}"
            }


class WebhookManager:
    """
    Manager class for webhook CRUD operations and incoming webhook processing
    """

    def __init__(self):
        self.event_emitter = WebhookEventEmitter()

    def create_incoming_webhook(
        self, user_id: str, webhook_data: WebhookIncomingCreate
    ) -> Dict[str, Any]:
        """Create a new incoming webhook"""
        session = get_session()

        try:
            webhook_id = str(uuid.uuid4())
            api_key = self._generate_api_key()

            webhook = WebhookIncoming(
                id=str(uuid.uuid4()),
                webhook_id=webhook_id,
                name=webhook_data.name,
                agent_id=webhook_data.agent_id,
                user_id=user_id,
                api_key=api_key,
                description=webhook_data.description,
                active=webhook_data.active,
            )

            session.add(webhook)
            session.commit()

            return {
                "webhook_id": webhook_id,
                "api_key": api_key,
                "webhook_url": f"/api/webhook/{webhook_id}",
            }

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def process_incoming_webhook(
        self,
        webhook_id: str,
        api_key: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        source_ip: str,
    ) -> Dict[str, Any]:
        """Process an incoming webhook request"""
        session = get_session()
        start_time = time.time()

        try:
            # Find webhook
            webhook = (
                session.query(WebhookIncoming)
                .filter_by(webhook_id=webhook_id, api_key=api_key)
                .first()
            )

            if not webhook:
                raise ValueError("Invalid webhook ID or API key")

            if not webhook.active:
                raise ValueError("Webhook is not active")

            # Process webhook (integrate with agent)
            result = self._process_with_agent(webhook, payload)

            processing_time = int((time.time() - start_time) * 1000)

            # Log successful processing
            log_entry = WebhookLog(
                id=str(uuid.uuid4()),
                webhook_id=webhook.id,
                direction="incoming",
                payload=json.dumps(payload),
                response=json.dumps(result)[:1000],
                status_code=200,
                retry_count=0,
            )
            session.add(log_entry)

            session.commit()

            return result

        except Exception as e:
            # Log failed processing
            if "webhook" in locals():
                processing_time = int((time.time() - start_time) * 1000)
                log_entry = WebhookLog(
                    id=str(uuid.uuid4()),
                    webhook_id=webhook.id if webhook else webhook_id,
                    direction="incoming",
                    payload=json.dumps(payload),
                    response=None,
                    status_code=500,
                    retry_count=0,
                    error_message=str(e),
                )
                session.add(log_entry)

                session.commit()

            raise e

        finally:
            session.close()

    def _generate_api_key(self) -> str:
        """Generate a secure API key"""
        return str(uuid.uuid4()).replace("-", "") + str(uuid.uuid4()).replace("-", "")

    def _transform_payload_for_platform(
        self, target_url: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Transform payload based on the target platform"""
        # Discord webhook detection
        if "discord.com/api/webhooks" in target_url:
            return self._transform_for_discord(payload)

        # Add other platform transformations here in the future
        # elif "slack.com" in target_url:
        #     return self._transform_for_slack(payload)
        # elif "teams.microsoft.com" in target_url:
        #     return self._transform_for_teams(payload)

        return payload

    def _transform_for_discord(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Transform payload for Discord webhook format - handles any event type"""
        try:
            event_type = payload.get("event_type", "Unknown Event")
            agent_name = payload.get("agent_name", "XT")
            timestamp = payload.get("timestamp", "")
            data = payload.get("data", {})
            user_id = payload.get("user_id", "Unknown User")

            # Create emoji and message based on event type
            emoji_map = {
                "command.executed": "🤖",
                "chat.completed": "💬",
                "task.completed": "✅",
                "task.started": "🚀",
                "training.completed": "🎓",
                "training.started": "📚",
                "agent.created": "👤",
                "agent.updated": "🔄",
                "error.occurred": "❌",
                "webhook.test": "🧪",
                "conversation.started": "💭",
                "conversation.ended": "🏁",
                "file.processed": "📁",
                "memory.stored": "🧠",
                "extension.executed": "🔧",
            }

            emoji = emoji_map.get(event_type, "ℹ️")

            # Create content message
            if event_type == "command.executed":
                content = f"{emoji} **{agent_name}** executed a command"
                if "command" in data:
                    content += f": `{data['command']}`"
            elif event_type == "chat.completed":
                content = f"{emoji} **{agent_name}** completed a chat"
                if "message" in data:
                    message = str(data["message"])[:100]
                    if len(str(data.get("message", ""))) > 100:
                        message += "..."
                    content += f"\n> {message}"
            elif event_type == "task.completed":
                content = f"{emoji} **{agent_name}** completed a task"
                if "task_name" in data:
                    content += f": {data['task_name']}"
            elif event_type == "webhook.test":
                content = f"{emoji} **Test webhook** from **{agent_name}**"
                if "message" in data:
                    content += f"\n> {data['message']}"
            else:
                content = f"{emoji} **{agent_name}** triggered event: **{event_type}**"
                # Add any key data fields to the message
                if data and isinstance(data, dict):
                    key_fields = ["message", "task_name", "command", "status", "result"]
                    for field in key_fields:
                        if field in data and data[field]:
                            value = str(data[field])[:100]
                            if len(str(data[field])) > 100:
                                value += "..."
                            content += (
                                f"\n**{field.replace('_', ' ').title()}:** {value}"
                            )
                            break  # Only show the first key field found

            # Create Discord-compatible payload
            discord_payload = {
                "content": content,
                "embeds": [
                    {
                        "title": f"AGiXT Event: {event_type}",
                        "color": 3447003,  # Blue color
                        "fields": [
                            {"name": "Agent", "value": agent_name, "inline": True},
                            {"name": "Time", "value": timestamp, "inline": True},
                        ],
                        "footer": {"text": "AGiXT Webhook System"},
                    }
                ],
            }

            # Add additional fields from data
            if data:
                embed_fields = discord_payload["embeds"][0]["fields"]
                for key, value in data.items():
                    if (
                        key not in ["command", "message", "task_name"]
                        and len(embed_fields) < 25
                    ):  # Discord limit
                        embed_fields.append(
                            {
                                "name": key.replace("_", " ").title(),
                                "value": str(value)[:1024],  # Discord field value limit
                                "inline": True,
                            }
                        )

            return discord_payload

        except Exception as e:
            logger.error(f"Error transforming payload for Discord: {e}")
            # Fallback to simple message if transformation fails
            return {
                "content": f"AGiXT Event: {payload.get('event_type', 'Unknown')} from {payload.get('agent_name', 'Unknown Agent')}"
            }

    def _process_with_agent(
        self, webhook: WebhookIncoming, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process webhook payload with associated agent"""
        # This will be integrated with the Agent system
        # For now, return a placeholder response
        return {
            "status": "processed",
            "agent_id": webhook.agent_id,
            "webhook_name": webhook.name,
            "payload_received": payload,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def create_outgoing_webhook(
        self, user_id: str, company_id: str, webhook_data: WebhookOutgoingCreate
    ) -> str:
        """Create a new outgoing webhook subscription"""
        session = get_session()

        try:
            webhook_id = str(uuid.uuid4())

            webhook = WebhookOutgoing(
                id=webhook_id,
                name=webhook_data.name,
                description=webhook_data.description,
                user_id=user_id,
                company_id=company_id,
                target_url=webhook_data.target_url,
                event_types=(
                    json.dumps(webhook_data.event_types)
                    if webhook_data.event_types
                    else "[]"
                ),
                headers=(
                    json.dumps(webhook_data.headers) if webhook_data.headers else "{}"
                ),
                secret=webhook_data.secret,
                retry_count=webhook_data.retry_count,
                retry_delay=webhook_data.retry_delay,
                timeout=webhook_data.timeout,
                active=webhook_data.active,
                filters=(
                    json.dumps(webhook_data.filters) if webhook_data.filters else "{}"
                ),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                consecutive_failures=0,
                total_events_sent=0,
                successful_deliveries=0,
                failed_deliveries=0,
            )

            session.add(webhook)
            session.commit()

            return webhook_id

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_webhook_statistics(
        self, webhook_id: str, webhook_type: str = "incoming"
    ) -> Dict[str, Any]:
        """Get statistics for a webhook"""
        session = get_session()

        try:
            if webhook_type == "incoming":
                webhook = (
                    session.query(WebhookIncoming)
                    .filter_by(webhook_id=webhook_id)
                    .first()
                )
                if webhook:
                    return {
                        "webhook_id": webhook.webhook_id,
                        "webhook_type": "incoming",
                        "created_at": webhook.created_at.isoformat(),
                        "updated_at": webhook.updated_at.isoformat(),
                    }
            else:
                webhook = (
                    session.query(WebhookOutgoing).filter_by(id=webhook_id).first()
                )
                if webhook:
                    return {
                        "webhook_id": webhook.id,
                        "webhook_type": "outgoing",
                        "total_events_sent": webhook.total_events_sent,
                        "successful_deliveries": webhook.successful_deliveries,
                        "failed_deliveries": webhook.failed_deliveries,
                        "consecutive_failures": webhook.consecutive_failures,
                        "created_at": webhook.created_at.isoformat(),
                        "updated_at": webhook.updated_at.isoformat(),
                    }

            return None

        finally:
            session.close()


# Define available core webhook event types
CORE_WEBHOOK_EVENT_TYPES = [
    {"type": "command.executed", "description": "Triggered when a command is executed"},
    {
        "type": "command.failed",
        "description": "Triggered when a command execution fails",
    },
    {
        "type": "chat.started",
        "description": "Triggered when a chat conversation starts",
    },
    {
        "type": "chat.completed",
        "description": "Triggered when a chat conversation completes",
    },
    {"type": "chat.message", "description": "Triggered for each chat message"},
    {"type": "agent.created", "description": "Triggered when an agent is created"},
    {"type": "agent.updated", "description": "Triggered when an agent is updated"},
    {"type": "agent.deleted", "description": "Triggered when an agent is deleted"},
    {"type": "memory.created", "description": "Triggered when a memory is created"},
    {"type": "memory.updated", "description": "Triggered when a memory is updated"},
    {"type": "memory.deleted", "description": "Triggered when a memory is deleted"},
    {"type": "chain.started", "description": "Triggered when a chain execution starts"},
    {
        "type": "chain.step.completed",
        "description": "Triggered when a chain step completes",
    },
    {
        "type": "chain.completed",
        "description": "Triggered when a chain execution completes",
    },
    {"type": "chain.failed", "description": "Triggered when a chain execution fails"},
    {"type": "task.created", "description": "Triggered when a task is created"},
    {"type": "task.started", "description": "Triggered when a task starts"},
    {"type": "task.completed", "description": "Triggered when a task completes"},
    {"type": "task.failed", "description": "Triggered when a task fails"},
    {
        "type": "provider.changed",
        "description": "Triggered when provider settings change",
    },
    {
        "type": "extension.enabled",
        "description": "Triggered when an extension is enabled",
    },
    {
        "type": "extension.disabled",
        "description": "Triggered when an extension is disabled",
    },
    {"type": "file.uploaded", "description": "Triggered when a file is uploaded"},
    {"type": "file.processed", "description": "Triggered when a file is processed"},
    {
        "type": "transcription.completed",
        "description": "Triggered when transcription completes",
    },
    {"type": "training.started", "description": "Triggered when training starts"},
    {"type": "training.completed", "description": "Triggered when training completes"},
    {
        "type": "conversation.started",
        "description": "Triggered when a conversation starts",
    },
    {
        "type": "conversation.ended",
        "description": "Triggered when a conversation ends",
    },
    {"type": "webhook.test", "description": "Test webhook event"},
]


def get_all_webhook_event_types():
    """Get all webhook event types including core events and extension events"""
    # Import here to avoid circular imports during module initialization
    # This function will be called on-demand rather than at import time
    try:
        from Extensions import Extensions

        extension_events = Extensions.get_extension_webhook_events()
    except Exception as e:
        logging.error(f"Error loading extension webhook events: {e}")
        extension_events = []

    # Combine core events with extension events
    all_events = CORE_WEBHOOK_EVENT_TYPES.copy()
    all_events.extend(extension_events)

    return all_events


def get_webhook_event_types():
    """Get webhook event types - called on demand to avoid circular imports"""
    return get_all_webhook_event_types()


# Initialize with just core events to avoid circular import at module load time
# Extension events will be loaded on-demand when get_all_webhook_event_types() is called
WEBHOOK_EVENT_TYPES = CORE_WEBHOOK_EVENT_TYPES.copy()

# Create singleton instance for import
webhook_emitter = WebhookEventEmitter()
