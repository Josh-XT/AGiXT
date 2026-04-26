from fastapi import (
    APIRouter,
    Depends,
    Header,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Form,
    HTTPException,
)
from fastapi.responses import StreamingResponse, JSONResponse, Response
import hashlib
from pydantic import BaseModel
from typing import Dict, List, Optional
from ApiClient import verify_api_key, get_api_client, Agent
from Conversations import (
    Conversations,
    get_conversation_name_by_id,
    get_conversation_id_by_name,
    get_conversation_name_by_message_id,
)
from DB import Message, MessageReaction, Agent as DBAgent, User
from XT import AGiXT
from middleware import log_silenced_exception
from Models import (
    HistoryModel,
    ConversationHistoryModel,
    ConversationHistoryMessageModel,
    UpdateConversationHistoryMessageModel,
    ResponseMessage,
    LogInteraction,
    RenameConversationModel,
    UpdateMessageModel,
    DeleteMessageModel,
    ConversationFork,
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationHistoryResponse,
    NewConversationHistoryResponse,
    NotificationResponse,
    MessageIdResponse,
    WorkspaceListResponse,
    WorkspaceFolderCreateModel,
    WorkspaceDeleteModel,
    WorkspaceMoveModel,
    ConversationShareCreate,
    ConversationShareResponse,
    SharedConversationListResponse,
    SharedConversationResponse,
    CreateGroupConversationModel,
    AddParticipantModel,
    UpdateParticipantRoleModel,
    UpdateChannelModel,
    UpdateNotificationSettingsModel,
    NotificationSettingsResponse,
    GroupConversationListResponse,
    ThreadListResponse,
    AddReactionModel,
    MessageReactionsResponse,
)
import json
import uuid
import asyncio
import logging
import os
import io
import zipfile
import threading
import tempfile
from datetime import datetime, timezone
from MagicalAuth import MagicalAuth, get_user_id
from WorkerRegistry import worker_registry
from Workspaces import WorkspaceManager
from Interactions import generate_conversation_summary
import mimetypes
from typing import Set

app = APIRouter()
workspace_manager = WorkspaceManager()

# In-memory tracking for async import tasks
_import_tasks: Dict[str, dict] = {}
_import_tasks_lock = threading.Lock()

# In-memory tracking for chunked uploads
_chunked_uploads: Dict[str, dict] = {}
_chunked_uploads_lock = threading.Lock()
CHUNK_MAX_SIZE = 50 * 1024 * 1024  # 50MB per chunk
CHUNK_UPLOAD_DIR = os.path.join(
    os.environ.get("AGIXT_HUB", os.path.expanduser("~/.agixt")), "tmp_uploads"
)


# Redis pub/sub channel for cross-worker WebSocket broadcasts
REDIS_BROADCAST_CHANNEL = "agixt:ws:broadcast"
REDIS_USER_NOTIFY_CHANNEL = "agixt:ws:user_notify"


def _get_redis_client():
    """Get a Redis client for pub/sub operations."""
    redis_host = os.environ.get("REDIS_HOST", "")
    if not redis_host:
        return None

    try:
        import redis

        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        redis_password = os.environ.get("REDIS_PASSWORD", "")
        redis_db = int(os.environ.get("REDIS_DB", "0"))

        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password if redis_password else None,
            db=redis_db,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logging.debug(f"Redis client creation failed: {e}")
        return None


class ConversationMessageBroadcaster:
    """
    Manages WebSocket connections for real-time conversation message updates.
    Allows broadcasting message events directly to websocket listeners without polling.
    """

    def __init__(self):
        # Maps conversation_id -> set of active WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Per-connection tracking of message IDs already sent (by broadcast or poll loop)
        # Maps websocket id(ws) -> set of message IDs
        self._connection_sent_ids: Dict[int, Set[str]] = {}
        self._lock = asyncio.Lock()
        # Store reference to main event loop for cross-thread broadcasting
        self._main_loop = None
        # Redis pub/sub for cross-worker broadcasting
        self._redis_publisher = None
        self._redis_subscriber = None
        self._subscriber_thread = None
        self._subscriber_running = False

    def set_main_loop(self, loop):
        """Set the main event loop reference for cross-thread broadcasts."""
        self._main_loop = loop
        # Start Redis subscriber when main loop is set
        self._start_redis_subscriber()

    def _start_redis_subscriber(self):
        """Start the Redis pub/sub subscriber in a background thread."""
        if self._subscriber_running:
            return

        self._redis_publisher = _get_redis_client()
        if self._redis_publisher is None:
            logging.info(
                "ConversationMessageBroadcaster: Redis not available, cross-worker broadcasts disabled"
            )
            return

        # Create a separate client for subscribing (pub/sub requires dedicated connection)
        self._redis_subscriber = _get_redis_client()
        if self._redis_subscriber is None:
            return

        self._subscriber_running = True
        self._subscriber_thread = threading.Thread(
            target=self._redis_subscriber_loop, daemon=True, name="redis-ws-subscriber"
        )
        self._subscriber_thread.start()

    def _redis_subscriber_loop(self):
        """Background thread that listens for Redis pub/sub messages."""
        try:
            pubsub = self._redis_subscriber.pubsub()
            pubsub.subscribe(REDIS_BROADCAST_CHANNEL)

            for message in pubsub.listen():
                if not self._subscriber_running:
                    break

                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    conversation_id = data.get("conversation_id")
                    event_type = data.get("event_type")
                    message_data = data.get("message_data")

                    if conversation_id and event_type and message_data:
                        # Schedule the local broadcast on the main event loop
                        if self._main_loop is not None:
                            asyncio.run_coroutine_threadsafe(
                                self._local_broadcast(
                                    conversation_id, event_type, message_data
                                ),
                                self._main_loop,
                            )
                except json.JSONDecodeError:
                    logging.debug(
                        "ConversationMessageBroadcaster: Invalid JSON in Redis message"
                    )
                except Exception as e:
                    logging.debug(
                        f"ConversationMessageBroadcaster: Error processing Redis message: {e}"
                    )
        except Exception as e:
            logging.warning(
                f"ConversationMessageBroadcaster: Redis subscriber error: {e}"
            )
        finally:
            self._subscriber_running = False

    def get_main_loop(self):
        """Get the main event loop for scheduling broadcasts from other threads."""
        return self._main_loop

    async def connect(self, websocket: WebSocket, conversation_id: str):
        """Register a WebSocket connection for a conversation."""
        # Capture main event loop on first connection if not set
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
            self._start_redis_subscriber()
        async with self._lock:
            if conversation_id not in self.active_connections:
                self.active_connections[conversation_id] = set()
            self.active_connections[conversation_id].add(websocket)
            # Initialize per-connection sent-message tracking
            self._connection_sent_ids[id(websocket)] = set()
            logging.debug(
                f"Conversation {conversation_id}: WebSocket connected. Total: {len(self.active_connections[conversation_id])}"
            )

    async def disconnect(self, websocket: WebSocket, conversation_id: str):
        """Remove a WebSocket connection for a conversation."""
        async with self._lock:
            if conversation_id in self.active_connections:
                self.active_connections[conversation_id].discard(websocket)
                if not self.active_connections[conversation_id]:
                    del self.active_connections[conversation_id]
                logging.debug(
                    f"Conversation {conversation_id}: WebSocket disconnected."
                )
            # Clean up per-connection sent-message tracking
            self._connection_sent_ids.pop(id(websocket), None)

    def publish_to_redis(
        self, conversation_id: str, event_type: str, message_data: dict
    ):
        """
        Publish a broadcast message to Redis for cross-worker distribution.
        This should be called from any thread - it uses the Redis client synchronously.
        """
        if self._redis_publisher is None:
            return False

        try:
            payload = json.dumps(
                {
                    "conversation_id": conversation_id,
                    "event_type": event_type,
                    "message_data": make_json_serializable(message_data),
                }
            )
            self._redis_publisher.publish(REDIS_BROADCAST_CHANNEL, payload)
            logging.debug(
                f"Published broadcast to Redis: conv={conversation_id}, type={event_type}"
            )
            return True
        except Exception as e:
            logging.warning(f"Failed to publish to Redis: {e}")
            return False

    async def _local_broadcast(
        self, conversation_id: str, event_type: str, message_data: dict
    ):
        """
        Broadcast to local WebSocket connections only (called from Redis subscriber).
        """
        connections_to_remove = []
        async with self._lock:
            if conversation_id not in self.active_connections:
                return 0
            connections = list(self.active_connections[conversation_id])
            message_id = message_data.get("id")

        sent_count = 0
        for connection in connections:
            try:
                # Skip if this message was already sent to this connection
                if message_id:
                    ws_id = id(connection)
                    if (
                        ws_id in self._connection_sent_ids
                        and str(message_id) in self._connection_sent_ids[ws_id]
                    ):
                        continue
                await connection.send_text(
                    json.dumps(
                        {
                            "type": event_type,
                            "data": message_data,  # Already serialized from Redis
                        }
                    )
                )
                sent_count += 1
                # Track that this message was sent to this connection
                if message_id:
                    ws_id = id(connection)
                    if ws_id in self._connection_sent_ids:
                        self._connection_sent_ids[ws_id].add(str(message_id))
            except Exception as e:
                logging.debug(f"Failed to send to WebSocket: {e}")
                connections_to_remove.append(connection)

        if connections_to_remove:
            async with self._lock:
                for conn in connections_to_remove:
                    if conversation_id in self.active_connections:
                        self.active_connections[conversation_id].discard(conn)

        if sent_count > 0:
            logging.debug(
                f"Local broadcast sent to {sent_count} connections for {conversation_id}"
            )
        return sent_count

    async def broadcast_message_event(
        self, conversation_id: str, event_type: str, message_data: dict
    ):
        """
        Broadcast a message event to all WebSocket connections for a conversation.
        Uses Redis pub/sub for cross-worker distribution if available.

        Args:
            conversation_id: The conversation ID to broadcast to
            event_type: Either 'message_added' or 'message_updated'
            message_data: The message data to send

        Returns:
            Number of WebSocket connections that received the broadcast (local only)
        """
        logging.debug(
            f"broadcast_message_event called: conv={conversation_id}, type={event_type}"
        )

        # Mark conversation updated in SharedCache so poll loops can skip DB queries
        from Conversations import mark_conversation_updated

        mark_conversation_updated(conversation_id)

        # Try to publish to Redis for cross-worker distribution
        if self.publish_to_redis(conversation_id, event_type, message_data):
            # Redis will handle distribution to all workers including this one
            return 0

        # Fallback to local-only broadcast if Redis not available
        connections_to_remove = []
        async with self._lock:
            if conversation_id not in self.active_connections:
                logging.debug(
                    f"broadcast_message_event: no active connections for {conversation_id}"
                )
                return 0
            connections = list(self.active_connections[conversation_id])
            message_id = message_data.get("id")
            logging.debug(
                f"broadcast_message_event: found {len(connections)} connections"
            )

        sent_count = 0
        for connection in connections:
            try:
                # Skip if this message was already sent to this connection (by poll loop or prior broadcast)
                if message_id:
                    ws_id = id(connection)
                    if (
                        ws_id in self._connection_sent_ids
                        and str(message_id) in self._connection_sent_ids[ws_id]
                    ):
                        logging.debug(
                            f"broadcast_message_event: skipping already-sent message {message_id}"
                        )
                        continue
                await connection.send_text(
                    json.dumps(
                        {
                            "type": event_type,
                            "data": make_json_serializable(message_data),
                        }
                    )
                )
                sent_count += 1
                # Track that this message was sent to this connection
                if message_id:
                    ws_id = id(connection)
                    if ws_id in self._connection_sent_ids:
                        self._connection_sent_ids[ws_id].add(str(message_id))
                logging.debug(
                    f"broadcast_message_event: sent to connection {sent_count}/{len(connections)}"
                )
            except Exception as e:
                logging.warning(
                    f"Failed to broadcast to conversation {conversation_id}: {e}"
                )
                connections_to_remove.append(connection)

        # Clean up dead connections
        if connections_to_remove:
            async with self._lock:
                for conn in connections_to_remove:
                    if conversation_id in self.active_connections:
                        self.active_connections[conversation_id].discard(conn)

        return sent_count

    def was_sent_to_connection(self, websocket: WebSocket, message_id: str) -> bool:
        """Check if a message was already sent to this specific connection (by broadcast or poll)."""
        ws_id = id(websocket)
        if ws_id not in self._connection_sent_ids:
            return False
        return str(message_id) in self._connection_sent_ids[ws_id]

    def mark_sent_to_connection(self, websocket: WebSocket, message_id: str):
        """Record that a message was sent to this connection (called by poll loop after sending)."""
        ws_id = id(websocket)
        if ws_id in self._connection_sent_ids:
            self._connection_sent_ids[ws_id].add(str(message_id))

    def has_listeners(self, conversation_id: str) -> bool:
        """Check if a conversation has active WebSocket listeners."""
        return (
            conversation_id in self.active_connections
            and len(self.active_connections[conversation_id]) > 0
        )

    async def broadcast_typing_event(
        self,
        conversation_id: str,
        typing_data: dict,
        exclude_websocket: WebSocket = None,
    ):
        """
        Broadcast a typing indicator to all WebSocket connections for a conversation,
        excluding the sender's connection.
        """
        connections_to_remove = []
        async with self._lock:
            if conversation_id not in self.active_connections:
                return 0
            connections = list(self.active_connections[conversation_id])

        sent_count = 0
        for connection in connections:
            if connection is exclude_websocket:
                continue
            try:
                await connection.send_text(
                    json.dumps(
                        {
                            "type": "typing_indicator",
                            "data": typing_data,
                        }
                    )
                )
                sent_count += 1
            except Exception as e:
                logging.debug(f"Failed to send typing indicator: {e}")
                connections_to_remove.append(connection)

        if connections_to_remove:
            async with self._lock:
                for conn in connections_to_remove:
                    if conversation_id in self.active_connections:
                        self.active_connections[conversation_id].discard(conn)

        return sent_count


# Global conversation message broadcaster instance
conversation_message_broadcaster = ConversationMessageBroadcaster()


class UserNotificationManager:
    """
    Manages WebSocket connections for user-level notifications.
    Allows broadcasting events to all connections for a specific user.
    Uses Redis pub/sub for cross-worker distribution when multiple uvicorn
    workers are running, so a notification published from any worker reaches
    the WebSocket connection regardless of which worker holds it.
    """

    def __init__(self):
        # Maps user_id -> set of active WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        # Redis pub/sub for cross-worker broadcasting
        self._redis_publisher = None
        self._redis_subscriber = None
        self._subscriber_thread = None
        self._subscriber_running = False
        self._main_loop = None

    def set_main_loop(self, loop):
        """Set the main event loop reference for cross-thread broadcasts."""
        self._main_loop = loop
        self._start_redis_subscriber()

    def _start_redis_subscriber(self):
        """Start the Redis pub/sub subscriber in a background thread."""
        if self._subscriber_running:
            return

        self._redis_publisher = _get_redis_client()
        if self._redis_publisher is None:
            logging.info(
                "UserNotificationManager: Redis not available, cross-worker notifications disabled"
            )
            return

        self._redis_subscriber = _get_redis_client()
        if self._redis_subscriber is None:
            return

        self._subscriber_running = True
        self._subscriber_thread = threading.Thread(
            target=self._redis_subscriber_loop,
            daemon=True,
            name="redis-user-notify-subscriber",
        )
        self._subscriber_thread.start()
        logging.info("UserNotificationManager: Redis subscriber started")

    def _redis_subscriber_loop(self):
        """Background thread that listens for Redis pub/sub messages."""
        try:
            pubsub = self._redis_subscriber.pubsub()
            pubsub.subscribe(REDIS_USER_NOTIFY_CHANNEL)

            for message in pubsub.listen():
                if not self._subscriber_running:
                    break
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    user_id = data.get("user_id")
                    notification = data.get("notification")
                    if user_id and notification:
                        if self._main_loop is not None:
                            asyncio.run_coroutine_threadsafe(
                                self._local_broadcast_to_user(user_id, notification),
                                self._main_loop,
                            )
                except json.JSONDecodeError:
                    logging.debug(
                        "UserNotificationManager: Invalid JSON in Redis message"
                    )
                except Exception as e:
                    logging.debug(
                        f"UserNotificationManager: Error processing Redis message: {e}"
                    )
        except Exception as e:
            logging.warning(f"UserNotificationManager: Redis subscriber error: {e}")
        finally:
            self._subscriber_running = False

    async def connect(self, websocket: WebSocket, user_id: str):
        """Register a new WebSocket connection for a user."""
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
            self._start_redis_subscriber()
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)
            logging.debug(
                f"User {user_id} connected. Total connections: {len(self.active_connections[user_id])}"
            )

    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection for a user."""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                logging.debug(f"User {user_id} disconnected.")

    async def broadcast_to_user(self, user_id: str, message: dict):
        """Broadcast a message to all connections for a specific user.
        Uses Redis pub/sub so every worker can deliver to its local connections."""
        if self._publish_to_redis(user_id, message):
            return  # Redis will distribute to all workers including this one

        # Fallback: local-only broadcast when Redis is unavailable
        await self._local_broadcast_to_user(user_id, message)

    def _publish_to_redis(self, user_id: str, message: dict) -> bool:
        """Publish a user notification to Redis for cross-worker distribution."""
        # Lazily initialize Redis publisher on first broadcast attempt
        if self._redis_publisher is None:
            self._redis_publisher = _get_redis_client()
        if self._redis_publisher is None:
            return False
        try:
            payload = json.dumps(
                {
                    "user_id": user_id,
                    "notification": make_json_serializable(message),
                }
            )
            self._redis_publisher.publish(REDIS_USER_NOTIFY_CHANNEL, payload)
            return True
        except Exception as e:
            logging.warning(f"UserNotificationManager: Failed to publish to Redis: {e}")
            return False

    async def _local_broadcast_to_user(self, user_id: str, message: dict):
        """Broadcast to local WebSocket connections only (called from Redis subscriber or fallback)."""
        connections_to_remove = []
        async with self._lock:
            if user_id not in self.active_connections:
                return
            connections = list(self.active_connections[user_id])

        for connection in connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logging.warning(f"Failed to send to user {user_id}: {e}")
                connections_to_remove.append(connection)

        # Clean up dead connections
        if connections_to_remove:
            async with self._lock:
                for conn in connections_to_remove:
                    if user_id in self.active_connections:
                        self.active_connections[user_id].discard(conn)

    def get_user_connection_count(self, user_id: str) -> int:
        """Get the number of active connections for a user."""
        return len(self.active_connections.get(user_id, set()))

    async def broadcast_to_all_users(self, message: dict) -> int:
        """
        Broadcast a message to ALL connected users.
        Used for system-wide notifications like maintenance announcements.
        Returns the number of users notified.
        """
        users_notified = 0
        async with self._lock:
            user_ids = list(self.active_connections.keys())

        for user_id in user_ids:
            await self.broadcast_to_user(user_id, message)
            users_notified += 1

        return users_notified

    def get_all_connected_user_ids(self) -> list:
        """Get list of all currently connected user IDs."""
        return list(self.active_connections.keys())


# Global notification manager instance
user_notification_manager = UserNotificationManager()


def make_json_serializable(obj):
    """Convert datetime objects, UUIDs, and other non-serializable objects to JSON-serializable formats"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    else:
        return obj


def _resolve_conversation_workspace(
    conversation_identifier: str,
    user: str,
    authorization: Optional[str],
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    auth = MagicalAuth(token=authorization)
    if conversation_identifier == "-":
        conversation_identifier = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )

    try:
        conversation_uuid = uuid.UUID(conversation_identifier)
        conversation_id = str(conversation_uuid)
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
        if conversation_name is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    except ValueError:
        conversation_name = conversation_identifier
        conversation_id = get_conversation_id_by_name(
            conversation_name=conversation_name, user_id=auth.user_id
        )
        if conversation_id is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    agent_id = conversation.get_agent_id(auth.user_id)
    if not agent_id:
        raise HTTPException(
            status_code=400,
            detail="Unable to resolve agent for conversation workspace",
        )

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "agent_id": agent_id,
        "auth": auth,
        "conversation": conversation,
    }


@app.get(
    "/api/conversations",
    response_model=ConversationListResponse,
    summary="Get List of Conversations",
    description="Retrieves a list of all conversations for the authenticated user, including both conversation names and their IDs.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    conversations_with_ids = c.get_conversations_with_ids()
    conversations = (
        list(conversations_with_ids.values()) if conversations_with_ids else []
    )
    return {
        "conversations": conversations,
        "conversations_with_ids": conversations_with_ids,
    }


@app.get(
    "/v1/conversations",
    response_model=ConversationDetailResponse,
    summary="Get Detailed Conversations List",
    description="Retrieves a detailed list of conversations including metadata such as creation date, update date, and notification status. Supports optional limit/offset for pagination.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations(
    user=Depends(verify_api_key),
    limit: int = None,
    offset: int = 0,
    if_none_match: str = Header(None, alias="If-None-Match"),
):
    c = Conversations(user=user)
    # Cap the server-side response. Without a cap, this endpoint can return
    # 2+ MB for power users, computing unread counts, DM names, and agent
    # roles for every conversation. 500 is well above any UI pagination
    # default and keeps responses bounded.
    MAX_CONVERSATIONS = 500
    if limit is None or limit <= 0 or limit > MAX_CONVERSATIONS:
        limit = MAX_CONVERSATIONS
    # Pass limit/offset to the core method so expensive batch queries
    # (unread counts, DM names, agent roles) are only computed for the
    # paginated subset instead of all conversations.
    conversations = c.get_conversations_with_detail(limit=limit, offset=offset)
    if not conversations:
        conversations = {}
    # Conversations contain datetime values that JSONResponse can't serialize
    # directly; use jsonable_encoder to normalize before hashing/sending.
    from fastapi.encoders import jsonable_encoder

    encoded = jsonable_encoder({"conversations": conversations})

    # ETag based on response content. Lets the SSR layout fetch return 304
    # Not Modified on warm navigation, avoiding the 100-400ms recompute of
    # unread counts / DM names for every page hop.
    etag_string = json.dumps(encoded, sort_keys=True)
    etag = f'"{hashlib.sha256(etag_string.encode()).hexdigest()}"'
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(
        content=encoded,
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=5, stale-while-revalidate=15",
        },
    )


class SearchMessagesRequest(BaseModel):
    query: str
    conversation_types: Optional[List[str]] = None
    company_id: Optional[str] = None
    limit: Optional[int] = 50


@app.post(
    "/v1/conversations/search",
    summary="Search Messages",
    description="Search message content across all conversations the user has access to, with optional filters for conversation type and company.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def search_messages(
    body: SearchMessagesRequest,
    user=Depends(verify_api_key),
):
    c = Conversations(user=user)
    results = c.search_messages(
        query=body.query,
        conversation_types=body.conversation_types,
        company_id=body.company_id,
        limit=body.limit or 50,
    )
    return {"results": results}


@app.get(
    "/v1/conversation/{conversation_id}",
    response_model=ConversationHistoryResponse,
    summary="Get Conversation History by ID",
    description="Retrieves the complete history of a specific conversation using its ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
    limit: int = 100,
    page: int = 1,
):
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    # Skip redundant get_conversation_name_by_id() — get_conversation() already
    # resolves the conversation via conversation_id with its own fallback logic.
    conversation_history = Conversations(
        conversation_name="-",
        user=user,
        conversation_id=conversation_id,
    ).get_conversation(limit=limit, page=page)
    if conversation_history is None:
        conversation_history = {
            "interactions": [],
            "total": 0,
            "page": page,
            "limit": limit,
        }
    total = conversation_history.get("total")
    resp_page = conversation_history.get("page")
    resp_limit = conversation_history.get("limit")
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {
        "conversation_history": conversation_history,
        "total": total,
        "page": resp_page,
        "limit": resp_limit,
    }


@app.post(
    "/v1/conversation",
    response_model=NewConversationHistoryResponse,
    summary="Create New Conversation",
    description="Creates a new conversation with initial content. Requires agent_id.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def new_conversation_v1(
    history: ConversationHistoryModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    c = Conversations(conversation_name=history.conversation_name, user=user)
    c.new_conversation(conversation_content=history.conversation_content)
    conversation_id = c.get_conversation_id()

    # Notify user of new conversation via websocket
    _agent_id = c.get_agent_id(auth.user_id)
    asyncio.create_task(
        notify_user_conversation_created(
            user_id=auth.user_id,
            conversation_id=conversation_id,
            conversation_name=history.conversation_name,
            agent_id=str(_agent_id) if _agent_id else None,
        )
    )

    return {
        "id": conversation_id,
        "conversation_history": history.conversation_content,
    }


@app.delete(
    "/v1/conversation/{conversation_id}",
    response_model=ResponseMessage,
    summary="Delete Conversation by ID",
    description="Deletes an entire conversation and all its messages using conversation ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_v1(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    original_id = conversation_id
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    ).delete_conversation()

    # Notify user of deleted conversation via websocket
    asyncio.create_task(
        notify_user_conversation_deleted(
            user_id=auth.user_id,
            conversation_id=conversation_id,
            conversation_name=conversation_name,
        )
    )

    return ResponseMessage(message=f"Conversation `{conversation_name}` deleted.")


@app.put(
    "/v1/conversation/{conversation_id}",
    response_model=ResponseMessage,
    summary="Rename Conversation by ID",
    description="Renames a conversation using conversation ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def rename_conversation_v1(
    conversation_id: str,
    rename_model: RenameConversationModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    old_conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not old_conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    Conversations(
        conversation_name=old_conversation_name,
        user=user,
        conversation_id=conversation_id,
    ).rename_conversation(new_name=rename_model.new_conversation_name)

    # Notify user of renamed conversation via websocket
    asyncio.create_task(
        notify_user_conversation_renamed(
            user_id=auth.user_id,
            conversation_id=conversation_id,
            old_name=old_conversation_name,
            new_name=rename_model.new_conversation_name,
        )
    )

    return ResponseMessage(
        message=f"Conversation renamed to `{rename_model.new_conversation_name}`."
    )


class PinOrderUpdate(BaseModel):
    pin_order: Optional[int] = None


@app.patch(
    "/v1/conversation/{conversation_id}/pin",
    response_model=ResponseMessage,
    summary="Update Conversation Pin Order",
    description="Updates the pin order for a conversation. Set pin_order to null to unpin, or an integer to set pin position.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_pin_order(
    conversation_id: str,
    body: PinOrderUpdate,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    success = Conversations(conversation_name="-", user=user).update_pin_order(
        conversation_id=conversation_id, pin_order=body.pin_order
    )
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    action = "pinned" if body.pin_order is not None else "unpinned"
    return ResponseMessage(message=f"Conversation {action} successfully.")


@app.post(
    "/v1/conversation/{conversation_id}/message",
    response_model=MessageIdResponse,
    summary="Add Message to Conversation",
    description="Adds a new message to an existing conversation using conversation ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def add_message_v1(
    conversation_id: str,
    log_interaction: LogInteraction,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Create single Conversations instance for reuse across operations
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    # Check speaking permissions for USER messages in group channels
    if log_interaction.role.upper() == "USER":
        if not c.can_speak(str(auth.user_id)):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to speak in this channel",
            )

    # Extract base64 data URLs to workspace files before storing/broadcasting
    # This prevents massive base64 strings from bloating the DB, DOM, and WebSocket payloads
    stored_message = log_interaction.message
    if "data:" in stored_message and "base64," in stored_message:
        try:
            from Conversations import extract_data_urls_to_workspace

            agent_id = c.get_agent_id(str(auth.user_id)) or "default"
            stored_message = extract_data_urls_to_workspace(
                stored_message, agent_id, conversation_id
            )
        except Exception as e:
            logging.warning(f"Failed to extract data URLs from channel message: {e}")

    interaction_id = c.log_interaction(
        message=stored_message,
        role=log_interaction.role,
        sender_user_id=(
            str(auth.user_id) if log_interaction.role.upper() == "USER" else None
        ),
    )

    # Build sender object for broadcast (so other users see correct avatar/name)
    # verify_api_key returns a string (email), not a dict, so we must look up
    # the user's full profile from the DB to populate name/avatar fields.
    sender_data = None
    if log_interaction.role.upper() == "USER":
        try:
            from DB import get_session, User

            with get_session() as sender_session:
                sender_user = (
                    sender_session.query(User).filter(User.id == auth.user_id).first()
                )
                if sender_user:
                    sender_data = {
                        "id": str(auth.user_id),
                        "email": sender_user.email or "",
                        "first_name": sender_user.first_name or "",
                        "last_name": sender_user.last_name or "",
                        "avatar_url": getattr(sender_user, "avatar_url", None),
                    }
                else:
                    # Fallback: use what we have from auth
                    sender_data = {
                        "id": str(auth.user_id),
                        "email": auth.email or "",
                        "first_name": "",
                        "last_name": "",
                        "avatar_url": None,
                    }
        except Exception as e:
            logging.warning(f"Failed to build sender data for broadcast: {e}")

    # Notify all conversation participants of the new message via user-level websocket
    asyncio.create_task(
        notify_conversation_participants_message_added(
            sender_user_id=str(auth.user_id),
            conversation_id=conversation_id,
            conversation_name=conversation_name,
            message_id=str(interaction_id),
            message=stored_message,
            role=log_interaction.role,
        )
    )

    # Broadcast to conversation-level WebSocket so other users see the message
    asyncio.create_task(
        conversation_message_broadcaster.broadcast_message_event(
            conversation_id=conversation_id,
            event_type="message_added",
            message_data={
                "id": str(interaction_id),
                "role": log_interaction.role,
                "message": stored_message,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat(),
                "sender_user_id": (
                    str(auth.user_id)
                    if log_interaction.role.upper() == "USER"
                    else None
                ),
                "sender": sender_data,
            },
        )
    )

    # If message contains audio file references, schedule background transcription
    # Find audio links using imperative O(n) parsing instead of regex to avoid
    # polynomial backtracking (CodeQL: polynomial regular expression).
    _audio_extensions = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".aac", ".flac"}
    audio_matches = []
    _pos = 0
    _msg_len = len(stored_message)
    while _pos < _msg_len:
        _bracket_start = stored_message.find("[", _pos)
        if _bracket_start == -1:
            break
        _bracket_end = stored_message.find("]", _bracket_start + 1)
        if _bracket_end == -1:
            break
        if _bracket_end + 1 < _msg_len and stored_message[_bracket_end + 1] == "(":
            _paren_end = stored_message.find(")", _bracket_end + 2)
            if _paren_end != -1:
                _alt = stored_message[_bracket_start + 1 : _bracket_end]
                _url = stored_message[_bracket_end + 2 : _paren_end]
                if _url.startswith(("http://", "https://", "/outputs/")) and any(
                    _url.lower().endswith(ext) for ext in _audio_extensions
                ):
                    audio_matches.append((_alt, _url))
                _pos = _paren_end + 1
                continue
        _pos = _bracket_end + 1
    if audio_matches:
        asyncio.create_task(
            _transcribe_channel_audio(
                conversation_id=conversation_id,
                conversation_name=conversation_name,
                message_id=str(interaction_id),
                stored_message=stored_message,
                audio_matches=audio_matches,
                user=user,
                user_id=str(auth.user_id),
            )
        )

    return ResponseMessage(message=str(interaction_id))


async def _transcribe_channel_audio(
    conversation_id: str,
    conversation_name: str,
    message_id: str,
    stored_message: str,
    audio_matches: list,
    user: str,
    user_id: str,
):
    """
    Background task to transcribe audio files in channel messages.
    Updates the message with transcription text after processing.
    """
    try:
        from Globals import getenv

        agixt_uri = getenv("AGIXT_URI")
        working_directory = getenv("WORKING_DIRECTORY")
        original_message = stored_message

        for alt_text, audio_url in audio_matches:
            try:
                # Convert the URL to a local file path
                # URL format: {AGIXT_URI}/outputs/agent_{hash}/{conversation_id}/{filename}
                # or /outputs/agent_{hash}/{conversation_id}/{filename}
                audio_path = None
                if audio_url.startswith(agixt_uri):
                    path_part = audio_url[len(agixt_uri) :]
                elif audio_url.startswith("/outputs/"):
                    path_part = audio_url
                else:
                    continue

                # Convert /outputs/... to a path under the working directory
                # Split into components and sanitize each with os.path.basename
                # to prevent path traversal (CodeQL-recognized sanitizer)
                relative = path_part.replace("/outputs/", "", 1)
                relative_parts = relative.replace("\\", "/").split("/")
                safe_parts = [
                    os.path.basename(p)
                    for p in relative_parts
                    if p and p not in (".", "..")
                ]
                if not safe_parts:
                    continue
                candidate_path = os.path.join(working_directory, *safe_parts)
                # Normalize and validate the path stays within workspace root
                workspace_root = os.path.realpath(working_directory)
                audio_path = os.path.realpath(candidate_path)
                if os.path.commonpath([workspace_root, audio_path]) != workspace_root:
                    logging.warning(
                        f"Skipping audio transcription for path outside workspace: {audio_path}"
                    )
                    continue

                if not os.path.exists(audio_path):
                    logging.warning(
                        f"Audio file not found for transcription: {audio_path}"
                    )
                    continue

                # Get the default agent for transcription
                conv_obj = Conversations(
                    conversation_name=conversation_name,
                    user=user,
                    conversation_id=conversation_id,
                )
                agent_id = conv_obj.get_agent_id(user_id)
                if not agent_id:
                    logging.warning("No agent found for audio transcription")
                    continue

                agent_obj = Agent(user=user, agent_name=None)
                # Get the actual agent by ID
                from DB import get_session, Agent as DBAgentModel

                session = get_session()
                db_agent = (
                    session.query(DBAgentModel)
                    .filter(DBAgentModel.id == agent_id)
                    .first()
                )
                if db_agent:
                    agent_obj = Agent(user=user, agent_name=db_agent.name)
                session.close()

                # Transcribe the audio
                transcription = await agent_obj.transcribe_audio(audio_path=audio_path)
                if not transcription or len(transcription.strip()) < 1:
                    continue

                # Update the stored message to include transcription below the audio
                audio_link = f"[{alt_text}]({audio_url})"
                updated_message = stored_message.replace(
                    audio_link,
                    f"{audio_link}\n\n> **Transcription:** {transcription.strip()}",
                )
                stored_message = updated_message

            except Exception as e:
                logging.warning(f"Failed to transcribe audio in channel message: {e}")
                continue

        # If no transcription was added, skip the update
        if stored_message == original_message:
            return

        # Update message in DB
        conv_obj = Conversations(
            conversation_name=conversation_name,
            user=user,
            conversation_id=conversation_id,
        )
        conv_obj.update_message_by_id(
            message_id=message_id,
            new_message=stored_message,
        )

        # Broadcast the update via WebSocket
        await conversation_message_broadcaster.broadcast_message_event(
            conversation_id=conversation_id,
            event_type="message_updated",
            message_data={
                "id": message_id,
                "message": stored_message,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

    except Exception as e:
        logging.warning(f"Background audio transcription failed: {e}")


@app.put(
    "/v1/conversation/{conversation_id}/message/{message_id}",
    response_model=ResponseMessage,
    summary="Update Message by ID",
    description="Updates a message's content using conversation ID and message ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_message_v1(
    conversation_id: str,
    message_id: str,
    update_model: UpdateMessageModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    ).update_message_by_id(
        message_id=message_id,
        new_message=update_model.new_message,
    )
    return ResponseMessage(message="Message updated.")


@app.delete(
    "/v1/conversation/{conversation_id}/message/{message_id}",
    response_model=ResponseMessage,
    summary="Delete Message by ID",
    description="Deletes a specific message using conversation ID and message ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_message_v1(
    conversation_id: str,
    message_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    ).delete_message_by_id(
        message_id=message_id,
    )
    # Mark conversation updated so WebSocket poll loops detect the deletion
    from Conversations import mark_conversation_updated

    mark_conversation_updated(conversation_id)
    return ResponseMessage(message="Message deleted.")


# ============================================
# Message Reactions
# ============================================


@app.post(
    "/v1/conversation/{conversation_id}/message/{message_id}/reactions",
    response_model=ResponseMessage,
    summary="Add Reaction to Message",
    description="Adds an emoji reaction to a message. If the user already reacted with the same emoji, it toggles (removes) it.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def add_reaction(
    conversation_id: str,
    message_id: str,
    body: AddReactionModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    from DB import get_session

    auth = MagicalAuth(token=authorization)
    session = get_session()
    try:
        # Check if user already reacted with same emoji — toggle off
        existing = (
            session.query(MessageReaction)
            .filter(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == str(auth.user_id),
                MessageReaction.emoji == body.emoji,
            )
            .first()
        )
        if existing:
            session.delete(existing)
            session.commit()
            return ResponseMessage(message="Reaction removed.")

        reaction = MessageReaction(
            message_id=message_id,
            user_id=str(auth.user_id),
            emoji=body.emoji,
        )
        session.add(reaction)
        session.commit()
        return ResponseMessage(message="Reaction added.")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get(
    "/v1/conversation/{conversation_id}/message/{message_id}/reactions",
    response_model=MessageReactionsResponse,
    summary="Get Reactions for Message",
    description="Gets all emoji reactions for a specific message.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_reactions(
    conversation_id: str,
    message_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> MessageReactionsResponse:
    from DB import get_session

    auth = MagicalAuth(token=authorization)
    session = get_session()
    try:
        reactions = (
            session.query(MessageReaction)
            .filter(MessageReaction.message_id == message_id)
            .all()
        )
        # Batch-fetch all users at once instead of N+1 individual queries
        user_ids = list({r.user_id for r in reactions if r.user_id})
        users_by_id = {}
        if user_ids:
            users = session.query(User).filter(User.id.in_(user_ids)).all()
            users_by_id = {str(u.id): u for u in users}
        result = []
        for r in reactions:
            u = users_by_id.get(str(r.user_id))
            result.append(
                {
                    "id": str(r.id),
                    "emoji": r.emoji,
                    "user_id": str(r.user_id),
                    "user_email": u.email if u else None,
                    "user_first_name": u.first_name if u else None,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
            )
        return MessageReactionsResponse(reactions=result)
    finally:
        session.close()


@app.delete(
    "/v1/conversation/{conversation_id}/message/{message_id}/reactions/{emoji}",
    response_model=ResponseMessage,
    summary="Remove Reaction from Message",
    description="Removes a specific emoji reaction from a message for the current user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def remove_reaction(
    conversation_id: str,
    message_id: str,
    emoji: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    from DB import get_session

    auth = MagicalAuth(token=authorization)
    session = get_session()
    try:
        reaction = (
            session.query(MessageReaction)
            .filter(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == str(auth.user_id),
                MessageReaction.emoji == emoji,
            )
            .first()
        )
        if not reaction:
            raise HTTPException(status_code=404, detail="Reaction not found")
        session.delete(reaction)
        session.commit()
        return ResponseMessage(message="Reaction removed.")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# ============================================
# Message Pinning
# ============================================


@app.put(
    "/v1/conversation/{conversation_id}/message/{message_id}/pin",
    response_model=ResponseMessage,
    summary="Toggle Pin Message",
    description="Toggles the pinned state of a message. Pinned messages can be viewed via the pinned messages endpoint.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def toggle_pin_message(
    conversation_id: str,
    message_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
    except:
        conversation_name = conversation_id
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    result = c.toggle_pin_message(message_id=message_id)
    pinned = result.get("pinned", False)
    return ResponseMessage(
        message=f"Message {'pinned' if pinned else 'unpinned'} successfully."
    )


@app.get(
    "/v1/conversation/{conversation_id}/pins",
    summary="Get Pinned Messages",
    description="Returns all pinned messages in a conversation.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_pinned_messages(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
    except:
        conversation_name = conversation_id
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    return c.get_pinned_messages()


@app.get(
    "/api/conversation",
    response_model=ConversationHistoryResponse,
    summary="Get Paginated Conversation History",
    description="Retrieves conversation history with pagination support using limit and page parameters.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(
    history: HistoryModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    conversation_history = Conversations(
        conversation_name=history.conversation_name,
        user=user,
        conversation_id=str(conversation_id) if conversation_id else None,
    ).get_conversation(
        limit=history.limit,
        page=history.page,
    )
    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


@app.get(
    "/api/conversation/{conversation_name}",
    response_model=ConversationHistoryResponse,
    summary="Get Conversation History by Name",
    description="Retrieves conversation history using the conversation name with optional pagination.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_data(
    conversation_name: str,
    limit: int = 1000,
    page: int = 1,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(conversation_name)
        conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    conversation_history = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=str(conversation_id) if conversation_id else None,
    ).get_conversation(limit=limit, page=page)
    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


@app.post(
    "/api/conversation",
    response_model=NewConversationHistoryResponse,
    summary="Create New Conversation",
    description="Creates a new conversation with initial content.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def new_conversation_history(
    history: ConversationHistoryModel,
    user=Depends(verify_api_key),
):
    c = Conversations(conversation_name=history.conversation_name, user=user)
    c.new_conversation(conversation_content=history.conversation_content)
    return {
        "id": c.get_conversation_id(),
        "conversation_history": history.conversation_content,
    }


@app.delete(
    "/api/conversation",
    response_model=ResponseMessage,
    summary="Delete Conversation",
    description="Deletes an entire conversation and all its messages.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_history(
    history: ConversationHistoryModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_conversation()
    return ResponseMessage(
        message=f"Conversation `{history.conversation_name}` for agent {history.agent_name} deleted."
    )


@app.delete(
    "/api/conversation/message",
    response_model=ResponseMessage,
    summary="Delete Conversation Message",
    description="Deletes a specific message from a conversation.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_history_message(
    history: ConversationHistoryMessageModel, user=Depends(verify_api_key)
) -> ResponseMessage:
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_message(message=history.message)
    return ResponseMessage(message=f"Message deleted.")


@app.put(
    "/api/conversation/message",
    response_model=ResponseMessage,
    summary="Update Conversation Message",
    description="Updates the content of a specific message in a conversation.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_history_message(
    history: UpdateConversationHistoryMessageModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).update_message(
        message=history.message,
        new_message=history.new_message,
    )
    return ResponseMessage(message=f"Message updated.")


@app.put(
    "/api/conversation/message/{message_id}",
    response_model=ResponseMessage,
    summary="Update Message by ID",
    description="Updates a message's content using its specific ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_by_id(
    message_id: str,
    history: UpdateMessageModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    resolved_conversation_id = None
    try:
        resolved_conversation_id = str(uuid.UUID(history.conversation_name))
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=resolved_conversation_id, user_id=auth.user_id
        )
    except (ValueError, AttributeError):
        pass
    Conversations(
        conversation_name=history.conversation_name,
        user=user,
        conversation_id=resolved_conversation_id,
    ).update_message_by_id(
        message_id=message_id,
        new_message=history.new_message,
    )
    return ResponseMessage(message=f"Message updated.")


@app.delete(
    "/api/conversation/message/{message_id}",
    response_model=ResponseMessage,
    summary="Delete Message by ID",
    description="Deletes a specific message using its ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_by_id(
    message_id: str,
    history: DeleteMessageModel,
    user=Depends(verify_api_key),
):
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_message_by_id(
        message_id=message_id,
    )
    return ResponseMessage(message=f"Message deleted.")


@app.delete(
    "/api/conversation/message/{message_id}/after",
    response_model=ResponseMessage,
    summary="Delete Messages After Message ID",
    description="Deletes all messages after and including the specified message ID. Used for regenerating responses.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_messages_after_id(
    message_id: str,
    history: DeleteMessageModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    result = Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_messages_after(
        message_id=message_id,
    )
    deleted_count = (
        result.get("deleted_count", 0) if isinstance(result, dict) else result
    )
    return ResponseMessage(message=f"Deleted {deleted_count} messages.")


@app.post(
    "/api/conversation/message",
    response_model=MessageIdResponse,
    summary="Log Conversation Interaction",
    description="Logs a new message or interaction in the conversation and returns the message ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def log_interaction(
    log_interaction: LogInteraction,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(log_interaction.conversation_name)
        log_interaction.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    interaction_id = Conversations(
        conversation_name=log_interaction.conversation_name, user=user
    ).log_interaction(
        message=log_interaction.message,
        role=log_interaction.role,
    )
    return ResponseMessage(message=str(interaction_id))


@app.get(
    "/v1/conversation/{conversation_id}/workspace",
    response_model=WorkspaceListResponse,
    summary="List Conversation Workspace Items",
    description="Returns the folder tree for a conversation's workspace, optionally scoped to a sub-path.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_workspace(
    conversation_id: str,
    path: Optional[str] = None,
    recursive: bool = True,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)
    try:
        normalized_path = workspace_manager._normalize_relative_path(path)
        workspace_data = workspace_manager.list_workspace_tree(
            context["agent_id"],
            context["conversation_id"],
            path=normalized_path if normalized_path else None,
            recursive=recursive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WorkspaceListResponse(**workspace_data)


@app.post(
    "/v1/conversation/{conversation_id}/workspace/upload",
    response_model=WorkspaceListResponse,
    summary="Upload Files to Conversation Workspace",
    description="Uploads one or more files into the conversation workspace at the specified path.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def upload_conversation_workspace_files(
    conversation_id: str,
    files: List[UploadFile] = File(...),
    destination_path: Optional[str] = Form(None),
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload")

    context = _resolve_conversation_workspace(conversation_id, user, authorization)
    try:
        normalized_destination = workspace_manager._normalize_relative_path(
            destination_path
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    destination_relative = normalized_destination or None

    for upload in files:
        if not upload.filename:
            continue
        upload.file.seek(0)
        try:
            workspace_manager.save_upload(
                context["agent_id"],
                context["conversation_id"],
                destination_relative,
                upload.filename,
                upload.file,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            await upload.close()

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    listing_path = destination_relative if destination_relative else None
    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=listing_path,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


@app.post(
    "/v1/conversation/{conversation_id}/workspace/folder",
    response_model=WorkspaceListResponse,
    summary="Create Workspace Folder",
    description="Creates a new folder within the conversation workspace.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def create_conversation_workspace_folder(
    conversation_id: str,
    payload: WorkspaceFolderCreateModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)
    parent_path = payload.parent_path if payload.parent_path not in (None, "") else None

    try:
        normalized_parent = workspace_manager._normalize_relative_path(parent_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parent_relative = normalized_parent or None

    try:
        workspace_manager.create_folder(
            context["agent_id"],
            context["conversation_id"],
            parent_relative,
            payload.folder_name,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Folder already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=parent_relative,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


@app.delete(
    "/v1/conversation/{conversation_id}/workspace/item",
    response_model=WorkspaceListResponse,
    summary="Delete Workspace Item",
    description="Deletes a file or folder from the conversation workspace.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_workspace_item(
    conversation_id: str,
    payload: WorkspaceDeleteModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)

    normalized_path = None
    try:
        normalized_path = workspace_manager._normalize_relative_path(payload.path)
        workspace_manager.delete_item(
            context["agent_id"], context["conversation_id"], normalized_path
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workspace item not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    path_parts = (
        [part for part in normalized_path.split("/") if part] if normalized_path else []
    )
    parent_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else None

    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=parent_path,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


@app.get(
    "/v1/conversation/{conversation_id}/workspace/download",
    summary="Download Workspace File",
    description="Streams a workspace file for download.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def download_conversation_workspace_file(
    conversation_id: str,
    path: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    context = _resolve_conversation_workspace(conversation_id, user, authorization)

    try:
        relative_path = workspace_manager._normalize_relative_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not relative_path:
        raise HTTPException(status_code=400, detail="A valid file path is required")

    filename = relative_path.split("/")[-1]
    content_type, _ = mimetypes.guess_type(filename)

    try:
        stream = workspace_manager.stream_file(
            context["agent_id"], context["conversation_id"], relative_path
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        stream,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )


@app.put(
    "/v1/conversation/{conversation_id}/workspace/item",
    response_model=WorkspaceListResponse,
    summary="Move or Rename Workspace Item",
    description="Moves or renames a file or folder within the conversation workspace.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def move_conversation_workspace_item(
    conversation_id: str,
    payload: WorkspaceMoveModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)

    try:
        source_relative = workspace_manager._normalize_relative_path(
            payload.source_path
        )
        destination_relative_input = workspace_manager._normalize_relative_path(
            payload.destination_path
        )
        destination_relative = workspace_manager.move_item(
            context["agent_id"],
            context["conversation_id"],
            source_relative,
            destination_relative_input,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source item not found") from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Destination already exists"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    path_parts = [part for part in destination_relative.strip("/").split("/") if part]
    parent_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else None

    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=parent_path,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


# Ask AI to rename the conversation
@app.put(
    "/api/conversation",
    response_model=Dict[str, str],
    summary="Rename Conversation",
    description="Renames an existing conversation, optionally using AI to generate a new name.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def rename_conversation(
    rename: RenameConversationModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(rename.conversation_name)
        rename.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    agixt = AGiXT(
        user=user,
        agent_name=rename.agent_name,
        api_key=authorization,
        conversation_name=rename.conversation_name,
    )
    c = agixt.conversation
    if rename.new_conversation_name == "-":
        conversation_list = c.get_conversations()
        # Build a hardcoded prompt for naming the conversation. We do NOT use
        # the prompt template files here because they are only re-imported on
        # database seed and edits won't take effect on existing installs.
        # Pull the recent conversation history to base the name on.
        try:
            messages = c.get_conversation(limit=20, page=1)
            if isinstance(messages, dict) and "interactions" in messages:
                messages = messages["interactions"]
            history_lines = []
            for m in messages or []:
                role = m.get("role", "user") if isinstance(m, dict) else "user"
                msg = m.get("message", "") if isinstance(m, dict) else str(m)
                if not msg:
                    continue
                # Skip activity/system noise.
                if msg.startswith("[ACTIVITY]") or msg.startswith("[SUBACTIVITY]"):
                    continue
                history_lines.append(f"{role}: {msg}")
            conversation_history = "\n".join(history_lines[-20:])
        except Exception:
            conversation_history = ""

        # These prefixes indicate the model returned a summary/description instead
        # of a short title.  Any parsed name starting with one of these is
        # treated as a bad result and triggers a retry.
        _BAD_TITLE_PREFIXES = (
            "topics discussed",
            "topics:",
            "topic:",
            "summary",
            "conversation",
            "discussion",
            "chat",
            "overview",
            "about:",
            "subject:",
            "re:",
            "regarding",
        )

        def _is_bad_name(name: str) -> bool:
            if not name:
                return True
            lower = name.lower().strip()
            if any(lower.startswith(p) for p in _BAD_TITLE_PREFIXES):
                return True
            # Bad if it reads like a sentence (contains a period mid-name or
            # exceeds a reasonable word count for a sidebar title).
            if len(name.split()) > 8:
                return True
            return False

        def _build_name_prompt(extra: str = "") -> str:
            return (
                "You are assigning a name to a chat conversation for display in a sidebar list.\n"
                "Your response MUST be a single JSON object and nothing else — no preamble, no explanation.\n\n"
                "STRICT Rules for the name:\n"
                "- 2 to 5 words maximum (hard limit: 50 characters).\n"
                "- It is a SHORT, SPECIFIC TITLE — not a summary, sentence, or label.\n"
                "- FORBIDDEN first words: 'Topics', 'Summary', 'Conversation', 'Discussion',\n"
                "  'Chat', 'Overview', 'About', 'Subject', 'Re', 'Regarding'.\n"
                "- No colons, trailing punctuation, surrounding quotes, or markdown.\n"
                "- Use spaces, not underscores. No '#' characters.\n"
                "- Must be unique vs. the existing names listed below.\n"
                "- Reflect the SPECIFIC subject matter — never something generic.\n\n"
                "GOOD examples: 'Python Unit Testing', 'Mars Mission Budget',\n"
                "               'React Hook Errors', 'Resume Formatting Tips'\n"
                "BAD examples:  'Topics Discussed: AI', 'Conversation About Code',\n"
                "               'Summary of Chat', 'Discussion Overview', 'Chat Session'\n\n"
                f"Existing conversation names to NOT reuse:\n{chr(10).join(conversation_list) if conversation_list else '(none)'}\n\n"
                f"Conversation history to name:\n{conversation_history or '(empty)'}\n\n"
                f"{extra}"
                "Return ONLY JSON — no text before or after it.\n"
                'Format: {"suggested_conversation_name": "Short Title Here"}'
            )

        async def _ask_for_name(extra: str = "") -> str:
            prompt = _build_name_prompt(extra)
            return await agixt.agent.inference(prompt=prompt)

        def _parse_name(raw: str) -> str:
            text = raw or ""
            # Strip code fences.
            if "```json" not in text and "```" in text:
                text = text.replace("```", "```json", 1)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            try:
                data = json.loads(text)
                return str(data.get("suggested_conversation_name", "")).strip()
            except Exception:
                pass
            # Try to extract the JSON value with a regex even if the full
            # parse failed (e.g. model added trailing text after the closing }).
            import re as _re

            match = _re.search(
                r'"suggested_conversation_name"\s*:\s*"([^"]+)"', raw or ""
            )
            if match:
                return match.group(1).strip()
            # Last resort: return the first non-empty line that doesn't look
            # like preamble/junk.
            junk_starts = (
                "topics",
                "summary",
                "conversation",
                "discussion",
                "chat",
                "overview",
                "{",
                "}",
                "```",
                "#",
                "*",
            )
            for line in (raw or "").splitlines():
                line = line.strip().strip('"').strip("'").strip("`").strip("*")
                if line and not any(line.lower().startswith(j) for j in junk_starts):
                    return line
            return ""

        try:
            new_name = _parse_name(await _ask_for_name())
            if _is_bad_name(new_name) or new_name in conversation_list:
                bad = new_name or "(empty)"
                new_name = _parse_name(
                    await _ask_for_name(
                        extra=(
                            f'The previous attempt returned "{bad}" which is NOT acceptable.\n'
                            "It must be a specific 2-5 word title that reflects the actual subject.\n"
                            "Do NOT start with 'Topics Discussed', 'Summary', 'Conversation', "
                            "or any similar generic word.\n\n"
                        )
                    )
                )
            if _is_bad_name(new_name) or new_name in conversation_list:
                new_name = datetime.now().strftime(
                    "Conversation Created %Y-%m-%d %I:%M %p"
                )
        except Exception:
            new_name = datetime.now().strftime("Conversation Created %Y-%m-%d %I:%M %p")
        rename.new_conversation_name = new_name.replace("_", " ")
    if "#" in rename.new_conversation_name:
        rename.new_conversation_name = str(rename.new_conversation_name).replace(
            "#", ""
        )
    # Enforce a short conversation title. The AI is supposed to return a brief
    # title (not a summary), but cap the length defensively in case it returns
    # a sentence or paragraph.
    rename.new_conversation_name = (
        rename.new_conversation_name.strip().strip('"').strip("'")
    )
    # Take only the first line if it returned multiple lines.
    rename.new_conversation_name = (
        rename.new_conversation_name.splitlines()[0]
        if rename.new_conversation_name
        else rename.new_conversation_name
    )
    # Truncate to a reasonable title length.
    if len(rename.new_conversation_name) > 60:
        rename.new_conversation_name = (
            rename.new_conversation_name[:60].rstrip() + "..."
        )
    c.rename_conversation(new_name=rename.new_conversation_name)
    c = Conversations(conversation_name=rename.new_conversation_name, user=user)
    c.log_interaction(
        message=f"[ACTIVITY][INFO] Conversation renamed to `{rename.new_conversation_name}`.",
        role=rename.agent_name,
    )
    return {"conversation_name": rename.new_conversation_name}


@app.post(
    "/api/conversation/fork",
    response_model=ResponseMessage,
    summary="Fork Conversation",
    description="Creates a new conversation as a fork from an existing one up to a specific message.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def fork_conversation(
    fork: ConversationFork, user=Depends(verify_api_key)
) -> ResponseMessage:
    conversation_name = fork.conversation_name
    try:
        conversation_id = uuid.UUID(conversation_name)
        user_id = get_user_id(user)
        conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=user_id
        )
    except:
        conversation_id = None
    new_conversation_name = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=str(conversation_id) if conversation_id else None,
    ).fork_conversation(message_id=fork.message_id)
    return ResponseMessage(message=f"Forked conversation to {new_conversation_name}")


@app.post(
    "/v1/conversation/fork/{conversation_id}/{message_id}",
    response_model=ResponseMessage,
    summary="Fork Conversation",
    description="Creates a new conversation as a fork from an existing one up to a specific message.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def forkconversation(
    conversation_id: str, message_id: str, user=Depends(verify_api_key)
) -> ResponseMessage:
    user_id = get_user_id(user)
    try:
        conversation_id = uuid.UUID(conversation_id)
        conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=user_id
        )
    except:
        conversation_id = None
    new_conversation_name = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=str(conversation_id) if conversation_id else None,
    ).fork_conversation(message_id=str(message_id))
    return ResponseMessage(message=f"Forked conversation to {new_conversation_name}")


@app.get(
    "/v1/conversation/{conversation_id}/tts/{message_id}",
    response_model=Dict[str, str],
    summary="Get Text-to-Speech for Message",
    description="Converts a specific message to speech and returns the audio URL.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_tts(
    conversation_id: str,
    message_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    # If conversation_id is "-", look up the conversation from the message_id
    if conversation_id == "-":
        conversation_name = get_conversation_name_by_message_id(
            message_id=message_id, user_id=auth.user_id
        )
        if not conversation_name:
            raise HTTPException(status_code=404, detail="Message not found")
    else:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    message = c.get_message_by_id(message_id=message_id)
    agent_name = c.get_last_agent_name()
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    tts_url = await agent.text_to_speech(text=message)
    new_message = (
        f'{message}\n<audio controls><source src="{tts_url}" type="audio/wav"></audio>'
    )
    c.update_message_by_id(message_id=message_id, new_message=new_message)
    return {"message": new_message}


@app.post(
    "/v1/conversation/{conversation_id}/stop",
    response_model=ResponseMessage,
    summary="Stop Active Conversation",
    description="Stops an active conversation and cancels any running AI process.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def stop_conversation(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    """
    Stop an active conversation by cancelling its task
    """
    auth = MagicalAuth(token=authorization)

    # Handle special case of "-" conversation ID
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )

    # Validate that the conversation exists and user has access
    try:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
    except Exception as e:
        logging.error(f"Error getting conversation name for {conversation_id}: {e}")
        return ResponseMessage(
            message=f"Conversation {conversation_id} not found or access denied."
        )

    # Attempt to stop the conversation
    success = await worker_registry.stop_conversation(
        conversation_id=conversation_id, user_id=auth.user_id
    )

    if success:
        # Log the stop action to the conversation
        c = Conversations(
            conversation_name=conversation_name,
            user=user,
            conversation_id=conversation_id,
        )
        c.log_interaction(
            message="[ACTIVITY][INFO] Conversation stopped by user.",
            role="SYSTEM",
        )
        return ResponseMessage(
            message=f"Successfully stopped conversation {conversation_id}."
        )
    else:
        return ResponseMessage(
            message=f"Conversation {conversation_id} was not active or could not be stopped."
        )


@app.post(
    "/v1/conversations/stop",
    response_model=ResponseMessage,
    summary="Stop All User Conversations",
    description="Stops all active conversations for the authenticated user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def stop_all_conversations(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    """
    Stop all active conversations for a user
    """
    auth = MagicalAuth(token=authorization)

    stopped_count = await worker_registry.stop_user_conversations(user_id=auth.user_id)

    return ResponseMessage(message=f"Stopped {stopped_count} active conversation(s).")


@app.get(
    "/v1/conversations/active",
    response_model=Dict[str, Dict],
    summary="Get Active Conversations",
    description="Retrieves all active conversations for the authenticated user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_active_conversations(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get all active conversations for a user
    """
    auth = MagicalAuth(token=authorization)

    active_conversations = worker_registry.get_user_conversations(user_id=auth.user_id)

    # Remove the task object from the response as it's not serializable
    for conversation_id, info in active_conversations.items():
        if "task" in info:
            del info["task"]

    return {"active_conversations": active_conversations}


# WebSocket endpoint for streaming conversation updates
@app.websocket("/v1/conversation/{conversation_id}/stream")
async def conversation_stream(
    websocket: WebSocket, conversation_id: str, authorization: str = None
):
    """
    WebSocket endpoint for streaming real-time conversation updates.

    This endpoint allows clients to subscribe to conversation updates and receive
    real-time notifications when new messages are added, updated, or deleted.

    Parameters:
    - conversation_id: The ID of the conversation to stream
    - authorization: Bearer token for authentication (can be passed as query param)

    The WebSocket will send JSON messages with the following structure:
    {
        "type": "message_added" | "message_updated" | "message_deleted" | "error" | "heartbeat",
        "data": {
            "id": "message_id",
            "role": "user|agent_name",
            "message": "message_content",
            "timestamp": "ISO datetime",
            "updated_at": "ISO datetime",
            "updated_by": "user_id",
            "feedback_received": boolean
        }
    }
    """
    await websocket.accept()

    try:
        # Get authorization token from query params if not in header
        if not authorization:
            authorization = websocket.query_params.get("authorization")

        if not authorization:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Authorization token required"})
            )
            await websocket.close()
            return

        # Authenticate user using the same logic as verify_api_key
        try:
            # Import the verify_api_key function to reuse the same authentication logic
            from ApiClient import verify_api_key

            # Create a mock header object for verify_api_key
            class MockHeader:
                def __init__(self, value):
                    self.value = value

                def __str__(self):
                    return self.value

            # Use the same authentication logic as other endpoints
            user = verify_api_key(authorization=MockHeader(authorization))
            auth = MagicalAuth(token=authorization)
        except Exception as e:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"Authentication failed: {str(e)}"}
                )
            )
            await websocket.close()
            return

        # Get conversation name from ID, handle special case of "-"
        try:
            if conversation_id == "-":
                conversation_id = get_conversation_id_by_name(
                    conversation_name="-", user_id=auth.user_id
                )
            conversation_name = get_conversation_name_by_id(
                conversation_id=conversation_id, user_id=auth.user_id
            )
        except Exception as e:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"Conversation not found: {str(e)}"}
                )
            )
            await websocket.close()
            return

        # Initialize conversation handler with conversation_id so we can detect renames
        c = Conversations(
            conversation_name=conversation_name,
            user=user,
            conversation_id=conversation_id,
        )

        # Get initial conversation history
        # Respect client-requested limit (via ?limit= query param), defaulting to 500.
        # Keep this bounded to avoid unbounded payloads while still supporting
        # long-running activity-heavy sessions.
        try:
            ws_limit_str = websocket.query_params.get("limit", "500")
            try:
                ws_limit = max(1, min(int(ws_limit_str), 2000))  # Clamp 1-2000
            except (ValueError, TypeError):
                ws_limit = 500
            initial_history = c.get_conversation(limit=ws_limit)

            messages = []
            if initial_history is None:
                messages = []
            elif isinstance(initial_history, list):
                # History is directly a list of messages
                messages = initial_history
            elif (
                isinstance(initial_history, dict) and "interactions" in initial_history
            ):
                # History is a dict with interactions key
                messages = initial_history["interactions"]
            else:
                # Try to convert to list if it's some other format
                messages = []
                logging.warning(
                    f"Unexpected initial_history format: {type(initial_history)}"
                )

            # Batch all initial messages into a single WebSocket send for efficiency
            # This reduces N+1 WebSocket sends to just 1, significantly improving load time
            if messages:
                serializable_messages = [
                    make_json_serializable(msg) for msg in messages
                ]
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "initial_data",
                            "data": serializable_messages,
                            "conversation_id": conversation_id,
                        }
                    )
                )

        except Exception as e:
            # Send error message to client for debugging
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error loading conversation history: {str(e)}",
                    }
                )
            )

        # Send initial connection confirmation
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "conversation_id": conversation_id,
                    "conversation_name": conversation_name,
                }
            )
        )

        # Register with the conversation message broadcaster for real-time updates
        await conversation_message_broadcaster.connect(websocket, conversation_id)

        # Track conversation name to detect renames
        last_known_name = conversation_name

        # Track the last message count to detect new messages
        last_message_count = len(messages) if messages else 0
        # Convert all IDs to strings for consistent comparison
        previous_message_ids = (
            {str(msg.get("id")) for msg in messages if msg.get("id")}
            if messages
            else set()
        )
        # Track which message IDs we've sent updates for in this poll cycle
        updated_message_ids_this_cycle = set()
        last_check_time = datetime.now()
        last_heartbeat_time = datetime.now()
        last_rename_check_time = datetime.now()

        # Adaptive poll interval: grows from 0.5s to 3s when idle, resets on activity
        poll_interval = 0.5
        consecutive_empty_polls = 0

        # Main streaming loop
        while True:
            try:
                # Use wait_for with adaptive timeout
                try:
                    message_data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=poll_interval
                    )

                    # Handle incoming messages
                    if message_data.get("type") == "ping":
                        # Respond to ping with pong
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "pong",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        )
                    elif message_data.get("type") == "typing":
                        # Broadcast typing indicator to other connections in this conversation
                        typing_data = {
                            "user_id": str(auth.user_id),
                            "email": str(user),
                            "first_name": "",
                            "last_name": "",
                            "timestamp": datetime.now().isoformat(),
                        }
                        # Get user details from DB
                        try:
                            from DB import get_session

                            with get_session() as session:
                                db_user = (
                                    session.query(User)
                                    .filter(User.id == auth.user_id)
                                    .first()
                                )
                                if db_user:
                                    typing_data["first_name"] = db_user.first_name or ""
                                    typing_data["last_name"] = db_user.last_name or ""
                        except Exception:
                            pass
                        await conversation_message_broadcaster.broadcast_typing_event(
                            conversation_id, typing_data, exclude_websocket=websocket
                        )

                except asyncio.TimeoutError:
                    # No incoming message, continue to check for updates
                    pass
                except WebSocketDisconnect:
                    # Client disconnected
                    break
                except Exception as e:
                    # Error receiving message, but don't break the connection
                    logging.warning(f"Error receiving WebSocket message: {e}")

                # Use efficient change detection instead of fetching all messages
                changes = c.get_conversation_changes(
                    since_timestamp=last_check_time,
                    last_known_ids=(
                        previous_message_ids if previous_message_ids else None
                    ),
                )

                # Handle deleted messages
                if changes["deleted_ids"]:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "messages_deleted",
                                "conversation_id": conversation_id,
                                "data": {
                                    "previous_count": last_message_count,
                                    "current_count": changes["current_count"],
                                    "deleted_count": len(changes["deleted_ids"]),
                                    "deleted_message_ids": changes["deleted_ids"],
                                },
                            }
                        )
                    )
                    logging.info(
                        f"WebSocket: Sent messages_deleted event for {len(changes['deleted_ids'])} message(s)"
                    )
                    # Update IDs after deletion
                    for deleted_id in changes["deleted_ids"]:
                        previous_message_ids.discard(deleted_id)

                # Handle new messages - only send messages we haven't already sent
                for message in changes["new_messages"]:
                    message_id = str(message.get("id")) if message.get("id") else None
                    # Skip if we've already sent this message
                    if message_id and message_id in previous_message_ids:
                        continue
                    # Skip if this was already sent via broadcast
                    if (
                        message_id
                        and conversation_message_broadcaster.was_sent_to_connection(
                            websocket, message_id
                        )
                    ):
                        logging.debug(
                            f"WebSocket: Skipping already-sent new message {message_id}"
                        )
                        if message_id:
                            previous_message_ids.add(message_id)
                        continue
                    serializable_message = make_json_serializable(message)
                    logging.debug(f"WebSocket: Sending message_added for {message_id}")
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "message_added",
                                "data": serializable_message,
                                "conversation_id": conversation_id,
                            }
                        )
                    )
                    # Track new message ID
                    if message_id:
                        previous_message_ids.add(message_id)
                        # Also track that we just sent this as "added" - don't send as "updated" too
                        updated_message_ids_this_cycle.add(message_id)
                        # Mark in broadcaster so concurrent broadcast task won't re-send
                        conversation_message_broadcaster.mark_sent_to_connection(
                            websocket, message_id
                        )

                # Handle updated messages - skip any we just sent as "added" or were broadcasted
                for message in changes["updated_messages"]:
                    message_id = str(message.get("id")) if message.get("id") else None
                    # Skip if we just sent this message as "added" in this cycle
                    if message_id and message_id in updated_message_ids_this_cycle:
                        logging.debug(
                            f"WebSocket: Skipping updated message {message_id} (already sent as added)"
                        )
                        continue
                    # Skip if this was already sent via broadcast
                    if (
                        message_id
                        and conversation_message_broadcaster.was_sent_to_connection(
                            websocket, message_id
                        )
                    ):
                        logging.debug(
                            f"WebSocket: Skipping already-sent updated message {message_id}"
                        )
                        continue
                    logging.debug(
                        f"WebSocket: Sending message_updated for {message_id}"
                    )
                    serializable_message = make_json_serializable(message)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "message_updated",
                                "data": serializable_message,
                                "conversation_id": conversation_id,
                            }
                        )
                    )
                    # Mark in broadcaster so concurrent broadcast task won't re-send
                    if message_id:
                        conversation_message_broadcaster.mark_sent_to_connection(
                            websocket, message_id
                        )

                # Reset per-cycle tracking
                updated_message_ids_this_cycle.clear()

                # Check for conversation rename (throttled to every 15 seconds)
                current_time = datetime.now()
                time_since_rename_check = (
                    current_time - last_rename_check_time
                ).total_seconds()
                if time_since_rename_check >= 15:
                    last_rename_check_time = current_time
                    current_name = c.get_current_name_from_db()
                    if current_name and current_name != last_known_name:
                        old_name = last_known_name
                        last_known_name = current_name
                        # Update the conversation object's name as well
                        c.conversation_name = current_name
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "conversation_renamed",
                                    "data": {
                                        "conversation_id": (
                                            str(conversation_id)
                                            if conversation_id
                                            else None
                                        ),
                                        "old_name": old_name,
                                        "new_name": current_name,
                                    },
                                }
                            )
                        )
                        logging.info(
                            f"WebSocket: Sent conversation_renamed event '{old_name}' -> '{current_name}'"
                        )

                # Update tracking
                last_message_count = changes["current_count"]
                last_check_time = datetime.now()

                # Adaptive poll interval: grow when idle, shrink on activity
                has_changes = (
                    changes["new_messages"]
                    or changes["updated_messages"]
                    or changes["deleted_ids"]
                )
                if has_changes:
                    # Activity detected — reset to fast polling
                    consecutive_empty_polls = 0
                    poll_interval = 0.5
                else:
                    # No changes — gradually increase poll interval (0.5 → 1 → 1.5 → 2 → 2.5 → 3s)
                    consecutive_empty_polls += 1
                    if consecutive_empty_polls >= 4:
                        poll_interval = min(poll_interval + 0.5, 3.0)

                # Send heartbeat every 30 seconds to keep connection alive
                current_time = datetime.now()
                time_since_last_heartbeat = (
                    current_time - last_heartbeat_time
                ).total_seconds()

                if time_since_last_heartbeat >= 30:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "heartbeat",
                                "timestamp": current_time.isoformat(),
                            }
                        )
                    )
                    last_heartbeat_time = current_time

            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.error(f"Error in conversation stream: {e}")
                try:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
                except:
                    # Connection likely closed
                    break

        # Cleanup: Unregister from the conversation message broadcaster
        await conversation_message_broadcaster.disconnect(websocket, conversation_id)

    except Exception as e:
        logging.error(f"Unexpected error in conversation stream: {e}")
        # Ensure cleanup even on unexpected errors
        try:
            await conversation_message_broadcaster.disconnect(
                websocket, conversation_id
            )
        except:
            pass
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"Unexpected error: {str(e)}"})
            )
            await websocket.close()
        except Exception as close_error:
            log_silenced_exception(
                close_error, "conversation_stream: closing websocket after error"
            )


# User-level WebSocket endpoint for global notifications
@app.websocket("/v1/user/notifications")
async def user_notifications_stream(websocket: WebSocket, authorization: str = None):
    """
    WebSocket endpoint for streaming user-level notifications across all conversations.

    This endpoint allows clients to receive real-time notifications when:
    - A new conversation is created
    - A conversation is deleted
    - A conversation is renamed
    - A new message is added to any conversation

    Parameters:
    - authorization: Bearer token for authentication (can be passed as query param)

    The WebSocket will send JSON messages with the following structure:
    {
        "type": "conversation_created" | "conversation_deleted" | "conversation_renamed" | "message_added" | "error" | "heartbeat",
        "data": {
            // Event-specific data
        }
    }
    """
    await websocket.accept()
    user_id = None

    try:
        # Get authorization token from query params if not in header
        if not authorization:
            authorization = websocket.query_params.get("authorization")

        if not authorization:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Authorization token required"})
            )
            await websocket.close()
            return

        # Authenticate user
        try:
            from ApiClient import verify_api_key

            class MockHeader:
                def __init__(self, value):
                    self.value = value

                def __str__(self):
                    return self.value

            user = verify_api_key(authorization=MockHeader(authorization))
            auth = MagicalAuth(token=authorization)
            user_id = auth.user_id
        except Exception as e:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"Authentication failed: {str(e)}"}
                )
            )
            await websocket.close()
            return

        # Register connection
        await user_notification_manager.connect(websocket, user_id)

        # Send connection confirmation with initial conversation list
        c = Conversations(user=user)
        conversations = c.get_conversations_with_detail()
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "user_id": user_id,
                    "conversations": (
                        make_json_serializable(conversations) if conversations else {}
                    ),
                }
            )
        )

        # Main loop - wait for ping/pong to keep connection alive
        last_heartbeat_time = datetime.now()

        while True:
            try:
                try:
                    message_data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=1.0
                    )

                    if message_data.get("type") == "ping":
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "pong",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        )

                except asyncio.TimeoutError:
                    pass
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logging.warning(f"Error receiving WebSocket message: {e}")

                # Send heartbeat every 30 seconds
                current_time = datetime.now()
                time_since_last_heartbeat = (
                    current_time - last_heartbeat_time
                ).total_seconds()

                if time_since_last_heartbeat >= 30:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "heartbeat",
                                "timestamp": current_time.isoformat(),
                            }
                        )
                    )
                    last_heartbeat_time = current_time

            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.error(f"Error in user notifications stream: {e}")
                try:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
                except:
                    break

    except Exception as e:
        logging.error(f"Unexpected error in user notifications stream: {e}")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"Unexpected error: {str(e)}"})
            )
            await websocket.close()
        except Exception as close_error:
            log_silenced_exception(
                close_error, "user_notifications_stream: closing websocket after error"
            )
    finally:
        if user_id:
            await user_notification_manager.disconnect(websocket, user_id)


async def notify_user_conversation_created(
    user_id: str, conversation_id: str, conversation_name: str, agent_id: str = None
):
    """Notify user when a new conversation is created."""
    await user_notification_manager.broadcast_to_user(
        user_id,
        {
            "type": "conversation_created",
            "data": {
                "conversation_id": conversation_id,
                "conversation_name": conversation_name,
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
            },
        },
    )


async def notify_user_conversation_deleted(
    user_id: str, conversation_id: str, conversation_name: str
):
    """Notify user when a conversation is deleted."""
    await user_notification_manager.broadcast_to_user(
        user_id,
        {
            "type": "conversation_deleted",
            "data": {
                "conversation_id": conversation_id,
                "conversation_name": conversation_name,
                "timestamp": datetime.now().isoformat(),
            },
        },
    )


async def notify_user_conversation_renamed(
    user_id: str, conversation_id: str, old_name: str, new_name: str
):
    """Notify user when a conversation is renamed."""
    await user_notification_manager.broadcast_to_user(
        user_id,
        {
            "type": "conversation_renamed",
            "data": {
                "conversation_id": conversation_id,
                "old_name": old_name,
                "new_name": new_name,
                "timestamp": datetime.now().isoformat(),
            },
        },
    )


async def notify_user_message_added(
    user_id: str,
    conversation_id: str,
    conversation_name: str,
    message_id: str,
    message: str,
    role: str,
):
    """Notify user when a new message is added to any conversation."""
    # Build clean notification preview: resolve mentions, strip metadata
    import re
    from DB import get_session, User

    preview = message
    try:
        with get_session() as session:
            # Resolve <@userId> mentions
            mention_re = re.compile(r"<@([0-9a-f-]{36})>")
            uids = set(mention_re.findall(preview))
            if uids:
                uid_to_name = {}
                users = session.query(User).filter(User.id.in_(list(uids))).all()
                for u in users:
                    first = getattr(u, "first_name", "") or ""
                    last = getattr(u, "last_name", "") or ""
                    uid_to_name[str(u.id)] = f"{first} {last}".strip() or "User"
                preview = mention_re.sub(
                    lambda m: f"@{uid_to_name.get(m.group(1), 'User')}", preview
                )
            # Strip metadata tags and markdown bold
            preview = re.sub(r"\[ref:[^\[\]]+\]", "", preview)
            preview = re.sub(r"\[uid:[^\[\]]+\]", "", preview)
            preview = preview.replace("**", "")
            preview = re.sub(r"\s+", " ", preview).strip()
    except Exception:
        pass
    if len(preview) > 100:
        preview = preview[:100] + "..."
    await user_notification_manager.broadcast_to_user(
        user_id,
        {
            "type": "message_added",
            "data": {
                "conversation_id": conversation_id,
                "conversation_name": conversation_name,
                "message_id": message_id,
                "message_preview": preview,
                "role": role,
                "timestamp": datetime.now().isoformat(),
            },
        },
    )


async def notify_conversation_participants_message_added(
    sender_user_id: str,
    conversation_id: str,
    conversation_name: str,
    message_id: str,
    message: str,
    role: str,
):
    """Notify ALL participants of a conversation when a new message is added.
    This ensures DM recipients and group channel members get notifications.
    Also sends targeted 'mention' and 'reply' notifications to @mentioned and replied-to users.
    """
    try:
        from DB import get_session, ConversationParticipant, User, Conversation
        import re

        # Build a clean preview: resolve <@userId> mentions, strip metadata tags
        def clean_notification_preview(raw: str, session) -> str:
            """Clean raw message text for notification previews."""
            text = raw
            # Strip reply blockquote lines (> **Author** said: ... > quoted)
            if text.startswith("> **"):
                lines = text.split("\n")
                i = 0
                if re.match(r"^> \*\*.+\*\* said:", lines[0]):
                    i = 1
                while i < len(lines) and (lines[i].startswith("> ") or lines[i] == ">"):
                    i += 1
                # Skip blank separator
                if i < len(lines) and lines[i].strip() == "":
                    i += 1
                actual = "\n".join(lines[i:]).strip()
                if actual:
                    text = actual
            # Resolve <@userId> to display names
            mention_re = re.compile(r"<@([0-9a-f-]{36})>")
            uids_in_text = set(mention_re.findall(text))
            if uids_in_text:
                uid_to_name = {}
                users = (
                    session.query(User).filter(User.id.in_(list(uids_in_text))).all()
                )
                for u in users:
                    first = getattr(u, "first_name", "") or ""
                    last = getattr(u, "last_name", "") or ""
                    uid_to_name[str(u.id)] = f"{first} {last}".strip() or "User"
                text = mention_re.sub(
                    lambda m: f"@{uid_to_name.get(m.group(1), 'User')}", text
                )
            # Strip [ref:...] and [uid:...] metadata tags
            text = re.sub(r"\[ref:[^\[\]]+\]", "", text)
            text = re.sub(r"\[uid:[^\[\]]+\]", "", text)
            # Strip markdown bold from remaining text
            text = text.replace("**", "")
            # Collapse whitespace
            text = re.sub(r"\s+", " ", text).strip()
            # Truncate
            if len(text) > 100:
                text = text[:100] + "..."
            return text

        # Look up sender display name, conversation's company_id, and participants in one session
        sender_name = "Someone"
        company_id = None
        participant_user_ids = []
        with get_session() as session:
            preview = clean_notification_preview(message, session)

            sender = session.query(User).filter(User.id == sender_user_id).first()
            if sender:
                first = getattr(sender, "first_name", "") or ""
                last = getattr(sender, "last_name", "") or ""
                sender_name = f"{first} {last}".strip() or "Someone"
            # Look up company_id from the conversation
            conv = (
                session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            if conv and conv.company_id:
                company_id = str(conv.company_id)
            conversation_type = (
                getattr(conv, "conversation_type", None) if conv else None
            )

            # Get all active participants in same session
            participants = (
                session.query(ConversationParticipant)
                .filter(
                    ConversationParticipant.conversation_id == conversation_id,
                    ConversationParticipant.participant_type == "user",
                    ConversationParticipant.status == "active",
                )
                .all()
            )
            participant_user_ids = [str(p.user_id) for p in participants if p.user_id]

        notification_data = {
            "type": "message_added",
            "data": {
                "conversation_id": conversation_id,
                "conversation_name": conversation_name,
                "conversation_type": conversation_type,
                "message_id": message_id,
                "message_preview": preview,
                "role": role,
                "sender_user_id": sender_user_id,
                "sender_name": sender_name,
                "company_id": company_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

        # Parse @mentions: <@userId> format
        mentioned_user_ids = set()
        mention_pattern = re.compile(r"<@([0-9a-f-]{36})>")
        for match in mention_pattern.finditer(message):
            uid = match.group(1)
            if uid != sender_user_id:  # Don't notify sender about their own mentions
                mentioned_user_ids.add(uid)

        # Parse reply-to: [uid:userId] format
        replied_to_user_ids = set()
        uid_pattern = re.compile(r"\[uid:([0-9a-f-]{36})\]")
        for match in uid_pattern.finditer(message):
            uid = match.group(1)
            if (
                uid != sender_user_id
            ):  # Don't notify sender about replying to themselves
                replied_to_user_ids.add(uid)

        # Notify all participants with the base message_added notification
        for user_id in participant_user_ids:
            await user_notification_manager.broadcast_to_user(
                user_id, notification_data
            )

        # Send targeted mention notifications to @mentioned users
        for uid in mentioned_user_ids:
            mention_notification = {
                "type": "mention",
                "data": {
                    "conversation_id": conversation_id,
                    "conversation_name": conversation_name,
                    "conversation_type": conversation_type,
                    "message_id": message_id,
                    "message_preview": preview,
                    "role": role,
                    "sender_user_id": sender_user_id,
                    "sender_name": sender_name,
                    "company_id": company_id,
                    "timestamp": datetime.now().isoformat(),
                },
            }
            await user_notification_manager.broadcast_to_user(uid, mention_notification)

        # Send targeted reply notifications to replied-to users
        for uid in replied_to_user_ids:
            if uid not in mentioned_user_ids:  # Don't double-notify if also mentioned
                reply_notification = {
                    "type": "reply",
                    "data": {
                        "conversation_id": conversation_id,
                        "conversation_name": conversation_name,
                        "conversation_type": conversation_type,
                        "message_id": message_id,
                        "message_preview": preview,
                        "role": role,
                        "sender_user_id": sender_user_id,
                        "sender_name": sender_name,
                        "company_id": company_id,
                        "timestamp": datetime.now().isoformat(),
                    },
                }
                await user_notification_manager.broadcast_to_user(
                    uid, reply_notification
                )
    except Exception as e:
        logging.warning(f"Failed to notify conversation participants: {e}")
        # Fallback: at least notify the sender
        await notify_user_message_added(
            user_id=sender_user_id,
            conversation_id=conversation_id,
            conversation_name=conversation_name,
            message_id=message_id,
            message=message,
            role=role,
        )


async def broadcast_system_notification(notification_data: dict) -> int:
    """
    Broadcast a system-wide notification to all connected users.
    Used for server maintenance announcements and other admin messages.

    Args:
        notification_data: Dict containing id, title, message, notification_type, expires_at, created_at

    Returns:
        Number of users notified
    """
    from DB import SystemNotification, get_session

    users_notified = await user_notification_manager.broadcast_to_all_users(
        {
            "type": "system_notification",
            "data": {
                "id": notification_data["id"],
                "title": notification_data["title"],
                "message": notification_data["message"],
                "notification_type": notification_data.get("notification_type", "info"),
                "expires_at": notification_data["expires_at"],
                "created_at": notification_data["created_at"],
                "timestamp": datetime.now().isoformat(),
            },
        }
    )

    # Update the notified count in the database
    if users_notified > 0:
        try:
            with get_session() as db:
                notification = (
                    db.query(SystemNotification)
                    .filter(SystemNotification.id == notification_data["id"])
                    .first()
                )
                if notification:
                    notification.notified_count = (
                        notification.notified_count or 0
                    ) + users_notified
                    db.commit()
        except Exception as e:
            logging.warning(f"Failed to update notified_count: {e}")

    logging.info(
        f"System notification '{notification_data['title']}' broadcast to {users_notified} users"
    )
    return users_notified


@app.get(
    "/api/notifications",
    response_model=NotificationResponse,
    summary="Get User Notifications",
    description="Retrieves all notifications for the authenticated user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_notifications(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    notifications = c.get_notifications()
    return {"notifications": notifications}


# Remote Command Execution Endpoint (for CLI remote tools)
@app.post(
    "/v1/conversation/{conversation_id}/remote-command-result",
    summary="Submit Remote Command Result",
    description="Submit the result of a remote command execution from the CLI. This injects the command output into the conversation so the agent can continue processing.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def submit_remote_command_result(
    conversation_id: str,
    result: dict,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Submit the result of a remote command execution.

    This endpoint is called by the CLI after executing a command locally.
    The result is injected into the conversation as an activity log entry,
    allowing the agent to see the command output in its next inference.

    Request body should contain:
    - request_id: The unique ID of the remote command request
    - terminal_id: The terminal session ID
    - exit_code: The command's exit code (0 for success)
    - stdout: Standard output from the command
    - stderr: Standard error from the command
    - working_directory: The current working directory after command execution
    - execution_time_seconds: How long the command took to run
    """
    try:
        auth = MagicalAuth(token=authorization)

        # Resolve conversation
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            conversation_id_str = str(conversation_uuid)
            conversation_name = get_conversation_name_by_id(
                conversation_id=conversation_id_str, user_id=auth.user_id
            )
            if conversation_name is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
        except ValueError:
            conversation_name = conversation_id
            conversation_id_str = get_conversation_id_by_name(
                conversation_name=conversation_name, user_id=auth.user_id
            )

        c = Conversations(
            conversation_name=conversation_name,
            user=user,
            conversation_id=conversation_id_str,
        )

        # Extract result data
        request_id = result.get("request_id", "unknown")
        terminal_id = result.get("terminal_id", "unknown")
        exit_code = result.get("exit_code", -1)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        working_directory = result.get("working_directory", "")
        execution_time = result.get("execution_time_seconds", 0)

        # Format the output
        output_parts = []
        if stdout:
            output_parts.append(f"**stdout:**\n```\n{stdout}\n```")
        if stderr:
            output_parts.append(f"**stderr:**\n```\n{stderr}\n```")

        output_text = "\n\n".join(output_parts) if output_parts else "(no output)"

        # Log the result to the conversation
        status_emoji = "✅" if exit_code == 0 else "❌"

        c.log_interaction(
            role="REMOTE_TERMINAL",
            message=f"[REMOTE_COMMAND_RESULT][{request_id}] {status_emoji} Exit code: {exit_code}\nTerminal: {terminal_id}\nWorking directory: {working_directory}\nExecution time: {execution_time:.2f}s\n\n{output_text}",
        )

        return {
            "status": "success",
            "message": "Remote command result recorded",
            "request_id": request_id,
            "conversation_id": conversation_id_str,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error submitting remote command result: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit remote command result: {str(e)}"
        )


# Conversation Sharing Endpoints
@app.post(
    "/v1/conversation/{conversation_id}/share",
    response_model=ConversationShareResponse,
    summary="Share Conversation",
    description="Creates a shareable link for a conversation, optionally with workspace files. Share can be public or with a specific user by email.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def share_conversation(
    conversation_id: str,
    share_data: ConversationShareCreate,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)

    # Resolve conversation name from ID
    try:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
        if not conversation_name:
            raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Conversation not found: {str(e)}")

    # Create the share
    try:
        c = Conversations(
            conversation_name=conversation_name,
            user=user,
            conversation_id=conversation_id,
        )
        share_info = c.share_conversation(
            share_type=share_data.share_type,
            target_user_email=share_data.email,
            include_workspace=share_data.include_workspace,
            expires_at=share_data.expires_at,
        )
        return ConversationShareResponse(**share_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error sharing conversation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to share conversation: {str(e)}"
        )


@app.get(
    "/v1/conversations/shared",
    response_model=SharedConversationListResponse,
    summary="Get Shared Conversations",
    description="Retrieves all conversations shared with the current user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_shared_conversations(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    shared_conversations = c.get_shared_conversations()
    return {"shared_conversations": shared_conversations}


@app.get(
    "/api/shared/{share_token}",
    response_model=SharedConversationResponse,
    summary="Get Shared Conversation (Public)",
    description="Retrieves a shared conversation using its public share token. No authentication required.",
    tags=["Conversation"],
)
async def get_shared_conversation(share_token: str):
    # This endpoint is public, so we use a default user context
    from Globals import DEFAULT_USER

    try:
        c = Conversations(user=DEFAULT_USER)
        conversation_data = c.get_conversation_by_share_token(share_token)
        return SharedConversationResponse(**conversation_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error retrieving shared conversation: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve shared conversation"
        )


@app.delete(
    "/v1/conversation/share/{share_token}",
    response_model=ResponseMessage,
    summary="Revoke Conversation Share",
    description="Revokes a conversation share by deleting the share link.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def revoke_conversation_share(
    share_token: str,
    user=Depends(verify_api_key),
):
    try:
        c = Conversations(user=user)
        c.revoke_share(share_token)
        return ResponseMessage(message="Share revoked successfully")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error revoking share: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke share")


@app.post(
    "/v1/conversation/import-shared/{share_token}",
    response_model=NewConversationHistoryResponse,
    summary="Import Shared Conversation",
    description="Imports a shared conversation into the user's account, optionally including workspace files.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def import_shared_conversation(
    share_token: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    from Globals import DEFAULT_USER
    from DB import ConversationShare, get_session

    auth = MagicalAuth(token=authorization)
    session = get_session()

    try:
        # Find the share
        share = (
            session.query(ConversationShare)
            .filter(ConversationShare.share_token == share_token)
            .first()
        )

        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # Check if expired
        if share.expires_at and share.expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Share has expired")

        # Get the shared conversation
        from DB import Conversation

        shared_conversation = (
            session.query(Conversation)
            .filter(Conversation.id == share.shared_conversation_id)
            .first()
        )

        if not shared_conversation:
            raise HTTPException(status_code=404, detail="Shared conversation not found")

        # Get all messages
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == shared_conversation.id)
            .order_by(Message.timestamp.asc())
            .all()
        )

        # Build conversation content
        conversation_content = [
            {
                "role": msg.role,
                "message": msg.content,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in messages
        ]

        # Create new conversation for the user
        new_conversation_name = f"Imported: {shared_conversation.name}"
        c = Conversations(conversation_name=new_conversation_name, user=user)
        new_conversation = c.new_conversation(conversation_content=conversation_content)
        # Get the actual conversation ID (not the dict id which might be wrong)
        new_conversation_id = c.get_conversation_id()

        # Copy workspace files if included in share
        if share.include_workspace:
            try:
                # Get DEFAULT_USER's agent that has the workspace files
                from Globals import get_default_user_id

                default_user_id = get_default_user_id()
                if default_user_id:

                    # Get agent name from shared conversation messages
                    agent_message = (
                        session.query(Message)
                        .filter(
                            Message.conversation_id == shared_conversation.id,
                            Message.role != "USER",
                            Message.role != "user",
                        )
                        .order_by(Message.timestamp.desc())
                        .first()
                    )
                    if agent_message:
                        agent_name = agent_message.role

                        # Get source agent (DEFAULT_USER's agent)
                        source_agent = (
                            session.query(DBAgent)
                            .filter(
                                DBAgent.name == agent_name,
                                DBAgent.user_id == default_user_id,
                            )
                            .first()
                        )

                        # Get target agent (current user's agent)
                        target_agent = (
                            session.query(DBAgent)
                            .filter(
                                DBAgent.name == agent_name,
                                DBAgent.user_id == auth.user_id,
                            )
                            .first()
                        )

                        # Create target agent if it doesn't exist
                        if not target_agent:
                            target_agent = DBAgent(
                                name=agent_name,
                                user_id=auth.user_id,
                                settings=source_agent.settings if source_agent else {},
                            )
                            session.add(target_agent)
                            session.commit()

                        if source_agent and target_agent:
                            # Copy workspace files
                            files_copied = (
                                workspace_manager.copy_conversation_workspace(
                                    source_agent_id=str(source_agent.id),
                                    source_conversation_id=str(shared_conversation.id),
                                    target_agent_id=str(target_agent.id),
                                    target_conversation_id=new_conversation_id,
                                )
                            )

                            # Update attachment count
                            total_files = workspace_manager.count_files(
                                str(target_agent.id), new_conversation_id
                            )
                            c.update_attachment_count(total_files)
                        else:
                            logging.error(
                                f"❌ Missing agents - source: {source_agent is not None}, target: {target_agent is not None}"
                            )
                    else:
                        logging.error(
                            f"❌ No agent message found in shared conversation"
                        )
                else:
                    logging.error(f"❌ DEFAULT_USER not found")

            except Exception as e:
                logging.error(f"❌ Error copying workspace files during import: {e}")
                import traceback

                logging.error(traceback.format_exc())
                # Don't fail the import if workspace copy fails

        return {
            "id": new_conversation_id,
            "conversation_history": conversation_content,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error importing shared conversation: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to import shared conversation"
        )
    finally:
        session.close()


# Public workspace endpoints for shared conversations
@app.get(
    "/api/shared/{share_token}/workspace",
    response_model=WorkspaceListResponse,
    summary="List Shared Conversation Workspace (Public)",
    description="Returns the folder tree for a shared conversation's workspace. No authentication required.",
    tags=["Conversation"],
)
async def get_shared_conversation_workspace(
    share_token: str,
    path: Optional[str] = None,
    recursive: bool = True,
):
    from Globals import DEFAULT_USER
    from DB import ConversationShare, get_session

    session = get_session()
    try:
        # Find the share
        share = (
            session.query(ConversationShare)
            .filter(ConversationShare.share_token == share_token)
            .first()
        )

        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # Check if expired
        if share.expires_at and share.expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Share has expired")

        # Check if workspace is included
        if not share.include_workspace:
            raise HTTPException(status_code=403, detail="Workspace not shared")

        # Get the shared conversation from database
        from DB import Conversation

        shared_conversation = (
            session.query(Conversation)
            .filter(Conversation.id == share.shared_conversation_id)
            .first()
        )

        if not shared_conversation:
            raise HTTPException(status_code=404, detail="Shared conversation not found")

        conversation_id = str(shared_conversation.id)

        # Get the DEFAULT_USER's ID to query for their agent
        from Globals import get_default_user_id

        default_user_id = get_default_user_id()
        if not default_user_id:
            raise HTTPException(status_code=500, detail="Default user not found")

        # Get the agent name from the shared conversation's messages
        agent_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == shared_conversation.id,
                Message.role != "USER",
                Message.role != "user",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        if not agent_message:
            logging.error(f"❌ No agent messages found in shared conversation")
            raise HTTPException(
                status_code=400, detail="No agent found in conversation"
            )

        agent_name = agent_message.role
        # Get agent ID directly by name for DEFAULT_USER
        target_agent = (
            session.query(DBAgent)
            .filter(DBAgent.name == agent_name, DBAgent.user_id == default_user_id)
            .first()
        )

        if not target_agent:
            logging.error(f"❌ No agent '{agent_name}' found for DEFAULT_USER")
            raise HTTPException(
                status_code=400,
                detail=f"Agent '{agent_name}' not found for shared workspace",
            )

        agent_id = str(target_agent.id)

        try:
            normalized_path = workspace_manager._normalize_relative_path(path)
            workspace_data = workspace_manager.list_workspace_tree(
                agent_id,
                conversation_id,
                path=normalized_path if normalized_path else None,
                recursive=recursive,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return WorkspaceListResponse(**workspace_data)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error retrieving shared workspace: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve shared workspace"
        )
    finally:
        session.close()


@app.get(
    "/api/shared/{share_token}/workspace/download",
    summary="Download Shared Workspace File (Public)",
    description="Streams a workspace file from a shared conversation for download. No authentication required.",
    tags=["Conversation"],
)
async def download_shared_workspace_file(
    share_token: str,
    path: str,
):
    from Globals import DEFAULT_USER
    from DB import ConversationShare, get_session

    session = get_session()
    try:
        # Find the share
        share = (
            session.query(ConversationShare)
            .filter(ConversationShare.share_token == share_token)
            .first()
        )

        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # Check if expired
        if share.expires_at and share.expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Share has expired")

        # Check if workspace is included
        if not share.include_workspace:
            raise HTTPException(status_code=403, detail="Workspace not shared")

        # Get the shared conversation from database
        from DB import Conversation

        shared_conversation = (
            session.query(Conversation)
            .filter(Conversation.id == share.shared_conversation_id)
            .first()
        )

        if not shared_conversation:
            raise HTTPException(status_code=404, detail="Shared conversation not found")

        conversation_id = str(shared_conversation.id)

        # Get the DEFAULT_USER's ID to query for their agent
        from Globals import get_default_user_id

        default_user_id = get_default_user_id()
        if not default_user_id:
            raise HTTPException(status_code=500, detail="Default user not found")

        # Get the agent name from the shared conversation's messages
        agent_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == shared_conversation.id,
                Message.role != "USER",
                Message.role != "user",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        if not agent_message:
            raise HTTPException(
                status_code=400, detail="No agent found in conversation"
            )

        agent_name = agent_message.role

        # Get agent ID directly by name for DEFAULT_USER
        target_agent = (
            session.query(DBAgent)
            .filter(DBAgent.name == agent_name, DBAgent.user_id == default_user_id)
            .first()
        )

        if not target_agent:
            raise HTTPException(
                status_code=400,
                detail=f"Agent '{agent_name}' not found for shared workspace",
            )

        agent_id = str(target_agent.id)

        try:
            relative_path = workspace_manager._normalize_relative_path(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not relative_path:
            raise HTTPException(status_code=400, detail="A valid file path is required")

        filename = relative_path.split("/")[-1]
        content_type, _ = mimetypes.guess_type(filename)

        try:
            stream = workspace_manager.stream_file(
                agent_id, conversation_id, relative_path
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail="File not found") from exc

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }

        return StreamingResponse(
            stream,
            media_type=content_type or "application/octet-stream",
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error downloading shared workspace file: {e}")
        raise HTTPException(status_code=500, detail="Failed to download file")
    finally:
        session.close()


# =========================================================================
# Group Chat / Discord-like Endpoints
# =========================================================================


@app.post(
    "/v1/conversation/group",
    summary="Create Group Conversation or Thread",
    description="Creates a new group conversation (channel) or thread within a company/group. For threads, provide parent_id (the channel conversation) and optionally parent_message_id (the message that spawned the thread). Adds the creator as owner and optionally adds agents as participants.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def create_group_conversation(
    body: CreateGroupConversationModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    c = Conversations(
        conversation_name=body.conversation_name, user=user, create_if_missing=False
    )
    result = c.create_group_conversation(
        company_id=body.company_id,
        conversation_type=body.conversation_type,
        agents=body.agent_names,
        parent_id=body.parent_id,
        parent_message_id=body.parent_message_id,
        category=body.category,
        invite_only=body.invite_only,
        force_new=body.force_new,
    )
    return result


@app.get(
    "/v1/company/{company_id}/conversations",
    response_model=GroupConversationListResponse,
    summary="Get Group Conversations for Company",
    description="Gets all group conversations (channels) for a company/group that the current user is a participant of.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def get_group_conversations(
    company_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    c = Conversations(user=user)
    conversations = c.get_group_conversations_for_company(company_id=company_id)
    return {"conversations": conversations}


@app.get(
    "/v1/conversation/{conversation_id}/participants",
    summary="Get Conversation Participants",
    description="Gets all active participants (users and agents) in a conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_participants(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    import uuid as _uuid

    try:
        _uuid.UUID(conversation_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Conversation not found")
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name or conversation_name == "-":
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    participants = c.get_participants()
    return {"participants": participants}


@app.post(
    "/v1/conversation/{conversation_id}/participants",
    summary="Add Participant to Conversation",
    description="Adds a user or agent as a participant to a group conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def add_conversation_participant(
    conversation_id: str,
    body: AddParticipantModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    participant_id = c.add_participant(
        user_id=body.user_id,
        agent_id=body.agent_id,
        participant_type=body.participant_type,
        role=body.role,
    )
    return {"participant_id": participant_id}


@app.patch(
    "/v1/conversation/{conversation_id}/participants/{participant_id}",
    summary="Update Participant Role",
    description="Updates a participant's role in the conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def update_conversation_participant_role(
    conversation_id: str,
    participant_id: str,
    body: UpdateParticipantRoleModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    c.update_participant_role(participant_id=participant_id, new_role=body.role)
    return ResponseMessage(message="Participant role updated successfully.")


@app.delete(
    "/v1/conversation/{conversation_id}/participants/{participant_id}",
    summary="Remove Participant from Conversation",
    description="Removes a participant from the conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def remove_conversation_participant(
    conversation_id: str,
    participant_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    c.remove_participant(participant_id=participant_id)
    return ResponseMessage(message="Participant removed successfully.")


@app.post(
    "/v1/conversation/{conversation_id}/leave",
    summary="Leave Conversation",
    description="Current user leaves a group conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def leave_conversation(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from DB import get_session, ConversationParticipant

    session = get_session()
    try:
        participant = (
            session.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == auth.user_id,
                ConversationParticipant.status == "active",
            )
            .first()
        )
        if not participant:
            raise HTTPException(
                status_code=404, detail="You are not a participant in this conversation"
            )
        participant.status = "left"
        session.commit()
        return ResponseMessage(message="Left conversation successfully.")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error leaving conversation: {e}")
    finally:
        session.close()


@app.post(
    "/v1/conversation/{conversation_id}/read",
    summary="Mark Conversation as Read",
    description="Updates the last_read_at timestamp for the current user in a group conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def mark_conversation_read(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    c.update_last_read(user_id=str(auth.user_id))
    return ResponseMessage(message="Conversation marked as read.")


@app.get(
    "/v1/conversation/{conversation_id}/notification-settings",
    summary="Get Notification Settings",
    description="Gets the current user's notification settings for a conversation.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def get_notification_settings(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    from DB import get_session, ConversationParticipant

    auth = MagicalAuth(token=authorization)
    session = get_session()
    try:
        participant = (
            session.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == str(auth.user_id),
                ConversationParticipant.status == "active",
            )
            .first()
        )
        if not participant:
            raise HTTPException(
                status_code=404, detail="Not a participant in this conversation"
            )
        return NotificationSettingsResponse(
            notification_mode=participant.notification_mode or "all",
        )
    finally:
        session.close()


@app.put(
    "/v1/conversation/{conversation_id}/notification-settings",
    summary="Update Notification Settings",
    description="Updates the current user's notification settings for a conversation. Supports 'all' (all messages), 'mentions' (only @mentions), or 'none' (muted).",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def update_notification_settings(
    conversation_id: str,
    body: UpdateNotificationSettingsModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    from DB import get_session, ConversationParticipant

    auth = MagicalAuth(token=authorization)
    valid_modes = {"all", "mentions", "none"}
    if body.notification_mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid notification_mode. Must be one of: {', '.join(valid_modes)}",
        )
    session = get_session()
    try:
        participant = (
            session.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == str(auth.user_id),
                ConversationParticipant.status == "active",
            )
            .first()
        )
        if not participant:
            raise HTTPException(
                status_code=404, detail="Not a participant in this conversation"
            )
        participant.notification_mode = body.notification_mode
        session.commit()
    finally:
        session.close()
    return ResponseMessage(
        message=f"Notification settings updated to '{body.notification_mode}'."
    )


@app.get(
    "/v1/conversation/{conversation_id}/threads",
    response_model=ThreadListResponse,
    summary="Get Threads for Channel",
    description="Gets all threads spawned from messages in a given channel conversation. Returns thread metadata including message count and last activity.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def get_threads(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    c = Conversations(
        conversation_name=conversation_name,
        user=user,
        conversation_id=conversation_id,
    )
    threads = c.get_threads(conversation_id=conversation_id)
    return {"threads": threads}


@app.post(
    "/v1/conversation/{conversation_id}/threads",
    summary="Create Thread from Message",
    description="Creates a new thread conversation from a specific message in a channel. The thread inherits the channel's company_id and adds the creator as owner.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def create_thread(
    conversation_id: str,
    body: CreateGroupConversationModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Parent conversation not found")
    from DB import get_session, Conversation, Message

    # Inherit company_id from parent conversation if not provided
    company_id = body.company_id
    if not company_id or company_id == "private":
        session = get_session()
        try:
            parent_conv = (
                session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            if parent_conv and parent_conv.company_id:
                company_id = str(parent_conv.company_id)
        except Exception:
            pass
        finally:
            session.close()

    c = Conversations(
        conversation_name=body.conversation_name, user=user, create_if_missing=False
    )
    result = c.create_group_conversation(
        company_id=company_id or "",
        conversation_type="thread",
        agents=body.agent_names,
        parent_id=conversation_id,
        parent_message_id=body.parent_message_id,
    )

    # Copy the parent message into the thread as the first message
    # so the thread context is clear (like Discord does)
    if body.parent_message_id and result and result.get("id"):
        session = get_session()
        try:
            parent_msg = (
                session.query(Message)
                .filter(Message.id == str(body.parent_message_id))
                .first()
            )
            if parent_msg:
                thread_conv = Conversations(
                    conversation_name=body.conversation_name,
                    user=user,
                    conversation_id=result["id"],
                )
                thread_conv.log_interaction(
                    role=parent_msg.role,
                    message=parent_msg.content,
                    timestamp=parent_msg.timestamp,
                    sender_user_id=(
                        str(parent_msg.sender_user_id)
                        if parent_msg.sender_user_id
                        else None
                    ),
                )
            else:
                logging.warning(
                    f"Parent message not found for thread copy: id={body.parent_message_id}"
                )
        except Exception as e:
            logging.warning(f"Failed to copy parent message into thread: {e}")
        finally:
            session.close()

    return result


@app.patch(
    "/v1/conversation/{conversation_id}/channel",
    summary="Update Channel Properties",
    description="Updates a channel's properties such as category or name.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def update_channel(
    conversation_id: str,
    body: UpdateChannelModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from DB import get_session, Conversation

    session = get_session()
    try:
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if body.category is not None:
            conversation.category = body.category
        if body.name is not None:
            conversation.name = body.name
        if body.description is not None:
            conversation.description = body.description

        session.commit()
        return {
            "id": str(conversation.id),
            "name": conversation.name,
            "category": getattr(conversation, "category", None),
            "description": getattr(conversation, "description", None),
            "message": "Channel updated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error updating channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to update channel")
    finally:
        session.close()


@app.put(
    "/v1/conversation/{conversation_id}/lock",
    summary="Lock or Unlock a Conversation/Thread",
    description="Locks or unlocks a conversation or thread. When locked, only owners and admins can send messages. Useful for closing threads.",
    tags=["Group Chat"],
    dependencies=[Depends(verify_api_key)],
)
async def lock_conversation(
    conversation_id: str,
    body: dict,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    if not conversation_name:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from DB import get_session, Conversation, ConversationParticipant

    session = get_session()
    try:
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Only owners and admins can lock/unlock
        participant = (
            session.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == auth.user_id,
                ConversationParticipant.status == "active",
            )
            .first()
        )
        if not participant or participant.role not in ("owner", "admin"):
            raise HTTPException(
                status_code=403,
                detail="Only owners and admins can lock/unlock conversations",
            )

        locked = body.get("locked", True)
        conversation.locked = locked
        session.commit()
        return {
            "id": str(conversation.id),
            "locked": conversation.locked,
            "message": f"Conversation {'locked' if locked else 'unlocked'} successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logging.error(f"Error locking conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to lock conversation")
    finally:
        session.close()


def _strip_chatgpt_citations(text: str) -> str:
    """
    Remove ChatGPT inline citation markers from text.

    ChatGPT exports embed citation references like ``citeturn0search4``,
    ``【6†source】``, or ``turn0search7`` directly in the text. These are
    artifacts of ChatGPT's browsing feature and render as garbage in any
    UI that isn't ChatGPT.
    """
    import re

    # Pattern: citeturn{N}search{N}  (sometimes chained: citeturn0search4turn0search7)
    text = re.sub(r"(?:cite)?turn\d+search\d+(?:turn\d+search\d+)*", "", text)
    # Pattern: 【N†source】 or 【N†...】 (CJK brackets with dagger)
    text = re.sub(r"\s*【\d+†[^】]*】\s*", " ", text)
    # Clean up leftover double spaces or trailing spaces before punctuation
    text = re.sub(r"  +", " ", text)
    text = re.sub(r" ([.,;:!?])", r"\1", text)
    return text


def _parse_chatgpt_export(data: list, agent_name: str) -> list:
    """
    Parse ChatGPT conversations.json export format into a list of conversations.

    Handles rich content types:
    - ``text`` / ``multimodal_text``: regular messages (may contain image dicts)
    - ``code``: code interpreter input
    - ``execution_output``: code interpreter results
    - ``tether_browsing_display``: browsing results
    - ``tether_quote``: browsing quotes

    Tool-role messages (DALL-E, browsing, code interpreter) are converted to
    ``[SUBACTIVITY]`` messages. Citation artifacts are stripped. Internal system
    prompt noise (e.g. "GPT-4o returned 1 images…") is filtered.
    """
    conversations = []
    for conv in data:
        title = conv.get("title") or "Untitled"
        mapping = conv.get("mapping", {})
        if not mapping:
            continue

        nodes_by_id = {}
        for node_id, node in mapping.items():
            nodes_by_id[node_id] = node

        # Walk backward from current_node to build ordered path
        current_node = conv.get("current_node")
        ordered_nodes = []
        if current_node and current_node in nodes_by_id:
            path = []
            nid = current_node
            while nid and nid in nodes_by_id:
                path.append(nid)
                nid = nodes_by_id[nid].get("parent")
            path.reverse()
            ordered_nodes = [nodes_by_id[nid] for nid in path if nid in nodes_by_id]
        else:
            ordered_nodes = list(nodes_by_id.values())

        messages = []
        for node in ordered_nodes:
            msg = node.get("message")
            if not msg:
                continue

            author_role = msg.get("author", {}).get("role", "unknown")
            author_name = msg.get("author", {}).get("name", "")
            content = msg.get("content", {})
            content_type = content.get("content_type", "text")
            parts = content.get("parts", [])
            metadata = msg.get("metadata", {})
            create_time = msg.get("create_time")

            timestamp = None
            if create_time:
                try:
                    from datetime import timezone as tz

                    timestamp = datetime.fromtimestamp(
                        create_time, tz=tz.utc
                    ).isoformat()
                except Exception:
                    pass

            # Skip system messages entirely
            if author_role == "system":
                continue

            # Determine the AGiXT role
            if author_role == "user":
                role = "USER"
            else:
                role = agent_name

            # --- Tool messages → subactivities ---
            if author_role == "tool":
                tool_name = author_name or "tool"

                # DALL-E / image generation
                if tool_name == "dalle" or "dall" in tool_name.lower():
                    # Extract the DALL-E prompt from metadata if available
                    dalle_meta = metadata.get("dalle", {})
                    if not dalle_meta and parts:
                        # Some exports put dalle data in the parts
                        for p in parts:
                            if isinstance(p, dict) and p.get("metadata", {}).get(
                                "dalle"
                            ):
                                dalle_meta = p["metadata"]["dalle"]
                                break
                    prompt = dalle_meta.get("prompt", "")
                    if prompt:
                        messages.append(
                            {
                                "role": role,
                                "message": f"[SUBACTIVITY][0][EXECUTION] Generated image with DALL-E\n**Prompt:** {prompt}",
                                "timestamp": timestamp,
                            }
                        )
                    continue

                # Code interpreter / Python execution
                if tool_name == "python" or content_type == "execution_output":
                    text_parts = []
                    for p in parts:
                        if isinstance(p, str) and p.strip():
                            text_parts.append(p)
                    output_text = "\n".join(text_parts)
                    if output_text.strip():
                        if len(output_text) > 2000:
                            output_text = output_text[:2000] + "\n... (truncated)"
                        messages.append(
                            {
                                "role": role,
                                "message": f"[SUBACTIVITY][0][INFO] {output_text}",
                                "timestamp": timestamp,
                            }
                        )
                    continue

                # Web browsing results
                if tool_name == "browser" or content_type == "tether_browsing_display":
                    text_parts = []
                    for p in parts:
                        if isinstance(p, str) and p.strip():
                            text_parts.append(p)
                    browsing_text = "\n".join(text_parts)
                    if browsing_text.strip():
                        if len(browsing_text) > 2000:
                            browsing_text = browsing_text[:2000] + "\n... (truncated)"
                        messages.append(
                            {
                                "role": role,
                                "message": f"[SUBACTIVITY][0][INFO] Web browsing result:\n{browsing_text}",
                                "timestamp": timestamp,
                            }
                        )
                    continue

                # Browsing quotes
                if content_type == "tether_quote":
                    quote_text = content.get("text", "")
                    quote_url = content.get("url", "")
                    quote_title = content.get("title", "")
                    if quote_text:
                        label = quote_title or quote_url or "Quote"
                        messages.append(
                            {
                                "role": role,
                                "message": f"[SUBACTIVITY][0][INFO] **{label}**\n> {quote_text[:1000]}",
                                "timestamp": timestamp,
                            }
                        )
                    continue

                # Generic tool output
                text_parts = [str(p) for p in parts if isinstance(p, str) and p.strip()]
                tool_text = "\n".join(text_parts)
                if tool_text.strip():
                    if len(tool_text) > 2000:
                        tool_text = tool_text[:2000] + "\n... (truncated)"
                    messages.append(
                        {
                            "role": role,
                            "message": f"[SUBACTIVITY][0][INFO] Tool ({tool_name}):\n{tool_text}",
                            "timestamp": timestamp,
                        }
                    )
                continue

            # --- Assistant messages ---
            if author_role == "assistant":
                # Handle code content_type (code interpreter input)
                if content_type == "code":
                    code_text = content.get("text", "")
                    if not code_text:
                        code_text = "\n".join(
                            str(p) for p in parts if isinstance(p, str) and p.strip()
                        )
                    if code_text.strip():
                        lang = content.get("language", "python")
                        messages.append(
                            {
                                "role": role,
                                "message": f"[SUBACTIVITY][0][EXECUTION] Code interpreter\n```{lang}\n{code_text}\n```",
                                "timestamp": timestamp,
                            }
                        )
                    continue

                # Filter out internal DALL-E system noise from assistant
                text_parts = []
                has_image_ref = False
                for p in parts:
                    if isinstance(p, str):
                        cleaned = p.strip()
                        if not cleaned:
                            continue
                        # Skip internal DALL-E prompt injection text
                        if "do not say or show ANYTHING" in cleaned:
                            continue
                        if cleaned.startswith("Processing image"):
                            continue
                        if (
                            "returned 1 images" in cleaned
                            or "returned 2 images" in cleaned
                        ):
                            continue
                        text_parts.append(cleaned)
                    elif isinstance(p, dict):
                        # Image asset pointer (from multimodal_text)
                        p_type = p.get("content_type", "")
                        if p_type == "image_asset_pointer" or "asset_pointer" in p:
                            has_image_ref = True
                            # Extract DALL-E metadata if present
                            dalle_meta = p.get("metadata", {}).get("dalle", {})
                            prompt = dalle_meta.get("prompt", "")
                            if prompt:
                                messages.append(
                                    {
                                        "role": role,
                                        "message": f"[SUBACTIVITY][0][EXECUTION] Generated image with DALL-E\n**Prompt:** {prompt}",
                                        "timestamp": timestamp,
                                    }
                                )

                text = "\n".join(text_parts) if text_parts else ""

                # Strip citation artifacts
                if text:
                    text = _strip_chatgpt_citations(text)

                # Add citation URLs from metadata if available
                citations = metadata.get("citations", [])
                if citations and text:
                    cite_links = []
                    for cite in citations:
                        cite_meta = cite.get("metadata", {})
                        url = cite_meta.get("url", cite.get("url", ""))
                        cite_title = cite_meta.get("title", "")
                        if url:
                            label = cite_title or url
                            cite_links.append(f"- [{label}]({url})")
                    if cite_links:
                        text += "\n\n**Sources:**\n" + "\n".join(cite_links)

                if text and text.strip():
                    messages.append(
                        {
                            "role": role,
                            "message": text,
                            "timestamp": timestamp,
                        }
                    )
                continue

            # --- User messages ---
            if author_role == "user":
                text_parts = []
                for p in parts:
                    if isinstance(p, str) and p.strip():
                        text_parts.append(p)
                    elif isinstance(p, dict):
                        # User-uploaded image
                        p_type = p.get("content_type", "")
                        if p_type == "image_asset_pointer" or "asset_pointer" in p:
                            img_name = p.get("name", "uploaded image")
                            text_parts.append(f"*[Attached image: {img_name}]*")

                text = "\n".join(text_parts) if text_parts else ""
                if text and text.strip():
                    messages.append(
                        {
                            "role": role,
                            "message": text,
                            "timestamp": timestamp,
                        }
                    )
                continue

        if messages:
            conversations.append({"name": title, "messages": messages})
    return conversations


def _parse_claude_export(data: list, agent_name: str) -> list:
    """
    Parse Claude.ai conversations.json export format into a list of conversations.

    Claude exports have two text sources per message:
    - ``text``: a flattened dump that includes thinking, tool placeholders
      (``This block is not supported on your current device yet.``), and response text.
    - ``content``: a structured array of typed blocks (text, thinking, tool_use,
      tool_result, token_budget).

    We prefer the ``content`` array because it lets us extract only the actual
    response text (``type == "text"``), and we convert thinking / tool_use /
    tool_result blocks into AGiXT ``[SUBACTIVITY]`` messages so they render
    properly in the conversation UI.
    """
    conversations = []
    for conv in data:
        name = conv.get("name") or "Untitled"
        chat_messages = conv.get("chat_messages", [])
        if not chat_messages:
            continue

        messages = []
        for msg in chat_messages:
            sender = msg.get("sender", "")
            content_list = msg.get("content", [])
            created_at = msg.get("created_at")

            if sender == "human":
                role = "USER"
            else:
                role = agent_name

            if role == "USER":
                # For user messages, just extract text
                text = ""
                if content_list and isinstance(content_list, list):
                    text_parts = []
                    for item in content_list:
                        if isinstance(item, dict) and item.get("type") == "text":
                            t = item.get("text", "")
                            if t and t.strip():
                                text_parts.append(t)
                        elif isinstance(item, str) and item.strip():
                            text_parts.append(item)
                    text = "\n\n".join(text_parts)
                if not text or not text.strip():
                    fallback = msg.get("text", "")
                    if fallback and fallback.strip():
                        text = fallback
                if text and text.strip():
                    messages.append(
                        {"role": role, "message": text, "timestamp": created_at}
                    )
                continue

            # --- Assistant message: extract subactivities + response text ---
            subactivities = []
            text_parts = []

            if content_list and isinstance(content_list, list):
                for item in content_list:
                    if not isinstance(item, dict):
                        if isinstance(item, str) and item.strip():
                            text_parts.append(item)
                        continue

                    block_type = item.get("type", "")

                    if block_type == "thinking":
                        thinking_text = item.get("thinking", "")
                        if thinking_text and thinking_text.strip():
                            subactivities.append(
                                {
                                    "role": role,
                                    "message": f"[SUBACTIVITY][0][THINKING] {thinking_text}",
                                    "timestamp": created_at,
                                }
                            )

                    elif block_type == "tool_use":
                        tool_name = item.get("name", "unknown_tool")
                        tool_input = item.get("input", {})
                        if isinstance(tool_input, dict):
                            # Check if this is an artifact (has content/title)
                            artifact_content = tool_input.get("content", "")
                            artifact_title = tool_input.get("title", "")
                            artifact_type = tool_input.get("type", "")
                            if (
                                artifact_content
                                and isinstance(artifact_content, str)
                                and artifact_content.strip()
                            ):
                                lang = ""
                                if artifact_type and "code" in artifact_type:
                                    lang = artifact_type.replace(
                                        "application/vnd.ant.code", ""
                                    ).strip(". ")
                                label = artifact_title or tool_name
                                subactivities.append(
                                    {
                                        "role": role,
                                        "message": f"[SUBACTIVITY][0][EXECUTION] **{label}**\n```{lang}\n{artifact_content}\n```",
                                        "timestamp": created_at,
                                    }
                                )
                            else:
                                # Non-artifact tool use
                                input_summary = (
                                    json.dumps(tool_input, indent=2)
                                    if tool_input
                                    else ""
                                )
                                subactivities.append(
                                    {
                                        "role": role,
                                        "message": f"[SUBACTIVITY][0][EXECUTION] Used tool: {tool_name}\n```json\n{input_summary}\n```",
                                        "timestamp": created_at,
                                    }
                                )

                    elif block_type == "tool_result":
                        result_content = item.get("content", "")
                        if isinstance(result_content, list):
                            parts = []
                            for rc in result_content:
                                if isinstance(rc, dict) and rc.get("type") == "text":
                                    parts.append(rc.get("text", ""))
                            result_content = "\n".join(parts)
                        if result_content and str(result_content).strip():
                            result_text = str(result_content)
                            # Truncate very long tool results
                            if len(result_text) > 2000:
                                result_text = result_text[:2000] + "\n... (truncated)"
                            subactivities.append(
                                {
                                    "role": role,
                                    "message": f"[SUBACTIVITY][0][INFO] {result_text}",
                                    "timestamp": created_at,
                                }
                            )

                    elif block_type == "text":
                        block_text = item.get("text", "")
                        if block_text and block_text.strip():
                            text_parts.append(block_text)

                    # Skip token_budget and other unknown types

            response_text = "\n\n".join(text_parts) if text_parts else ""

            # Fallback to flat text field only if we got nothing from content
            if not response_text.strip() and not subactivities:
                fallback = msg.get("text", "")
                if fallback and fallback.strip():
                    response_text = fallback

            # Emit subactivities before the response text
            messages.extend(subactivities)

            if response_text and response_text.strip():
                messages.append(
                    {"role": role, "message": response_text, "timestamp": created_at}
                )

        if messages:
            conversations.append({"name": name, "messages": messages})
    return conversations


def _copilot_flat_text(node) -> str:
    """Best-effort string extraction from a VS Code MarkdownString-like value."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if isinstance(node.get("value"), str):
            return node["value"]
        if isinstance(node.get("text"), str):
            return node["text"]
    if isinstance(node, list):
        return "".join(_copilot_flat_text(x) for x in node)
    return ""


def _copilot_request_text(message) -> str:
    if isinstance(message, dict):
        if isinstance(message.get("text"), str) and message["text"]:
            return message["text"]
        parts = message.get("parts")
        if isinstance(parts, list):
            return "".join(_copilot_flat_text(p) for p in parts)
    return _copilot_flat_text(message)


def _copilot_uri_path(uri) -> str:
    if isinstance(uri, dict):
        return uri.get("fsPath") or uri.get("path") or uri.get("external") or ""
    if isinstance(uri, str):
        return uri
    return ""


def _parse_copilot_export(data: list, agent_name: str) -> list:
    """
    Parse a VS Code GitHub Copilot Chat export into AGiXT conversations.

    Each entry in *data* is a raw VS Code chat session dict (as written by VS
    Code under ``workspaceStorage/<hash>/chatSessions/<id>.json``) and exposes
    ``requests``, an ordered list of ``{message, response, ...}`` turn objects.

    For every turn we emit a USER message from ``message.text`` (or joined
    ``message.parts``) and an assistant message containing the prose extracted
    from the ``response`` array. Tool invocations and inline file edits in the
    response are emitted as ``[SUBACTIVITY]`` blocks before the assistant text,
    matching the convention used by the Claude importer.
    """
    role_assistant = agent_name
    conversations = []

    def _ms_to_iso(value):
        """VS Code stores timestamps as ms-since-epoch ints. Convert to ISO so the
        downstream importer (which expects strings or datetimes) can parse them."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            try:
                seconds = value / 1000.0 if value > 1e12 else float(value)
                return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
            except Exception:
                return None
        return None

    for sess in data:
        if not isinstance(sess, dict):
            continue
        name = sess.get("customTitle") or sess.get("title") or "Untitled"
        requests = sess.get("requests") or []
        if not isinstance(requests, list) or not requests:
            continue

        sess_created = _ms_to_iso(sess.get("creationDate"))
        sess_updated = _ms_to_iso(sess.get("lastMessageDate"))

        messages = []
        for req in requests:
            if not isinstance(req, dict):
                continue
            ts = _ms_to_iso(req.get("timestamp"))

            # --- USER message ---
            user_text = _copilot_request_text(req.get("message")).strip()
            if user_text:
                messages.append({"role": "USER", "message": user_text, "timestamp": ts})

            # --- Assistant response: split into subactivities + prose ---
            subactivities = []
            text_buf = []

            response_items = req.get("response")
            if isinstance(response_items, list):
                for item in response_items:
                    if isinstance(item, dict):
                        kind = item.get("kind")
                        if kind == "toolInvocationSerialized":
                            tool_id = (
                                item.get("toolId") or item.get("toolName") or "tool"
                            )
                            invocation = _copilot_flat_text(
                                item.get("invocationMessage")
                            )
                            past = _copilot_flat_text(item.get("pastTenseMessage"))
                            lines = [f"Used tool: {tool_id}"]
                            if invocation:
                                lines.append(f"request: {invocation}")
                            if past:
                                lines.append(f"result: {past}")
                            details = item.get("resultDetails")
                            if isinstance(details, list) and details:
                                files = []
                                for d in details:
                                    if isinstance(d, dict):
                                        p = _copilot_uri_path(d.get("uri"))
                                        if p and p not in files:
                                            files.append(p)
                                if files:
                                    lines.append("files:")
                                    for f in files[:25]:
                                        lines.append(f"  - {f}")
                                    if len(files) > 25:
                                        lines.append(
                                            f"  - ... ({len(files) - 25} more)"
                                        )
                            subactivities.append(
                                {
                                    "role": role_assistant,
                                    "message": "[SUBACTIVITY][0][EXECUTION] "
                                    + "\n".join(lines),
                                    "timestamp": ts,
                                }
                            )
                            continue
                        if kind == "prepareToolInvocation":
                            # Skipped: redundant with the matching toolInvocationSerialized
                            continue
                        if kind == "thinking":
                            thinking_text = (
                                _copilot_flat_text(item.get("value"))
                                or item.get("text")
                                or ""
                            )
                            if isinstance(thinking_text, str) and thinking_text.strip():
                                subactivities.append(
                                    {
                                        "role": role_assistant,
                                        "message": f"[SUBACTIVITY][0][THINKING] {thinking_text}",
                                        "timestamp": ts,
                                    }
                                )
                            continue
                        if kind == "progressTaskSerialized":
                            progress_text = _copilot_flat_text(item.get("content"))
                            if progress_text and progress_text.strip():
                                subactivities.append(
                                    {
                                        "role": role_assistant,
                                        "message": f"[SUBACTIVITY][0][INFO] {progress_text}",
                                        "timestamp": ts,
                                    }
                                )
                            continue
                        if kind == "elicitationSerialized":
                            title = _copilot_flat_text(item.get("title"))
                            body = _copilot_flat_text(item.get("message"))
                            chunks = [c for c in (title, body) if c and c.strip()]
                            if chunks:
                                subactivities.append(
                                    {
                                        "role": role_assistant,
                                        "message": "[SUBACTIVITY][0][INFO] "
                                        + "\n".join(chunks),
                                        "timestamp": ts,
                                    }
                                )
                            continue
                        if kind == "mcpServersStarting":
                            continue
                        if kind == "textEditGroup":
                            uri = _copilot_uri_path(item.get("uri"))
                            if uri:
                                subactivities.append(
                                    {
                                        "role": role_assistant,
                                        "message": f"[SUBACTIVITY][0][EXECUTION] Edited file: {uri}",
                                        "timestamp": ts,
                                    }
                                )
                            continue
                        if kind == "inlineReference":
                            ref = item.get("inlineReference")
                            p = (
                                _copilot_uri_path(ref)
                                if isinstance(ref, (dict, str))
                                else ""
                            )
                            if p:
                                from pathlib import Path as _P

                                text_buf.append(f"`{_P(p).name}`")
                            continue
                        if kind in {"undoStop", "codeblockUri"}:
                            continue
                        # MarkdownString-like dict
                        text = _copilot_flat_text(item)
                        if text:
                            text_buf.append(text)
                    else:
                        text = _copilot_flat_text(item)
                        if text:
                            text_buf.append(text)

            response_text = "".join(text_buf).strip()

            messages.extend(subactivities)
            if response_text:
                messages.append(
                    {
                        "role": role_assistant,
                        "message": response_text,
                        "timestamp": ts,
                    }
                )

            result = req.get("result")
            if isinstance(result, dict) and result.get("errorDetails"):
                messages.append(
                    {
                        "role": role_assistant,
                        "message": f"[SUBACTIVITY][0][ERROR] {json.dumps(result['errorDetails'])}",
                        "timestamp": ts,
                    }
                )

        if messages:
            conv_dict = {"name": name, "messages": messages}
            if sess_created:
                conv_dict["created_at"] = sess_created
            if sess_updated:
                conv_dict["updated_at"] = sess_updated
            conversations.append(conv_dict)
    return conversations


def _import_conversations_worker(
    task_id: str,
    conversations_data: list,
    source: str,
    agent_name: str,
    user: str,
):
    """Background worker that imports conversations and updates task status."""
    try:
        if source == "chatgpt":
            parsed = _parse_chatgpt_export(conversations_data, agent_name)
        elif source == "copilot":
            parsed = _parse_copilot_export(conversations_data, agent_name)
        else:
            parsed = _parse_claude_export(conversations_data, agent_name)

        with _import_tasks_lock:
            _import_tasks[task_id]["total_found"] = len(parsed)

        if not parsed:
            with _import_tasks_lock:
                _import_tasks[task_id].update(
                    {
                        "status": "error",
                        "error": "No conversations found in the export file",
                    }
                )
            return

        # Build a set of existing conversation names for dedup
        try:
            c = Conversations(conversation_name="-", user=user)
            all_convs = c.get_conversations()
            prefix = f"[{source.title()}] "
            existing_names = set(name for name in all_convs if name.startswith(prefix))
        except Exception as e:
            logging.warning(
                f"Could not load existing conversation names for dedup: {e}"
            )
            existing_names = set()

        imported_count = 0
        skipped_count = 0
        errors = []

        for i, conv in enumerate(parsed):
            try:
                conv_name = conv["name"]
                messages = conv["messages"]
                if not messages:
                    skipped_count += 1
                    continue

                full_name = f"[{source.title()}] {conv_name}"
                if full_name in existing_names:
                    skipped_count += 1
                    continue

                conversation_content = []
                for msg in messages:
                    conversation_content.append(
                        {
                            "role": msg["role"],
                            "message": msg["message"],
                            "timestamp": msg.get("timestamp"),
                        }
                    )

                c = Conversations(
                    conversation_name=full_name,
                    user=user,
                )
                # Use the single-transaction bulk path for historical imports.
                # This avoids the per-message DB session/commit cycle in
                # log_interaction(), which is the dominant cost for large
                # imports (Copilot conversations frequently contain 100+
                # messages once expanded into USER + SUBACTIVITY entries).
                c.bulk_create_with_messages(
                    conversation_content=conversation_content,
                    created_at=conv.get("created_at"),
                    updated_at=conv.get("updated_at"),
                )

                # Summary generation is intentionally deferred. Calling
                # generate_conversation_summary here issues an LLM request
                # per conversation, which makes bulk historical imports
                # (hundreds-to-thousands of conversations) take hours and
                # block the worker on every iteration. Imported conversations
                # without summaries simply get one generated lazily on first
                # view, which is the same path new conversations follow.

                imported_count += 1
            except Exception as e:
                logging.error(f"Error importing conversation '{conv.get('name')}': {e}")
                errors.append(str(e))
                skipped_count += 1

            # Update progress after every conversation
            with _import_tasks_lock:
                _import_tasks[task_id].update(
                    {
                        "imported": imported_count,
                        "skipped": skipped_count,
                        "processed": i + 1,
                        "errors": errors[:10] if errors else [],
                    }
                )

        # User-knowledge updates from bulk imports are intentionally skipped.
        # The original implementation reloaded summaries for up to 50 imported
        # conversations and fed them all into update_user_knowledge_after_interaction,
        # which is another blocking LLM call with a multi-thousand-token prompt.
        # That made finishing a large import an order of magnitude slower and
        # offered little incremental value vs. the lazy summaries that get
        # generated when a user opens each imported conversation.

        with _import_tasks_lock:
            _import_tasks[task_id].update(
                {
                    "status": "complete",
                    "imported": imported_count,
                    "skipped": skipped_count,
                    "processed": len(parsed),
                    "errors": errors[:10] if errors else [],
                }
            )
    except Exception as e:
        logging.error(f"Import task {task_id} failed: {e}")
        with _import_tasks_lock:
            _import_tasks[task_id].update({"status": "error", "error": str(e)})


def _stream_conversations_from_json_fp(fp) -> list:
    """Parse a JSON array of conversation dicts from a file-like object.

    Uses ``json.load`` (which reads from the file pointer) rather than
    ``json.loads`` on a pre-read bytes blob — this avoids materializing the
    full source as a separate intermediate string, roughly halving peak
    memory on multi-GB uploads.
    """
    try:
        return json.load(fp)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON in conversations.json: {e}",
        )


def _parse_import_file(file_content: bytes) -> list:
    """Parse a zip or JSON file (in-memory bytes) and return the conversations list."""
    conversations_data = None
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            for name in zf.namelist():
                if name.endswith("conversations.json"):
                    with zf.open(name) as f:
                        conversations_data = _stream_conversations_from_json_fp(f)
                    break
    except zipfile.BadZipFile:
        try:
            conversations_data = _stream_conversations_from_json_fp(
                io.BytesIO(file_content)
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="File must be a zip archive or JSON file containing conversations.json",
            )

    if conversations_data is None:
        raise HTTPException(
            status_code=400,
            detail="Could not find conversations.json in the uploaded file",
        )

    if not isinstance(conversations_data, list):
        raise HTTPException(
            status_code=400, detail="conversations.json must contain a JSON array"
        )

    return conversations_data


def _parse_import_path(file_path: str) -> list:
    """Parse a zip or JSON file from disk and return the conversations list.

    Streams via ijson so the parser's working set stays bounded regardless
    of the file's total size. This is what chunked uploads call after the
    last chunk has been written so we never have the assembled file in RAM.
    """
    conversations_data: list | None = None
    try:
        with zipfile.ZipFile(file_path) as zf:
            for name in zf.namelist():
                if name.endswith("conversations.json"):
                    with zf.open(name) as f:
                        conversations_data = _stream_conversations_from_json_fp(f)
                    break
    except zipfile.BadZipFile:
        try:
            with open(file_path, "rb") as f:
                conversations_data = _stream_conversations_from_json_fp(f)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="File must be a zip archive or JSON file containing conversations.json",
            )

    if conversations_data is None:
        raise HTTPException(
            status_code=400,
            detail="Could not find conversations.json in the uploaded file",
        )

    if not isinstance(conversations_data, list):
        raise HTTPException(
            status_code=400, detail="conversations.json must contain a JSON array"
        )

    return conversations_data


def _detect_source(conversations_data: list) -> str:
    """Auto-detect whether conversations data is from ChatGPT, Claude, or VS Code Copilot."""
    sample = (
        conversations_data[:5] if len(conversations_data) >= 5 else conversations_data
    )
    chatgpt_signals = sum(1 for c in sample if isinstance(c, dict) and "mapping" in c)
    claude_signals = sum(
        1 for c in sample if isinstance(c, dict) and "chat_messages" in c
    )
    copilot_signals = sum(
        1
        for c in sample
        if isinstance(c, dict)
        and isinstance(c.get("requests"), list)
        and ("sessionId" in c or "responderUsername" in c)
    )
    counts = {
        "chatgpt": chatgpt_signals,
        "claude": claude_signals,
        "copilot": copilot_signals,
    }
    best = max(counts, key=counts.get)
    if counts[best] > 0:
        return best
    raise HTTPException(
        status_code=400,
        detail="Could not auto-detect export format. The file does not appear to be a ChatGPT, Claude, or VS Code Copilot export.",
    )


def _start_import_task(
    conversations_data: list, source: str, agent_name: str, user: str
) -> dict:
    """Create an import task and start the background worker. Returns the response dict."""
    task_id = str(uuid.uuid4())
    with _import_tasks_lock:
        _import_tasks[task_id] = {
            "status": "processing",
            "source": source,
            "total_found": len(conversations_data),
            "imported": 0,
            "skipped": 0,
            "processed": 0,
            "errors": [],
            "error": None,
            "user": user,
        }

    thread = threading.Thread(
        target=_import_conversations_worker,
        args=(task_id, conversations_data, source, agent_name, user),
        daemon=True,
    )
    thread.start()

    return {
        "task_id": task_id,
        "message": f"Import started for {source.title()} export ({len(conversations_data)} conversations found). Poll /v1/conversation/import/{task_id} for progress.",
        "source": source,
        "total_found": len(conversations_data),
    }


@app.post(
    "/v1/conversation/import/chunk",
    summary="Upload a Chunk for Conversation Import",
    description="Upload a chunk of a large export file. Use this for files over 50MB. After all chunks are uploaded, call POST /v1/conversation/import with the upload_id to start the import.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def upload_import_chunk(
    file: UploadFile = File(...),
    upload_id: str = Form(None),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    agent_name: str = Form(...),
    source: str = Form(None),
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Upload a chunk of a large conversation export file.

    - **file**: A chunk of the export file (max ~50MB per chunk)
    - **upload_id**: ID returned from the first chunk upload. Omit for the first chunk.
    - **chunk_index**: 0-based index of this chunk
    - **total_chunks**: Total number of chunks expected
    - **agent_name**: The agent to associate imported conversations with
    - **source**: Optional. Either 'chatgpt' or 'claude'. Auto-detected if not provided.
    """
    auth = MagicalAuth(token=authorization)

    if source and source not in ("chatgpt", "claude", "copilot"):
        raise HTTPException(
            status_code=400, detail="source must be 'chatgpt', 'claude', or 'copilot'"
        )

    if total_chunks < 1 or chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(
            status_code=400, detail="Invalid chunk_index or total_chunks"
        )

    chunk_data = await file.read()

    # Create upload_id on first chunk
    if not upload_id:
        upload_id = str(uuid.uuid4())

    # Ensure upload directory exists
    os.makedirs(CHUNK_UPLOAD_DIR, exist_ok=True)

    # Validate upload_id is a UUID to prevent path traversal. Reassign to the
    # canonical UUID string form so downstream uses cannot contain any path
    # separators or traversal sequences (sanitizes the user-provided value).
    try:
        upload_id = str(uuid.UUID(str(upload_id)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid upload_id")

    # Save chunk to disk. Build the path and verify it is contained within the
    # upload directory as a defense-in-depth check against path injection.
    upload_root = os.path.realpath(CHUNK_UPLOAD_DIR)
    chunk_filename = f"{upload_id}_chunk_{int(chunk_index)}"
    chunk_path = os.path.realpath(os.path.join(upload_root, chunk_filename))
    if os.path.commonpath([upload_root, chunk_path]) != upload_root:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    with open(chunk_path, "wb") as f:
        f.write(chunk_data)

    # Track the upload
    with _chunked_uploads_lock:
        if upload_id not in _chunked_uploads:
            _chunked_uploads[upload_id] = {
                "total_chunks": total_chunks,
                "received_chunks": set(),
                "agent_name": agent_name,
                "source": source,
                "user": user,
            }
        _chunked_uploads[upload_id]["received_chunks"].add(chunk_index)
        received = len(_chunked_uploads[upload_id]["received_chunks"])

    all_received = received == total_chunks

    if all_received:
        # All chunks received — assemble on disk (never in RAM) and stream-parse.
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f"import_{upload_id}_",
                suffix=".bin",
                delete=False,
                dir=CHUNK_UPLOAD_DIR,
            ) as tmp:
                tmp_path = tmp.name
                for i in range(total_chunks):
                    cp = os.path.realpath(
                        os.path.join(upload_root, f"{upload_id}_chunk_{int(i)}")
                    )
                    if os.path.commonpath([upload_root, cp]) != upload_root:
                        raise HTTPException(
                            status_code=400, detail="Invalid upload path"
                        )
                    with open(cp, "rb") as f:
                        while True:
                            buf = f.read(1024 * 1024)
                            if not buf:
                                break
                            tmp.write(buf)

            conversations_data = _parse_import_path(tmp_path)
            detected_source = source or _detect_source(conversations_data)

            result = _start_import_task(
                conversations_data, detected_source, agent_name, user
            )

            return {
                "upload_id": upload_id,
                "chunk_index": chunk_index,
                "chunks_received": received,
                "total_chunks": total_chunks,
                "complete": True,
                **result,
            }
        finally:
            # Clean up chunk files and the assembled tempfile
            for i in range(total_chunks):
                cp = os.path.realpath(
                    os.path.join(upload_root, f"{upload_id}_chunk_{int(i)}")
                )
                if os.path.commonpath([upload_root, cp]) != upload_root:
                    continue
                try:
                    os.remove(cp)
                except OSError:
                    pass
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            with _chunked_uploads_lock:
                _chunked_uploads.pop(upload_id, None)
    else:
        return {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "chunks_received": received,
            "total_chunks": total_chunks,
            "complete": False,
        }


@app.post(
    "/v1/conversation/import",
    summary="Import Conversations from ChatGPT or Claude",
    description="Upload a ChatGPT or Claude.ai export zip file to import conversations for a specific agent. The source format is auto-detected. Returns a task_id for polling progress. For files over 50MB, use chunked upload via /v1/conversation/import/chunk instead.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def import_conversations(
    file: UploadFile = File(...),
    agent_name: str = Form(...),
    source: str = Form(None),
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Import conversations from a ChatGPT or Claude.ai export.
    The file is uploaded and validated, then import runs in the background.
    Poll GET /v1/conversation/import/{task_id} for progress.

    - **file**: The export zip file or JSON file
    - **agent_name**: The agent to associate imported conversations with
    - **source**: Optional. Either 'chatgpt' or 'claude'. Auto-detected if not provided.
    """
    auth = MagicalAuth(token=authorization)

    if source and source not in ("chatgpt", "claude", "copilot"):
        raise HTTPException(
            status_code=400, detail="source must be 'chatgpt', 'claude', or 'copilot'"
        )

    file_content = await file.read()
    conversations_data = _parse_import_file(file_content)
    detected_source = source or _detect_source(conversations_data)
    return _start_import_task(conversations_data, detected_source, agent_name, user)


@app.get(
    "/v1/conversation/import/{task_id}",
    summary="Get Import Task Status",
    description="Poll the status of an async conversation import task.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_import_status(
    task_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    with _import_tasks_lock:
        task = _import_tasks.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Import task not found")

    if task.get("user") != user:
        raise HTTPException(status_code=404, detail="Import task not found")

    return {
        "task_id": task_id,
        "status": task["status"],
        "source": task["source"],
        "total_found": task["total_found"],
        "imported": task["imported"],
        "skipped": task["skipped"],
        "processed": task["processed"],
        "errors": task["errors"],
        "error": task.get("error"),
    }
