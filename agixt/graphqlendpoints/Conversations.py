from typing import List, Optional
import strawberry
from fastapi import HTTPException
from endpoints.Conversation import (
    get_conversations_list as rest_get_conversations_list,
    get_conversations as rest_get_conversations,
    get_conversation_history as rest_get_conversation_history,
    get_conversation_data as rest_get_conversation_data,
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


# Helper for auth
async def get_user_and_auth_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
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
    name: str
    agent_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    has_notifications: bool
    summary: str
    attachment_count: int


@strawberry.type
class ConversationNotification:
    conversation_id: str
    conversation_name: str
    message_id: str
    message: str
    role: str
    timestamp: datetime


@strawberry.type
class ConversationList:
    conversations: List[str]
    conversations_with_ids: List["ConversationIdentifier"]


@strawberry.type
class ConversationIdentifier:
    id: str
    name: str


@strawberry.type
class ConversationDetail:
    conversations: List["ConversationMetadata"]


@strawberry.type
class ConversationHistory:
    messages: List[ConversationMessage]


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
    conversation_content: List[ConversationMessageInput] = []


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


# Updated Query type
@strawberry.type
class Query:
    @strawberry.field
    async def conversations(self, info) -> ConversationList:
        """Get list of all conversations"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_conversations_list(user=user)

        # Convert dictionary to strongly typed objects
        conversation_identifiers = [
            ConversationIdentifier(id=id, name=name)
            for id, name in result.conversations_with_ids.items()
        ]

        return ConversationList(
            conversations=result.conversations,
            conversations_with_ids=conversation_identifiers,
        )

    @strawberry.field
    async def conversation_details(self, info) -> ConversationDetail:
        """Get detailed conversations list"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_conversations(user=user)

        # Convert dictionary to strongly typed objects
        conversation_metadata = [
            ConversationMetadata(
                name=details["name"],
                agent_id=details["agent_id"],
                created_at=details["created_at"],
                updated_at=details["updated_at"],
                has_notifications=details["has_notifications"],
                summary=details["summary"],
                attachment_count=details["attachment_count"],
            )
            for details in result.conversations.values()
        ]

        return ConversationDetail(conversations=conversation_metadata)

    @strawberry.field
    async def conversation_history_by_name(
        self, info, conversation_name: str, limit: int = 100, page: int = 1
    ) -> ConversationHistory:
        """Get conversation history by name with pagination"""
        user, auth = await get_user_and_auth_from_context(info)
        result = await rest_get_conversation_data(
            conversation_name=conversation_name,
            limit=limit,
            page=page,
            user=user,
            authorization=auth,
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
            for msg in result.conversation_history
        ]

        return ConversationHistory(messages=messages)

    @strawberry.field
    async def conversation_history(
        self, info, conversation_id: str
    ) -> ConversationHistory:
        """Get conversation history by ID"""
        user, auth = await get_user_and_auth_from_context(info)
        result = await rest_get_conversation_history(
            conversation_id=conversation_id, user=user, authorization=auth
        )

        # Convert dictionary to strongly typed objects
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

    @strawberry.field
    async def notifications(self, info) -> NotificationList:
        """Get user notifications"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_notifications(user=user)

        # Convert dictionary to strongly typed objects
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

        return NotificationList(notifications=notifications)


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
    async def log_interaction(
        self, info, input: LogInteractionInput
    ) -> MutationResponse:
        """Log a conversation interaction"""
        user, auth = await get_user_and_auth_from_context(info)
        model = LogInteraction(**input.__dict__)
        result = await rest_log_interaction(
            log_interaction=model, user=user, authorization=auth
        )
        return MutationResponse(success=True, message=result.message)

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


schema = strawberry.Schema(query=Query, mutation=Mutation)
