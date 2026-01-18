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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
from ApiClient import verify_api_key, get_api_client, Agent
from Conversations import (
    Conversations,
    get_conversation_name_by_id,
    get_conversation_id_by_name,
    get_conversation_name_by_message_id,
)
from DB import Message, Agent as DBAgent, User
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
)
import json
import uuid
import asyncio
import logging
import os
import threading
from datetime import datetime
from MagicalAuth import MagicalAuth, get_user_id
from WorkerRegistry import worker_registry
from Workspaces import WorkspaceManager
import mimetypes
from typing import Set

app = APIRouter()
workspace_manager = WorkspaceManager()


# Redis pub/sub channel for cross-worker WebSocket broadcasts
REDIS_BROADCAST_CHANNEL = "agixt:ws:broadcast"


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
        # Maps conversation_id -> set of message IDs that were broadcasted (to avoid duplicate sends via polling)
        self.broadcasted_message_ids: Dict[str, Set[str]] = {}
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
                self.broadcasted_message_ids[conversation_id] = set()
            self.active_connections[conversation_id].add(websocket)
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
                    # Clean up broadcasted IDs when no more connections
                    if conversation_id in self.broadcasted_message_ids:
                        del self.broadcasted_message_ids[conversation_id]
                logging.debug(
                    f"Conversation {conversation_id}: WebSocket disconnected."
                )

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
            # Track broadcasted message IDs
            message_id = message_data.get("id")
            if message_id and conversation_id in self.broadcasted_message_ids:
                self.broadcasted_message_ids[conversation_id].add(str(message_id))

        sent_count = 0
        for connection in connections:
            try:
                await connection.send_text(
                    json.dumps(
                        {
                            "type": event_type,
                            "data": message_data,  # Already serialized from Redis
                        }
                    )
                )
                sent_count += 1
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
            # Track broadcasted message IDs to prevent duplicate sends via polling
            message_id = message_data.get("id")
            if message_id and conversation_id in self.broadcasted_message_ids:
                self.broadcasted_message_ids[conversation_id].add(str(message_id))
            logging.debug(
                f"broadcast_message_event: found {len(connections)} connections"
            )

        sent_count = 0
        for connection in connections:
            try:
                await connection.send_text(
                    json.dumps(
                        {
                            "type": event_type,
                            "data": make_json_serializable(message_data),
                        }
                    )
                )
                sent_count += 1
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

    def was_broadcasted(self, conversation_id: str, message_id: str) -> bool:
        """Check if a message was already sent via broadcast (to avoid duplicate polling sends)."""
        if conversation_id not in self.broadcasted_message_ids:
            return False
        return str(message_id) in self.broadcasted_message_ids[conversation_id]

    def clear_broadcasted_ids(self, conversation_id: str):
        """Clear the broadcasted IDs for a conversation (call after processing poll cycle)."""
        if conversation_id in self.broadcasted_message_ids:
            self.broadcasted_message_ids[conversation_id].clear()

    def has_listeners(self, conversation_id: str) -> bool:
        """Check if a conversation has active WebSocket listeners."""
        return (
            conversation_id in self.active_connections
            and len(self.active_connections[conversation_id]) > 0
        )


# Global conversation message broadcaster instance
conversation_message_broadcaster = ConversationMessageBroadcaster()


class UserNotificationManager:
    """
    Manages WebSocket connections for user-level notifications.
    Allows broadcasting events to all connections for a specific user.
    """

    def __init__(self):
        # Maps user_id -> set of active WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str):
        """Register a new WebSocket connection for a user."""
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
        """Broadcast a message to all connections for a specific user."""
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
    """Convert datetime objects and other non-serializable objects to JSON-serializable formats"""
    if isinstance(obj, datetime):
        return obj.isoformat()
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

    conversation = Conversations(conversation_name=conversation_name, user=user)
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
    conversations = c.get_conversations()
    if conversations is None:
        conversations = []
    conversations_with_ids = c.get_conversations_with_ids()
    return {
        "conversations": conversations,
        "conversations_with_ids": conversations_with_ids,
    }


@app.get(
    "/v1/conversations",
    response_model=ConversationDetailResponse,
    summary="Get Detailed Conversations List",
    description="Retrieves a detailed list of conversations including metadata such as creation date, update date, and notification status.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    conversations = c.get_conversations_with_detail()
    if not conversations:
        conversations = {}
    # Output: {"conversations": { "conversation_id": { "name": "conversation_name", "created_at": "datetime", "updated_at": "datetime" } } }
    return {
        "conversations": conversations,
    }


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
):
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    conversation_history = Conversations(
        conversation_name=conversation_name, user=user
    ).get_conversation()
    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


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
    asyncio.create_task(
        notify_user_conversation_created(
            user_id=auth.user_id,
            conversation_id=conversation_id,
            conversation_name=history.conversation_name,
            agent_id=(
                str(c.get_agent_id(auth.user_id))
                if c.get_agent_id(auth.user_id)
                else None
            ),
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
    Conversations(conversation_name=conversation_name, user=user).delete_conversation()

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
        conversation_name=old_conversation_name, user=user
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
    interaction_id = Conversations(
        conversation_name=conversation_name, user=user
    ).log_interaction(
        message=log_interaction.message,
        role=log_interaction.role,
    )

    # Notify user of new message via websocket
    asyncio.create_task(
        notify_user_message_added(
            user_id=auth.user_id,
            conversation_id=conversation_id,
            conversation_name=conversation_name,
            message_id=str(interaction_id),
            message=log_interaction.message,
            role=log_interaction.role,
        )
    )

    return ResponseMessage(message=str(interaction_id))


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
    Conversations(conversation_name=conversation_name, user=user).update_message_by_id(
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
    Conversations(conversation_name=conversation_name, user=user).delete_message_by_id(
        message_id=message_id,
    )
    return ResponseMessage(message="Message deleted.")


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
        conversation_name=history.conversation_name, user=user
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
        conversation_name=conversation_name, user=user
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
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    Conversations(
        conversation_name=history.conversation_name, user=user
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
        response = await agixt.inference(
            user_input=f"Rename conversation",
            prompt_name="Name Conversation",
            conversation_list="\n".join(conversation_list),
            conversation_results=10,
            websearch=False,
            browse_links=False,
            voice_response=False,
            log_user_input=False,
            log_output=False,
        )
        if "```json" not in response and "```" in response:
            response = response.replace("```", "```json", 1)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        try:
            response = json.loads(response)
            new_name = response["suggested_conversation_name"]
            if new_name in conversation_list:
                # Do not use {new_name}!
                response = await agixt.inference(
                    user_input=f"**Do not use {new_name}!**",
                    prompt_name="Name Conversation",
                    conversation_list="\n".join(conversation_list),
                    conversation_results=10,
                    websearch=False,
                    browse_links=False,
                    voice_response=False,
                    log_user_input=False,
                    log_output=False,
                )
                if "```json" not in response and "```" in response:
                    response = response.replace("```", "```json", 1)
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                response = json.loads(response)
                new_name = response["suggested_conversation_name"]
                if new_name in conversation_list:
                    new_name = datetime.now().strftime(
                        "Conversation Created %Y-%m-%d %I:%M %p"
                    )
        except:
            new_name = datetime.now().strftime("Conversation Created %Y-%m-%d %I:%M %p")
        rename.new_conversation_name = new_name.replace("_", " ")
    if "#" in rename.new_conversation_name:
        rename.new_conversation_name = str(rename.new_conversation_name).replace(
            "#", ""
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
        conversation_name=conversation_name, user=user
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
        conversation_name=conversation_name, user=user
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
    c = Conversations(conversation_name=conversation_name, user=user)
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
        c = Conversations(conversation_name=conversation_name, user=user)
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
        try:
            initial_history = c.get_conversation()

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
                    json.dumps({"type": "initial_data", "data": serializable_messages})
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

        # Main streaming loop
        while True:
            try:
                # Use wait_for with a timeout to check for incoming messages
                # Increased to 0.5s to reduce CPU usage while still being responsive
                try:
                    message_data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=0.5
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
                        logging.debug(
                            f"WebSocket: Skipping duplicate new message {message_id}"
                        )
                        continue
                    # Skip if this was already sent via broadcast
                    if message_id and conversation_message_broadcaster.was_broadcasted(
                        conversation_id, message_id
                    ):
                        logging.debug(
                            f"WebSocket: Skipping broadcasted new message {message_id}"
                        )
                        if message_id:
                            previous_message_ids.add(message_id)
                        continue
                    serializable_message = make_json_serializable(message)
                    logging.debug(f"WebSocket: Sending message_added for {message_id}")
                    await websocket.send_text(
                        json.dumps(
                            {"type": "message_added", "data": serializable_message}
                        )
                    )
                    # Track new message ID
                    if message_id:
                        previous_message_ids.add(message_id)
                        # Also track that we just sent this as "added" - don't send as "updated" too
                        updated_message_ids_this_cycle.add(message_id)

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
                    if message_id and conversation_message_broadcaster.was_broadcasted(
                        conversation_id, message_id
                    ):
                        logging.debug(
                            f"WebSocket: Skipping broadcasted updated message {message_id}"
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
                            }
                        )
                    )

                # Reset per-cycle tracking and clear broadcasted IDs
                updated_message_ids_this_cycle.clear()
                conversation_message_broadcaster.clear_broadcasted_ids(conversation_id)

                # Check for conversation rename
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
    # Truncate message for notification (keep first 100 chars)
    preview = message[:100] + "..." if len(message) > 100 else message
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
        c = Conversations(conversation_name=conversation_name, user=user)
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
                default_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if default_user:
                    default_user_id = str(default_user.id)

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
        from DB import User

        default_user_obj = (
            session.query(User).filter(User.email == DEFAULT_USER).first()
        )
        if not default_user_obj:
            raise HTTPException(status_code=500, detail="Default user not found")

        default_user_id = str(default_user_obj.id)

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
        from DB import User

        default_user_obj = (
            session.query(User).filter(User.email == DEFAULT_USER).first()
        )
        if not default_user_obj:
            raise HTTPException(status_code=500, detail="Default user not found")

        default_user_id = str(default_user_obj.id)

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
