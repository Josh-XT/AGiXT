from typing import List, Dict, Any, Optional
import strawberry
from fastapi import Depends, HTTPException, Header
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
    NotificationResponse,
    MessageIdResponse,
)
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
from MagicalAuth import MagicalAuth


# Convert Pydantic models to Strawberry types
@strawberry.experimental.pydantic.type(model=ConversationListResponse)
class ConversationList:
    conversations: List[str]
    conversations_with_ids: Dict[str, str]


@strawberry.experimental.pydantic.type(model=ConversationHistoryResponse)
class ConversationHistory:
    conversation_history: List[Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=ConversationDetailResponse)
class ConversationDetail:
    conversations: Dict[str, Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=NotificationResponse)
class Notifications:
    notifications: List[Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=ResponseMessage)
class Response:
    message: str


@strawberry.experimental.pydantic.type(model=MessageIdResponse)
class MessageId:
    message: str


# Input types
@strawberry.input
class ConversationHistoryInput:
    conversation_name: str
    agent_name: Optional[str] = ""
    conversation_content: List[Dict[str, Any]] = strawberry.field(default_factory=list)


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
class Query:
    @strawberry.field
    async def conversations(self, info) -> ConversationList:
        """Get list of all conversations"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_conversations_list(user=user)
        return ConversationList.from_pydantic(result)

    @strawberry.field
    async def conversation_details(self, info) -> ConversationDetail:
        """Get detailed conversations list"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_conversations(user=user)
        return ConversationDetail.from_pydantic(result)

    @strawberry.field
    async def conversation_history_by_id(
        self, info, conversation_id: str
    ) -> ConversationHistory:
        """Get conversation history by ID"""
        user, auth = await get_user_and_auth_from_context(info)
        result = await rest_get_conversation_history(
            conversation_id=conversation_id, user=user, authorization=auth
        )
        return ConversationHistory.from_pydantic(result)

    @strawberry.field
    async def conversation_history(
        self, info, conversation_name: str, limit: int = 100, page: int = 1
    ) -> ConversationHistory:
        """Get conversation history with pagination"""
        user, auth = await get_user_and_auth_from_context(info)
        result = await rest_get_conversation_data(
            conversation_name=conversation_name,
            limit=limit,
            page=page,
            user=user,
            authorization=auth,
        )
        return ConversationHistory.from_pydantic(result)

    @strawberry.field
    async def notifications(self, info) -> Notifications:
        """Get user notifications"""
        user = await verify_api_key(info.context["request"])
        result = await rest_get_notifications(user=user)
        return Notifications.from_pydantic(result)


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
        return ConversationHistory.from_pydantic(result)

    @strawberry.mutation
    async def delete_conversation(
        self, info, input: ConversationHistoryInput
    ) -> Response:
        """Delete a conversation"""
        user, auth = await get_user_and_auth_from_context(info)
        model = ConversationHistoryModel(**input.__dict__)
        result = await rest_delete_conversation(
            history=model, user=user, authorization=auth
        )
        return Response.from_pydantic(result)

    @strawberry.mutation
    async def log_interaction(self, info, input: LogInteractionInput) -> MessageId:
        """Log a conversation interaction"""
        user, auth = await get_user_and_auth_from_context(info)
        model = LogInteraction(**input.__dict__)
        result = await rest_log_interaction(
            log_interaction=model, user=user, authorization=auth
        )
        return MessageId.from_pydantic(result)

    @strawberry.mutation
    async def update_message(self, info, input: UpdateMessageInput) -> Response:
        """Update a conversation message"""
        user, auth = await get_user_and_auth_from_context(info)
        model = UpdateConversationHistoryMessageModel(**input.__dict__)
        result = await rest_update_message(history=model, user=user, authorization=auth)
        return Response.from_pydantic(result)

    @strawberry.mutation
    async def update_message_by_id(
        self, info, message_id: str, input: MessageByIdInput
    ) -> Response:
        """Update a message by its ID"""
        user = await verify_api_key(info.context["request"])
        model = UpdateMessageModel(**input.__dict__)
        result = await rest_update_by_id(
            message_id=message_id, history=model, user=user
        )
        return Response.from_pydantic(result)

    @strawberry.mutation
    async def delete_message_by_id(
        self, info, message_id: str, conversation_name: str
    ) -> Response:
        """Delete a message by its ID"""
        user = await verify_api_key(info.context["request"])
        model = DeleteMessageModel(conversation_name=conversation_name)
        result = await rest_delete_by_id(
            message_id=message_id, history=model, user=user
        )
        return Response.from_pydantic(result)

    @strawberry.mutation
    async def fork_conversation(self, info, input: ConversationForkInput) -> Response:
        """Fork a conversation"""
        user = await verify_api_key(info.context["request"])
        model = ConversationFork(**input.__dict__)
        result = await rest_fork_conversation(fork=model, user=user)
        return Response.from_pydantic(result)

    @strawberry.mutation
    async def rename_conversation(
        self,
        info,
        agent_name: str,
        conversation_name: str,
        new_conversation_name: str = "-",
    ) -> Dict[str, str]:
        """Rename a conversation"""
        user, auth = await get_user_and_auth_from_context(info)
        model = RenameConversationModel(
            agent_name=agent_name,
            conversation_name=conversation_name,
            new_conversation_name=new_conversation_name,
        )
        return await rest_rename_conversation(
            rename=model, user=user, authorization=auth
        )

    @strawberry.mutation
    async def generate_message_tts(
        self, info, conversation_id: str, message_id: str
    ) -> Dict[str, str]:
        """Generate text-to-speech for a message"""
        user, auth = await get_user_and_auth_from_context(info)
        return await rest_get_tts(
            conversation_id=conversation_id,
            message_id=message_id,
            user=user,
            authorization=auth,
        )


# Create the schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
