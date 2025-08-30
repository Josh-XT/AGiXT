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

from DB import WebhookIncoming, WebhookOutgoing, WebhookLog, get_session
from Models import (
    WebhookEventPayload,
    WebhookIncomingCreate,
    WebhookOutgoingCreate,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            company_id: Optional company ID
            metadata: Optional additional metadata

        Returns:
            Event ID for tracking
        """
        event_id = str(uuid.uuid4())

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
            # Find all active webhooks subscribed to this event type
            webhooks = (
                session.query(WebhookOutgoing)
                .filter(
                    and_(
                        WebhookOutgoing.active == True,
                        WebhookOutgoing.event_types.contains([event.event_type]),
                    )
                )
                .all()
            )

            for webhook in webhooks:
                # Check if webhook matches filters
                if self._matches_filters(webhook, event):
                    # Check circuit breaker
                    if self._is_circuit_open(webhook.id):
                        logger.warning(f"Circuit breaker open for webhook {webhook.id}")
                        continue

                    # Send webhook
                    asyncio.create_task(self._send_webhook(webhook, event))

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

        filters = webhook.filters

        # Check agent filter
        if "agent_id" in filters and event.agent_id != filters["agent_id"]:
            return False
        if "agent_name" in filters and event.agent_name != filters["agent_name"]:
            return False

        # Check user filter
        if "user_id" in filters and event.user_id != filters["user_id"]:
            return False

        # Check company filter
        if "company_id" in filters and event.company_id != filters["company_id"]:
            return False

        return True

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

            # Add signature if secret is configured
            headers = webhook.headers.copy() if webhook.headers else {}
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

            # Log successful delivery
            log_entry = WebhookLog(
                id=str(uuid.uuid4()),
                webhook_type="outgoing",
                webhook_id=webhook.id,
                event_type=event.event_type,
                request_payload=payload,
                request_headers=headers,
                response_status=response.status_code,
                response_body=response.text[:1000],  # Limit response size
                retry_count=retry_count,
                processing_time_ms=processing_time,
                created_at=datetime.utcnow(),
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
            processing_time = int((time.time() - start_time) * 1000)

            # Log failed delivery
            log_entry = WebhookLog(
                id=str(uuid.uuid4()),
                webhook_type="outgoing",
                webhook_id=webhook.id,
                event_type=event.event_type,
                request_payload=(
                    payload if "payload" in locals() else event.model_dump()
                ),
                request_headers=headers if "headers" in locals() else {},
                response_status=None,
                error_message=str(e),
                retry_count=retry_count,
                processing_time_ms=processing_time,
                created_at=datetime.utcnow(),
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


class WebhookManager:
    """
    Manager class for webhook CRUD operations and incoming webhook processing
    """

    def __init__(self):
        self.event_emitter = WebhookEventEmitter()

    def create_incoming_webhook(
        self, user_id: str, company_id: str, webhook_data: WebhookIncomingCreate
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
                company_id=company_id,
                api_key=api_key,
                description=webhook_data.description,
                payload_transformation=webhook_data.payload_transformation,
                rate_limit=webhook_data.rate_limit,
                allowed_ips=webhook_data.allowed_ips,
                active=webhook_data.active,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
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

            # Check IP whitelist
            if webhook.allowed_ips and source_ip not in webhook.allowed_ips:
                raise ValueError(f"IP {source_ip} not allowed")

            # Check rate limit
            if not self._check_rate_limit(webhook_id, webhook.rate_limit):
                raise ValueError("Rate limit exceeded")

            # Transform payload if configured
            if webhook.payload_transformation:
                payload = self._transform_payload(
                    payload, webhook.payload_transformation
                )

            # Process webhook (integrate with agent)
            result = self._process_with_agent(webhook, payload)

            processing_time = int((time.time() - start_time) * 1000)

            # Log successful processing
            log_entry = WebhookLog(
                id=str(uuid.uuid4()),
                webhook_type="incoming",
                webhook_id=webhook.id,
                request_payload=payload,
                request_headers=headers,
                response_status=200,
                response_body=json.dumps(result)[:1000],
                retry_count=0,
                processing_time_ms=processing_time,
                created_at=datetime.utcnow(),
            )
            session.add(log_entry)

            # Update statistics
            webhook.total_requests += 1
            webhook.successful_requests += 1
            webhook.updated_at = datetime.utcnow()

            session.commit()

            return result

        except Exception as e:
            # Log failed processing
            if "webhook" in locals():
                processing_time = int((time.time() - start_time) * 1000)
                log_entry = WebhookLog(
                    id=str(uuid.uuid4()),
                    webhook_type="incoming",
                    webhook_id=webhook.id if webhook else webhook_id,
                    request_payload=payload,
                    request_headers=headers,
                    response_status=500,
                    error_message=str(e),
                    retry_count=0,
                    processing_time_ms=processing_time,
                    created_at=datetime.utcnow(),
                )
                session.add(log_entry)

                if webhook:
                    webhook.total_requests += 1
                    webhook.failed_requests += 1
                    webhook.updated_at = datetime.utcnow()

                session.commit()

            raise e

        finally:
            session.close()

    def _generate_api_key(self) -> str:
        """Generate a secure API key"""
        return str(uuid.uuid4()).replace("-", "") + str(uuid.uuid4()).replace("-", "")

    def _check_rate_limit(self, webhook_id: str, limit: int) -> bool:
        """Check if request exceeds rate limit"""
        current_time = time.time()
        rate_info = self.event_emitter._rate_limits[webhook_id]

        # Reset counter if minute has passed
        if current_time - rate_info["reset_time"] > 60:
            rate_info["count"] = 0
            rate_info["reset_time"] = current_time

        rate_info["count"] += 1
        return rate_info["count"] <= limit

    def _transform_payload(
        self, payload: Dict[str, Any], transformation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Transform incoming payload based on mapping configuration"""
        result = {}

        for target_key, source_path in transformation.items():
            # Support nested path extraction (e.g., "data.user.name")
            value = payload
            for key in source_path.split("."):
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break

            if value is not None:
                result[target_key] = value

        return result

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
                user_id=user_id,
                company_id=company_id,
                target_url=webhook_data.target_url,
                event_types=webhook_data.event_types,
                headers=webhook_data.headers,
                secret=webhook_data.secret,
                retry_count=webhook_data.retry_count,
                retry_delay=webhook_data.retry_delay,
                timeout=webhook_data.timeout,
                active=webhook_data.active,
                filters=webhook_data.filters,
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
                        "total_requests": webhook.total_requests,
                        "successful_requests": webhook.successful_requests,
                        "failed_requests": webhook.failed_requests,
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


# Define available webhook event types
WEBHOOK_EVENT_TYPES = [
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
]

# Create singleton instance for import
webhook_emitter = WebhookEventEmitter()
