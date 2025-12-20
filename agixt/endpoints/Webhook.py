"""
Webhook API Endpoints for AGiXT
Handles incoming and outgoing webhook management and processing
"""

from fastapi import APIRouter, HTTPException, Request, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import logging
import asyncio
import json
from datetime import datetime
import uuid

from MagicalAuth import (
    MagicalAuth,
    verify_api_key,
    convert_time,
    is_admin,
    require_scope,
)
from fastapi import Header
from Models import (
    WebhookIncomingCreate,
    WebhookIncomingUpdate,
    WebhookIncomingResponse,
    WebhookOutgoingCreate,
    WebhookOutgoingUpdate,
    WebhookOutgoingResponse,
    WebhookTestPayload,
    WebhookStatistics,
    WebhookEventTypeList,
    WebhookLogResponse,
    Detail,
)
from WebhookManager import (
    WebhookManager,
    WebhookEventEmitter,
    get_all_webhook_event_types,
)
from DB import (
    WebhookIncoming,
    WebhookOutgoing,
    WebhookLog,
    get_session,
    DATABASE_TYPE,
)
from sqlalchemy import and_, or_, desc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = APIRouter()


def safe_json_loads(json_str, default=None):
    """Safely load JSON string, returning default value on error"""
    if not json_str:
        return default
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


auth = MagicalAuth()
webhook_manager = WebhookManager()
event_emitter = WebhookEventEmitter()


@app.post("/v1/webhook/{webhook_id}", tags=["Webhooks"])
async def process_webhook(
    webhook_id: str, request: Request, background_tasks: BackgroundTasks
):
    """
    Process an incoming webhook request

    This endpoint receives webhook payloads from external systems.
    The webhook must be authenticated with the API key in the Authorization header.
    """
    try:
        # Get API key from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401, detail="Missing or invalid authorization header"
            )

        api_key = auth_header.replace("Bearer ", "")

        # Get request data
        payload = await request.json()
        headers = dict(request.headers)
        source_ip = request.client.host if request.client else "unknown"

        # Process webhook
        result = webhook_manager.process_incoming_webhook(
            webhook_id=webhook_id,
            api_key=api_key,
            payload=payload,
            headers=headers,
            source_ip=source_ip,
        )

        return JSONResponse(content=result, status_code=200)

    except ValueError as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post(
    "/api/webhooks/incoming",
    response_model=WebhookIncomingResponse,
    tags=["Webhooks"],
    summary="Create incoming webhook",
    dependencies=[Depends(require_scope("webhooks:write"))],
)
async def create_incoming_webhook(
    webhook_data: WebhookIncomingCreate,
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Create a new incoming webhook

    This creates a webhook endpoint that can receive data from external systems
    and route it to the specified agent for processing.
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        # Get user to verify existence
        session = get_session()
        user = auth.get_user_by_id(session, user_id)
        if not user:
            session.close()
            raise HTTPException(status_code=404, detail="User not found")

        # Handle agent_name to agent_id conversion if needed
        if webhook_data.agent_name and not webhook_data.agent_id:
            from DB import Agent

            agent = (
                session.query(Agent)
                .filter_by(name=webhook_data.agent_name, user_id=user_id)
                .first()
            )
            if not agent:
                session.close()
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{webhook_data.agent_name}' not found",
                )
            webhook_data.agent_id = str(agent.id)

        session.close()

        # Create webhook
        webhook_info = webhook_manager.create_incoming_webhook(
            user_id=user_id, webhook_data=webhook_data
        )

        # Get full webhook details for response
        session = get_session()
        webhook = (
            session.query(WebhookIncoming)
            .filter_by(webhook_id=webhook_info["webhook_id"])
            .first()
        )
        session.close()

        return WebhookIncomingResponse(
            webhook_id=webhook.webhook_id,
            name=webhook.name,
            agent_id=webhook.agent_id,
            api_key=webhook_info["api_key"],
            webhook_url=webhook_info["webhook_url"],
            description=webhook.description,
            active=webhook.active,
            created_at=(
                convert_time(webhook.created_at, user_id=user_id)
                if webhook.created_at
                else None
            ),
            updated_at=(
                convert_time(webhook.updated_at, user_id=user_id)
                if webhook.updated_at
                else None
            ),
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error creating incoming webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/api/webhooks/incoming",
    response_model=List[WebhookIncomingResponse],
    tags=["Webhooks"],
    summary="List incoming webhooks",
    dependencies=[Depends(require_scope("webhooks:read"))],
)
async def list_incoming_webhooks(
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """
    List all incoming webhooks for the user
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Get user to verify they exist
        user = auth.get_user_by_id(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Build query - no need for company_id since we're filtering by user_id
        query = session.query(WebhookIncoming).filter(
            WebhookIncoming.user_id == user_id
        )

        if agent_id:
            query = query.filter(WebhookIncoming.agent_id == agent_id)
        if active is not None:
            query = query.filter(WebhookIncoming.active == active)

        webhooks = query.all()

        result = []
        for webhook in webhooks:
            result.append(
                WebhookIncomingResponse(
                    webhook_id=webhook.webhook_id,
                    name=webhook.name,
                    agent_id=webhook.agent_id,
                    api_key=webhook.api_key,
                    webhook_url=f"/api/webhook/{webhook.webhook_id}",
                    description=webhook.description,
                    active=webhook.active,
                    created_at=(
                        convert_time(webhook.created_at, user_id=user_id)
                        if webhook.created_at
                        else None
                    ),
                    updated_at=(
                        convert_time(webhook.updated_at, user_id=user_id)
                        if webhook.updated_at
                        else None
                    ),
                )
            )

        session.close()
        return result

    except Exception as e:
        logger.error(f"Error listing incoming webhooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put(
    "/api/webhooks/incoming/{webhook_id}",
    response_model=WebhookIncomingResponse,
    tags=["Webhooks"],
    summary="Update incoming webhook",
    dependencies=[Depends(require_scope("webhooks:write"))],
)
async def update_incoming_webhook(
    webhook_id: str,
    webhook_update: WebhookIncomingUpdate,
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Update an existing incoming webhook
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Find webhook
        webhook = (
            session.query(WebhookIncoming)
            .filter_by(webhook_id=webhook_id, user_id=user_id)
            .first()
        )

        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        # Update fields
        if webhook_update.name is not None:
            webhook.name = webhook_update.name
        if webhook_update.description is not None or "description" in getattr(
            webhook_update, "model_fields_set", set()
        ):
            webhook.description = webhook_update.description
        if webhook_update.active is not None:
            webhook.active = webhook_update.active

        session.commit()

        result = WebhookIncomingResponse(
            webhook_id=webhook.webhook_id,
            name=webhook.name,
            agent_id=webhook.agent_id,
            api_key=webhook.api_key,
            webhook_url=f"/api/webhook/{webhook.webhook_id}",
            description=webhook.description,
            active=webhook.active,
            created_at=(
                convert_time(webhook.created_at, user_id=user_id)
                if webhook.created_at
                else None
            ),
            updated_at=(
                convert_time(webhook.updated_at, user_id=user_id)
                if webhook.updated_at
                else None
            ),
        )

        session.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating incoming webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete(
    "/api/webhooks/incoming/{webhook_id}",
    response_model=Detail,
    tags=["Webhooks"],
    summary="Delete incoming webhook",
    dependencies=[Depends(require_scope("webhooks:delete"))],
)
async def delete_incoming_webhook(
    webhook_id: str,
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Delete an incoming webhook
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Find webhook
        webhook = (
            session.query(WebhookIncoming)
            .filter_by(webhook_id=webhook_id, user_id=user_id)
            .first()
        )

        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        # Delete webhook
        session.delete(webhook)
        session.commit()
        session.close()

        return Detail(detail="Webhook deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting incoming webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/webhooks/outgoing",
    response_model=WebhookOutgoingResponse,
    tags=["Webhooks"],
    summary="Create outgoing webhook",
    dependencies=[Depends(require_scope("webhooks:write"))],
)
async def create_outgoing_webhook(
    webhook_data: WebhookOutgoingCreate,
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Create a new outgoing webhook subscription

    This creates a webhook that will be triggered when specified events occur in AGiXT.
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        # Get user's company ID through UserCompany relationship
        session = get_session()
        user = auth.get_user_by_id(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Determine company_id - use provided value or user's default
        company_id = webhook_data.company_id

        if not company_id:
            # Get the user's primary company through UserCompany relationship
            from DB import UserCompany

            user_company = (
                session.query(UserCompany)
                .filter(UserCompany.user_id == user_id)
                .first()
            )
            company_id = user_company.company_id if user_company else None

            if not company_id:
                session.close()
                raise HTTPException(
                    status_code=400,
                    detail="User has no associated company and no company_id provided",
                )

        session.close()

        # Validate event types
        valid_event_types = [et["type"] for et in get_all_webhook_event_types()]
        for event_type in webhook_data.event_types:
            if event_type not in valid_event_types:
                raise HTTPException(
                    status_code=400, detail=f"Invalid event type: {event_type}"
                )

        # Create webhook
        webhook_id = webhook_manager.create_outgoing_webhook(
            user_id=user_id, company_id=company_id, webhook_data=webhook_data
        )

        # Get full webhook details for response
        session = get_session()
        webhook = session.query(WebhookOutgoing).filter_by(id=webhook_id).first()
        session.close()

        return WebhookOutgoingResponse(
            id=str(webhook.id),
            name=webhook.name,
            description=webhook.description,
            target_url=webhook.target_url,
            event_types=safe_json_loads(webhook.event_types, []),
            company_id=str(webhook.company_id) if webhook.company_id else None,
            headers=safe_json_loads(webhook.headers, {}),
            secret=webhook.secret,
            retry_count=webhook.retry_count,
            retry_delay=webhook.retry_delay,
            timeout=webhook.timeout,
            active=webhook.active,
            filters=safe_json_loads(webhook.filters, {}),
            created_at=(
                convert_time(webhook.created_at, user_id=user_id)
                if webhook.created_at
                else None
            ),
            updated_at=(
                convert_time(webhook.updated_at, user_id=user_id)
                if webhook.updated_at
                else None
            ),
            consecutive_failures=webhook.consecutive_failures,
            total_events_sent=webhook.total_events_sent,
            successful_deliveries=webhook.successful_deliveries,
            failed_deliveries=webhook.failed_deliveries,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating outgoing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get(
    "/api/webhooks/outgoing",
    response_model=List[WebhookOutgoingResponse],
    tags=["Webhooks"],
    summary="List outgoing webhooks",
    dependencies=[Depends(require_scope("webhooks:read"))],
)
async def list_outgoing_webhooks(
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """
    List all outgoing webhook subscriptions for the user
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Build query
        query = session.query(WebhookOutgoing).filter(
            WebhookOutgoing.user_id == user_id
        )

        if event_type:
            query = query.filter(WebhookOutgoing.event_types.contains([event_type]))
        if active is not None:
            query = query.filter(WebhookOutgoing.active == active)

        webhooks = query.all()

        result = []
        for webhook in webhooks:
            result.append(
                WebhookOutgoingResponse(
                    id=str(webhook.id),
                    name=webhook.name,
                    description=webhook.description,
                    target_url=webhook.target_url,
                    event_types=safe_json_loads(webhook.event_types, []),
                    company_id=str(webhook.company_id) if webhook.company_id else None,
                    headers=safe_json_loads(webhook.headers, {}),
                    secret=webhook.secret,
                    retry_count=webhook.retry_count,
                    retry_delay=webhook.retry_delay,
                    timeout=webhook.timeout,
                    active=webhook.active,
                    filters=safe_json_loads(webhook.filters, {}),
                    created_at=(
                        convert_time(webhook.created_at, user_id=user_id)
                        if webhook.created_at
                        else None
                    ),
                    updated_at=(
                        convert_time(webhook.updated_at, user_id=user_id)
                        if webhook.updated_at
                        else None
                    ),
                    consecutive_failures=webhook.consecutive_failures,
                    total_events_sent=webhook.total_events_sent,
                    successful_deliveries=webhook.successful_deliveries,
                    failed_deliveries=webhook.failed_deliveries,
                )
            )

        session.close()
        return result

    except Exception as e:
        logger.error(f"Error listing outgoing webhooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put(
    "/api/webhooks/outgoing/{webhook_id}",
    response_model=WebhookOutgoingResponse,
    tags=["Webhooks"],
    summary="Update outgoing webhook",
    dependencies=[Depends(require_scope("webhooks:write"))],
)
async def update_outgoing_webhook(
    webhook_id: str,
    webhook_update: WebhookOutgoingUpdate,
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Update an existing outgoing webhook subscription
    """
    session = None
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Determine correct ID type based on database configuration
        webhook_identifier: Any = webhook_id
        if DATABASE_TYPE != "sqlite":
            try:
                webhook_identifier = uuid.UUID(str(webhook_id))
            except (ValueError, AttributeError):
                raise HTTPException(status_code=400, detail="Invalid webhook id")

        # Find webhook scoped to requesting user
        webhook = (
            session.query(WebhookOutgoing)
            .filter(
                WebhookOutgoing.id == webhook_identifier,
                WebhookOutgoing.user_id == user_id,
            )
            .first()
        )

        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        # Validate event types if provided
        if webhook_update.event_types is not None:
            valid_event_types = [et["type"] for et in get_all_webhook_event_types()]
            for event_type in webhook_update.event_types:
                if event_type not in valid_event_types:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid event type: {event_type}"
                    )

        # Update fields
        if webhook_update.name is not None:
            webhook.name = webhook_update.name
        if webhook_update.description is not None:
            webhook.description = webhook_update.description
        if webhook_update.target_url is not None:
            webhook.target_url = webhook_update.target_url
        if webhook_update.event_types is not None:
            webhook.event_types = json.dumps(webhook_update.event_types)
        if webhook_update.company_id is not None or "company_id" in getattr(
            webhook_update, "model_fields_set", set()
        ):
            company_id_value = webhook_update.company_id
            if company_id_value in (None, ""):
                webhook.company_id = None
            elif DATABASE_TYPE != "sqlite":
                try:
                    webhook.company_id = uuid.UUID(str(company_id_value))
                except (ValueError, AttributeError):
                    raise HTTPException(status_code=400, detail="Invalid company id")
            else:
                webhook.company_id = company_id_value
        if webhook_update.headers is not None:
            webhook.headers = json.dumps(webhook_update.headers)
        if webhook_update.secret is not None:
            webhook.secret = webhook_update.secret
        if webhook_update.retry_count is not None:
            webhook.retry_count = webhook_update.retry_count
        if webhook_update.retry_delay is not None:
            webhook.retry_delay = webhook_update.retry_delay
        if webhook_update.timeout is not None:
            webhook.timeout = webhook_update.timeout
        if webhook_update.active is not None:
            webhook.active = webhook_update.active
        if webhook_update.filters is not None:
            webhook.filters = json.dumps(webhook_update.filters)

        webhook.updated_at = datetime.utcnow()

        session.commit()

        return WebhookOutgoingResponse(
            id=str(webhook.id),
            name=webhook.name,
            description=webhook.description,
            target_url=webhook.target_url,
            event_types=safe_json_loads(webhook.event_types, []),
            company_id=str(webhook.company_id) if webhook.company_id else None,
            headers=safe_json_loads(webhook.headers, {}),
            secret=webhook.secret,
            retry_count=webhook.retry_count,
            retry_delay=webhook.retry_delay,
            timeout=webhook.timeout,
            active=webhook.active,
            filters=safe_json_loads(webhook.filters, {}),
            created_at=(
                convert_time(webhook.created_at, user_id=user_id)
                if webhook.created_at
                else None
            ),
            updated_at=(
                convert_time(webhook.updated_at, user_id=user_id)
                if webhook.updated_at
                else None
            ),
            consecutive_failures=webhook.consecutive_failures,
            total_events_sent=webhook.total_events_sent,
            successful_deliveries=webhook.successful_deliveries,
            failed_deliveries=webhook.failed_deliveries,
        )

    except HTTPException:
        if session is not None:
            session.rollback()
        raise
    except Exception as e:
        if session is not None:
            session.rollback()
        logger.error(f"Error updating outgoing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as close_error:
                logger.error(f"Error closing session: {close_error}")


@app.delete(
    "/api/webhooks/outgoing/{webhook_id}",
    response_model=Detail,
    tags=["Webhooks"],
    summary="Delete outgoing webhook",
    dependencies=[Depends(require_scope("webhooks:delete"))],
)
async def delete_outgoing_webhook(
    webhook_id: str,
    user_data: dict = Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Delete an outgoing webhook subscription
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Find webhook
        webhook = (
            session.query(WebhookOutgoing)
            .filter_by(id=webhook_id, user_id=user_id)
            .first()
        )

        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        # Delete webhook
        session.delete(webhook)
        session.commit()
        session.close()

        return Detail(detail="Webhook deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting outgoing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/webhooks/event-types",
    response_model=WebhookEventTypeList,
    tags=["Webhooks"],
    summary="List available webhook event types",
)
async def list_webhook_event_types():
    """
    Get a list of all available webhook event types
    """
    return WebhookEventTypeList(event_types=get_all_webhook_event_types())


@app.get(
    "/api/webhooks/stats",
    response_model=Dict[str, Any],
    tags=["Webhooks"],
    summary="Get global webhook statistics",
)
async def get_global_webhook_stats(
    user_data: dict = Depends(verify_api_key),
):
    """
    Get global webhook statistics for the user
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Get counts of webhooks
        incoming_count = (
            session.query(WebhookIncoming).filter_by(user_id=user_id).count()
        )
        outgoing_count = (
            session.query(WebhookOutgoing).filter_by(user_id=user_id).count()
        )

        # Get active webhooks
        active_incoming = (
            session.query(WebhookIncoming)
            .filter_by(user_id=user_id, active=True)
            .count()
        )
        active_outgoing = (
            session.query(WebhookOutgoing)
            .filter_by(user_id=user_id, active=True)
            .count()
        )

        session.close()

        return {
            "total_incoming_webhooks": incoming_count,
            "total_outgoing_webhooks": outgoing_count,
            "active_incoming_webhooks": active_incoming,
            "active_outgoing_webhooks": active_outgoing,
            "total_webhooks": incoming_count + outgoing_count,
            "active_webhooks": active_incoming + active_outgoing,
        }

    except Exception as e:
        logger.error(f"Error getting global webhook stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/webhooks/logs",
    response_model=List[WebhookLogResponse],
    tags=["Webhooks"],
    summary="Get recent webhook logs",
)
async def get_recent_webhook_logs(
    user_data: dict = Depends(verify_api_key),
    limit: int = Query(10, description="Maximum number of logs to return"),
    offset: int = Query(0, description="Number of logs to skip"),
):
    """
    Get recent webhook logs for all user webhooks
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Get all webhook IDs for the user
        incoming_webhooks = (
            session.query(WebhookIncoming).filter_by(user_id=user_id).all()
        )
        outgoing_webhooks = (
            session.query(WebhookOutgoing).filter_by(user_id=user_id).all()
        )

        webhook_ids = []
        for webhook in incoming_webhooks:
            webhook_ids.append((webhook.id, "incoming"))
        for webhook in outgoing_webhooks:
            webhook_ids.append((str(webhook.id), "outgoing"))

        # Get recent logs for all webhooks
        logs = []
        for webhook_id, webhook_type in webhook_ids:
            webhook_logs = (
                session.query(WebhookLog)
                .filter_by(webhook_id=webhook_id, direction=webhook_type)
                .order_by(desc(WebhookLog.timestamp))
                .limit(limit)
                .all()
            )
            logs.extend(webhook_logs)

        # Sort by timestamp and limit
        logs = sorted(logs, key=lambda x: x.timestamp, reverse=True)[:limit]

        result = []
        for log in logs:
            result.append(
                WebhookLogResponse(
                    id=str(log.id),
                    direction=log.direction,
                    webhook_id=str(log.webhook_id),
                    payload=log.payload,
                    response=log.response,
                    status_code=log.status_code,
                    error_message=log.error_message,
                    retry_count=log.retry_count,
                    timestamp=log.timestamp,
                )
            )

        session.close()
        return result

    except Exception as e:
        logger.error(f"Error getting recent webhook logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/webhooks/test/{webhook_id}",
    response_model=Detail,
    tags=["Webhooks"],
    summary="Test a webhook",
)
async def test_webhook(
    webhook_id: str,
    test_payload: WebhookTestPayload,
    user_data: dict = Depends(verify_api_key),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Send a test payload to an outgoing webhook
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Find webhook
        webhook = (
            session.query(WebhookOutgoing)
            .filter_by(id=webhook_id, user_id=user_id)
            .first()
        )

        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        session.close()

        # Create test event
        async def send_test_event():
            await event_emitter.emit_event(
                event_type=test_payload.event_type,
                user_id=user_id,
                data=test_payload.test_payload,
                metadata={"webhook_id": webhook_id, "test": True},
            )

        # Queue the test
        background_tasks.add_task(send_test_event)

        return Detail(detail="Test webhook sent successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/webhooks/{webhook_id}/statistics",
    response_model=WebhookStatistics,
    tags=["Webhooks"],
    summary="Get webhook statistics",
)
async def get_webhook_statistics(
    webhook_id: str,
    webhook_type: str = Query(
        "incoming", description="Type of webhook (incoming or outgoing)"
    ),
    user_data: dict = Depends(verify_api_key),
):
    """
    Get statistics for a specific webhook
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        stats = webhook_manager.get_webhook_statistics(webhook_id, webhook_type)

        if not stats:
            raise HTTPException(status_code=404, detail="Webhook not found")

        # Calculate average processing time from logs
        session = get_session()

        if webhook_type == "incoming":
            webhook = (
                session.query(WebhookIncoming)
                .filter_by(webhook_id=webhook_id, user_id=user_id)
                .first()
            )

            if not webhook:
                raise HTTPException(
                    status_code=404, detail="Webhook not found or access denied"
                )

            logs = (
                session.query(WebhookLog)
                .filter_by(webhook_id=webhook.id, direction="incoming")
                .all()
            )
        else:
            webhook = (
                session.query(WebhookOutgoing)
                .filter_by(id=webhook_id, user_id=user_id)
                .first()
            )

            if not webhook:
                raise HTTPException(
                    status_code=404, detail="Webhook not found or access denied"
                )

            logs = (
                session.query(WebhookLog)
                .filter_by(webhook_id=webhook_id, direction="outgoing")
                .all()
            )

        # Calculate average processing time (not available in current model)
        avg_time = 0.0

        # Get last request and error info
        last_log = (
            session.query(WebhookLog)
            .filter_by(
                webhook_id=webhook.id if webhook_type == "incoming" else webhook_id,
                direction=webhook_type,
            )
            .order_by(desc(WebhookLog.timestamp))
            .first()
        )

        last_error = (
            session.query(WebhookLog)
            .filter(
                and_(
                    WebhookLog.webhook_id
                    == (webhook.id if webhook_type == "incoming" else webhook_id),
                    WebhookLog.direction == webhook_type,
                    WebhookLog.error_message.isnot(None),
                )
            )
            .order_by(desc(WebhookLog.timestamp))
            .first()
        )

        session.close()

        # Since the webhook models don't have statistics fields,
        # we need to calculate them from the logs
        log_query = session.query(WebhookLog).filter(
            WebhookLog.webhook_id == webhook_id
            if webhook_type == "incoming"
            else WebhookLog.webhook_id == webhook_id
        )

        total_requests = log_query.count()
        successful_requests = log_query.filter(WebhookLog.status_code == 200).count()
        failed_requests = total_requests - successful_requests

        return WebhookStatistics(
            webhook_id=webhook_id,
            webhook_type=webhook_type,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_processing_time_ms=avg_time,
            last_request_at=last_log.timestamp if last_log else None,
            last_error_at=last_error.timestamp if last_error else None,
            last_error_message=last_error.error_message if last_error else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting webhook statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/webhooks/{webhook_id}/logs",
    response_model=List[WebhookLogResponse],
    tags=["Webhooks"],
    summary="Get webhook logs",
)
async def get_webhook_logs(
    webhook_id: str,
    webhook_type: str = Query(
        "incoming", description="Type of webhook (incoming or outgoing)"
    ),
    limit: int = Query(100, description="Maximum number of logs to return"),
    offset: int = Query(0, description="Number of logs to skip"),
    user_data: dict = Depends(verify_api_key),
):
    """
    Get logs for a specific webhook
    """
    try:
        # Extract user ID from the user data dictionary
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user data")

        session = get_session()

        # Verify webhook ownership
        if webhook_type == "incoming":
            webhook = (
                session.query(WebhookIncoming)
                .filter_by(webhook_id=webhook_id, user_id=user_id)
                .first()
            )

            if not webhook:
                raise HTTPException(
                    status_code=404, detail="Webhook not found or access denied"
                )

            logs = (
                session.query(WebhookLog)
                .filter_by(webhook_id=webhook.id, direction="incoming")
                .order_by(desc(WebhookLog.timestamp))
                .limit(limit)
                .offset(offset)
                .all()
            )
        else:
            webhook = (
                session.query(WebhookOutgoing)
                .filter_by(id=webhook_id, user_id=user_id)
                .first()
            )

            if not webhook:
                raise HTTPException(
                    status_code=404, detail="Webhook not found or access denied"
                )

            logs = (
                session.query(WebhookLog)
                .filter_by(webhook_id=webhook_id, direction="outgoing")
                .order_by(desc(WebhookLog.timestamp))
                .limit(limit)
                .offset(offset)
                .all()
            )

        result = []
        for log in logs:
            result.append(
                WebhookLogResponse(
                    id=str(log.id),
                    direction=log.direction,
                    webhook_id=str(log.webhook_id),
                    payload=log.payload,
                    response=log.response,
                    status_code=log.status_code,
                    error_message=log.error_message,
                    retry_count=log.retry_count,
                    timestamp=log.timestamp,
                )
            )

        session.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting webhook logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
