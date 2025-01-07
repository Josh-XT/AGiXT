from typing import List, Optional
import strawberry
from fastapi import HTTPException
from endpoints.Conversation import (
    get_conversations as rest_get_conversations,
    get_conversation_history as rest_get_conversation_history,
    new_conversation_history as rest_new_conversation,
    delete_conversation_history as rest_delete_conversation,
    delete_history_message as rest_delete_message,
    update_history_message as rest_update_message,
    update_by_id as rest_update_by_id,
    delete_by_id as rest_delete_by_id,
    log_interaction as rest_log_interaction,
    rename_conversation as rest_rename_conversation,
    fork_conversation as rest_fork_conversation,
    get_tts as rest_get_tts,
    get_notifications as rest_get_notifications,
)
from ApiClient import verify_api_key
from datetime import datetime
from typing import AsyncGenerator

try:
    from broadcaster import Broadcast
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "broadcaster"])
    from broadcaster import Broadcast
from contextlib import asynccontextmanager


# Helper for auth
async def get_user_and_auth_from_context(info):
    request = info.context["request"]
    try:
        user = verify_api_key(request)
        auth = request.headers.get("authorization")
        return user, auth
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class DeleteMessageModel:
    conversation_name: str


@strawberry.type
class UpdateMessageModel:
    conversation_name: str
    message_id: str
    new_message: str


@strawberry.type
class UpdateConversationHistoryMessageModel:
    agent_name: Optional[str] = ""
    conversation_name: str
    message: str
    new_message: str


@strawberry.type
class LogInteraction:
    role: str
    message: str
    conversation_name: Optional[str] = ""


@strawberry.type
class ConversationFork:
    conversation_name: str
    message_id: str


@strawberry.type
class RenameConversationModel:
    agent_name: str
    conversation_name: str
    new_conversation_name: Optional[str] = "-"


@strawberry.type
class ConversationHistoryMessageModel:
    agent_name: Optional[str] = ""
    conversation_name: str
    message: str


@strawberry.type
class ConversationMessage:
    id: str
    role: str
    message: str
    timestamp: datetime
    updated_at: datetime
    updated_by: Optional[str]
    feedback_received: bool


@strawberry.type
class ConversationHistoryModel:
    agent_name: Optional[str] = ""
    conversation_name: str
    conversation_content: List["ConversationMessageInput"]


@strawberry.type
class ConversationMetadata:
    id: str
    name: str
    agent_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    has_notifications: bool
    summary: str
    attachment_count: int


@strawberry.type
class ConversationIdentifier:
    id: str
    name: str


@strawberry.type
class ConversationList:
    conversations: List["ConversationIdentifier"]


@strawberry.type
class ConversationHistory:
    messages: List[ConversationMessage]


@strawberry.type
class ConversationNotification:
    conversation_id: str
    conversation_name: str
    message_id: str
    message: str
    role: str
    timestamp: datetime


@strawberry.type
class NotificationList:
    notifications: List[ConversationNotification]


# Input types for mutations
@strawberry.input
class ConversationHistoryMessageInput:
    conversation_name: str
    agent_name: Optional[str] = ""
    message: str


@strawberry.input
class ConversationMessageInput:
    role: str
    message: str
    timestamp: Optional[datetime] = None


@strawberry.input
class ConversationHistoryInput:
    conversation_name: str
    agent_name: Optional[str] = ""
    conversation_content: Optional[List[ConversationMessageInput]]


@strawberry.input
class LogInteractionInput:
    role: str
    message: str
    conversation_name: Optional[str] = ""


@strawberry.input
class UpdateMessageInput:
    conversation_name: str
    message: str
    new_message: str


@strawberry.input
class MessageByIdInput:
    conversation_name: str
    new_message: str


@strawberry.input
class ConversationForkInput:
    conversation_name: str
    message_id: str


# Pagination Input
@strawberry.input
class PaginationInput:
    page: int = 1
    limit: int = 100


# Pagination Info
@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    total_pages: int
    total_items: int
    current_page: int
    items_per_page: int


@strawberry.type
class ConversationDetail:
    metadata: ConversationMetadata
    messages: List[ConversationMessage]


@strawberry.type
class ConversationConnection:
    page_info: PageInfo
    edges: List[ConversationMetadata]


@strawberry.type
class NotificationConnection:
    page_info: PageInfo
    edges: List["ConversationNotification"]


@strawberry.type
class MessageEvent:
    conversation_id: str
    message: ConversationMessage


@strawberry.type
class ConversationEvent:
    conversation: ConversationMetadata


@strawberry.type
class NotificationEvent:
    notification: ConversationNotification


# Initialize broadcaster for pub/sub
broadcast = Broadcast("memory://")


@asynccontextmanager
async def get_broadcaster():
    await broadcast.connect()
    try:
        yield broadcast
    finally:
        await broadcast.disconnect()


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def message_added(
        self, info, conversation_id: str
    ) -> AsyncGenerator[MessageEvent, None]:
        """Subscribe to new messages in a specific conversation"""
        user = await verify_api_key(info.context["request"])

        async with get_broadcaster() as broadcaster:
            async with broadcaster.subscribe(
                channel=f"messages_{conversation_id}"
            ) as subscriber:
                async for event in subscriber:
                    yield MessageEvent(
                        conversation_id=conversation_id, message=event.message
                    )

    @strawberry.subscription
    async def conversation_updated(
        self, info
    ) -> AsyncGenerator[ConversationEvent, None]:
        """Subscribe to conversation updates (creation, deletion, renaming)"""
        user = await verify_api_key(info.context["request"])

        async with get_broadcaster() as broadcaster:
            async with broadcaster.subscribe(
                channel=f"conversations_{user}"
            ) as subscriber:
                async for event in subscriber:
                    yield ConversationEvent(conversation=event.conversation)

    @strawberry.subscription
    async def notification_received(
        self, info
    ) -> AsyncGenerator[NotificationEvent, None]:
        """Subscribe to new notifications"""
        user = await verify_api_key(info.context["request"])

        async with get_broadcaster() as broadcaster:
            async with broadcaster.subscribe(
                channel=f"notifications_{user}"
            ) as subscriber:
                async for event in subscriber:
                    yield NotificationEvent(notification=event.notification)


# Query type with pagination
@strawberry.type
class Query:
    @strawberry.field
    async def conversations(
        self, info, pagination: Optional[PaginationInput] = None
    ) -> ConversationConnection:
        """Get paginated list of conversations with details"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_conversations(user=user)

        # Convert dictionary to list and sort by updated_at
        conversations = [
            ConversationMetadata(
                id=id,
                name=details["name"],
                agent_id=details["agent_id"],
                created_at=details["created_at"],
                updated_at=details["updated_at"],
                has_notifications=details["has_notifications"],
                summary=details["summary"],
                attachment_count=details["attachment_count"],
            )
            for id, details in result.conversations.items()
        ]
        conversations.sort(key=lambda x: x.updated_at, reverse=True)

        # Handle pagination
        page = pagination.page if pagination else 1
        limit = pagination.limit if pagination else 100
        total_items = len(conversations)
        total_pages = -(-total_items // limit)  # Ceiling division
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit

        page_info = PageInfo(
            has_next_page=end_idx < total_items,
            has_previous_page=page > 1,
            total_pages=total_pages,
            total_items=total_items,
            current_page=page,
            items_per_page=limit,
        )

        return ConversationConnection(
            page_info=page_info, edges=conversations[start_idx:end_idx]
        )

    @strawberry.field
    async def conversation(
        self, info, conversation_id: str, pagination: Optional[PaginationInput] = None
    ) -> ConversationDetail:
        """Get conversation details and paginated messages"""
        user, auth = await get_user_and_auth_from_context(info)

        # Get conversation metadata
        result = await rest_get_conversations(user=user)
        if conversation_id not in result.conversations:
            raise Exception(f"Conversation {conversation_id} not found")

        details = result.conversations[conversation_id]
        metadata = ConversationMetadata(
            id=conversation_id,
            name=details["name"],
            agent_id=details["agent_id"],
            created_at=details["created_at"],
            updated_at=details["updated_at"],
            has_notifications=details["has_notifications"],
            summary=details["summary"],
            attachment_count=details["attachment_count"],
        )

        # Get messages with pagination
        history_result = await rest_get_conversation_history(
            conversation_id=conversation_id, user=user, authorization=auth
        )

        messages = [
            ConversationMessage(
                id=msg["id"],
                role=msg["role"],
                message=msg["message"],
                timestamp=msg["timestamp"],
                updated_at=msg["updated_at"],
                updated_by=msg["updated_by"],
                feedback_received=msg["feedback_received"],
            )
            for msg in history_result.conversation_history
        ]

        # Apply pagination if provided
        if pagination:
            start_idx = (pagination.page - 1) * pagination.limit
            end_idx = start_idx + pagination.limit
            messages = messages[start_idx:end_idx]

        return ConversationDetail(metadata=metadata, messages=messages)

    @strawberry.field
    async def notifications(
        self, info, pagination: Optional[PaginationInput] = None
    ) -> NotificationConnection:
        """Get paginated notifications"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_notifications(user=user)

        notifications = [
            ConversationNotification(
                conversation_id=notif["conversation_id"],
                conversation_name=notif["conversation_name"],
                message_id=notif["message_id"],
                message=notif["message"],
                role=notif["role"],
                timestamp=notif["timestamp"],
            )
            for notif in result.notifications
        ]

        # Handle pagination
        page = pagination.page if pagination else 1
        limit = pagination.limit if pagination else 100
        total_items = len(notifications)
        total_pages = -(-total_items // limit)  # Ceiling division
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit

        page_info = PageInfo(
            has_next_page=end_idx < total_items,
            has_previous_page=page > 1,
            total_pages=total_pages,
            total_items=total_items,
            current_page=page,
            items_per_page=limit,
        )

        return NotificationConnection(
            page_info=page_info, edges=notifications[start_idx:end_idx]
        )


# Response types for mutations
@strawberry.type
class MutationResponse:
    success: bool
    message: str


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_conversation(
        self, info, input: ConversationHistoryInput
    ) -> ConversationHistory:
        """Create a new conversation"""
        user = await verify_api_key(info.context["request"])
        model = ConversationHistoryModel(**input.__dict__)
        result = await rest_new_conversation(history=model, user=user)

        messages = [
            ConversationMessage(
                id=msg["id"],
                role=msg["role"],
                message=msg["message"],
                timestamp=msg["timestamp"],
                updated_at=msg["updated_at"],
                updated_by=msg["updated_by"],
                feedback_received=msg["feedback_received"],
            )
            for msg in result.conversation_history
        ]

        return ConversationHistory(messages=messages)

    @strawberry.mutation
    async def delete_conversation(
        self, info, input: ConversationHistoryInput
    ) -> MutationResponse:
        """Delete a conversation"""
        user, auth = await get_user_and_auth_from_context(info)
        model = ConversationHistoryModel(**input.__dict__)
        result = await rest_delete_conversation(
            history=model, user=user, authorization=auth
        )
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def rename_conversation(
        self,
        info,
        agent_name: str,
        conversation_name: str,
        new_conversation_name: str = "-",
    ) -> MutationResponse:
        """Rename a conversation"""
        user, auth = await get_user_and_auth_from_context(info)
        model = RenameConversationModel(
            agent_name=agent_name,
            conversation_name=conversation_name,
            new_conversation_name=new_conversation_name,
        )
        result = await rest_rename_conversation(
            rename=model, user=user, authorization=auth
        )
        return MutationResponse(
            success=True,
            message=f"Conversation renamed to {result['conversation_name']}",
        )

    @strawberry.mutation
    async def update_message(self, info, input: UpdateMessageInput) -> MutationResponse:
        """Update a conversation message"""
        user, auth = await get_user_and_auth_from_context(info)
        model = UpdateConversationHistoryMessageModel(**input.__dict__)
        result = await rest_update_message(history=model, user=user, authorization=auth)
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def update_message_by_id(
        self, info, message_id: str, input: MessageByIdInput
    ) -> MutationResponse:
        """Update a message by its ID"""
        user = await verify_api_key(info.context["request"])
        model = UpdateMessageModel(**input.__dict__)
        result = await rest_update_by_id(
            message_id=message_id, history=model, user=user
        )
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def delete_message(
        self, info, input: ConversationHistoryMessageInput
    ) -> MutationResponse:
        """Delete a message by its content"""
        user = await verify_api_key(info.context["request"])
        model = ConversationHistoryMessageModel(**input.__dict__)
        result = await rest_delete_message(history=model, user=user)
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def delete_message_by_id(
        self, info, message_id: str, conversation_name: str
    ) -> MutationResponse:
        """Delete a message by its ID"""
        user = await verify_api_key(info.context["request"])
        model = DeleteMessageModel(conversation_name=conversation_name)
        result = await rest_delete_by_id(
            message_id=message_id, history=model, user=user
        )
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def fork_conversation(
        self, info, input: ConversationForkInput
    ) -> MutationResponse:
        """Fork a conversation"""
        user = await verify_api_key(info.context["request"])
        model = ConversationFork(**input.__dict__)
        result = await rest_fork_conversation(fork=model, user=user)
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def generate_message_tts(
        self, info, conversation_id: str, message_id: str
    ) -> MutationResponse:
        """Generate text-to-speech for a message"""
        user, auth = await get_user_and_auth_from_context(info)
        result = await rest_get_tts(
            conversation_id=conversation_id,
            message_id=message_id,
            user=user,
            authorization=auth,
        )
        return MutationResponse(success=True, message=result["message"])

    @strawberry.mutation
    async def log_interaction(
        self, info, input: LogInteractionInput
    ) -> MutationResponse:
        """Log a conversation interaction"""
        user, auth = await get_user_and_auth_from_context(info)
        model = LogInteraction(**input.__dict__)
        result = await rest_log_interaction(
            log_interaction=model, user=user, authorization=auth
        )

        # Create message event
        message = ConversationMessage(
            id=result.message,
            role=input.role,
            message=input.message,
            timestamp=datetime.now(),
            updated_at=datetime.now(),
            updated_by=None,
            feedback_received=False,
        )

        # Broadcast the new message
        async with get_broadcaster() as broadcaster:
            await broadcaster.publish(
                channel=f"messages_{input.conversation_name}",
                message=MessageEvent(
                    conversation_id=input.conversation_name, message=message
                ),
            )

            # If this is a notification, broadcast it as well
            if not input.message.startswith("[ACTIVITY]"):
                notification = ConversationNotification(
                    conversation_id=input.conversation_name,
                    conversation_name=input.conversation_name,
                    message_id=result.message,
                    message=input.message,
                    role=input.role,
                    timestamp=datetime.now(),
                )
                await broadcaster.publish(
                    channel=f"notifications_{user}",
                    message=NotificationEvent(notification=notification),
                )

        return MutationResponse(success=True, message=result.message)


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
