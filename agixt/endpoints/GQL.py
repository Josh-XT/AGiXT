from typing import List, Optional, Dict
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
from Providers import get_providers_with_details
from Prompts import Prompts
from Websearch import Websearch
from ApiClient import verify_api_key, is_admin
from datetime import datetime
from typing import AsyncGenerator
from XT import AGiXT
from Agent import (
    Agent,
    get_agents,
    add_agent,
    delete_agent,
    rename_agent,
)
from Conversations import get_conversation_name_by_id
from MagicalAuth import MagicalAuth
from Models import ChatCompletions
from Globals import getenv, get_default_agent, get_agixt_training_urls
import uuid


try:
    from broadcaster import Broadcast
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "broadcaster"])
    from broadcaster import Broadcast
from contextlib import asynccontextmanager


# Helper for auth
async def get_user_from_context(info):
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


@strawberry.type
class ProviderSetting:
    name: str
    value: Optional[str]


@strawberry.type
class ProviderDetail:
    name: str
    friendly_name: str
    description: str
    services: List[str]
    settings: List[ProviderSetting]


@strawberry.type
class Providers:
    providers: List[ProviderDetail]


@strawberry.type
class PromptArgument:
    name: str


@strawberry.type
class PromptType:
    name: str
    content: str
    category: str
    description: str
    arguments: List[PromptArgument]


@strawberry.type
class PromptCategory:
    name: str
    description: str


@strawberry.type
class PromptResponse:
    success: bool
    message: str


# Input types
@strawberry.input
class CreatePromptInput:
    name: str
    content: str
    category: str = "Default"
    description: str = ""


@strawberry.input
class UpdatePromptInput:
    name: str
    content: str
    category: str = "Default"
    description: str = ""


@strawberry.input
class RenamePromptInput:
    old_name: str
    new_name: str
    category: str = "Default"


@strawberry.type
class AgentSetting:
    name: str
    value: str


@strawberry.type
class AgentCommand:
    name: str
    enabled: bool


@strawberry.type
class AgentType:
    id: str
    name: str
    status: bool
    company_id: Optional[str]
    settings: List[AgentSetting]
    commands: List[AgentCommand]


@strawberry.type
class ProviderDetail:
    name: str
    connected: bool
    friendly_name: str
    description: str
    settings: List[AgentSetting]


@strawberry.type
class AgentResponse:
    success: bool
    message: str


@strawberry.type
class AgentPromptResponse:
    response: str


# Input types
@strawberry.input
class AgentSettingInput:
    name: str
    value: str


@strawberry.input
class AgentCommandInput:
    name: str
    enabled: bool


@strawberry.input
class CreateAgentInput:
    name: str
    settings: List[AgentSettingInput]
    commands: List[AgentCommandInput]
    training_urls: Optional[List[str]] = None


@strawberry.input
class UpdateAgentSettingsInput:
    settings: List[AgentSettingInput]


@strawberry.input
class UpdateAgentCommandsInput:
    commands: List[AgentCommandInput]


@strawberry.input
class PromptArgInput:
    conversation_name: Optional[str] = None
    user_input: Optional[str] = None
    log_user_input: Optional[bool] = False
    log_output: Optional[bool] = False
    tts: Optional[bool] = False
    context_results: Optional[int] = None
    conversation_results: Optional[int] = 10
    file_urls: Optional[List[str]] = None
    prompt_category: Optional[str] = "Default"


@strawberry.input
class AgentPromptInput:
    prompt_name: str
    prompt_args: PromptArgInput


@strawberry.input
class TaskPlanInput:
    user_input: str
    websearch: bool = False
    websearch_depth: int = 3
    conversation_name: str = "AGiXT Task Planning"
    log_user_input: bool = True
    log_output: bool = True
    enable_new_command: bool = True


def convert_settings_to_type(settings_dict: Dict[str, str]) -> List[ProviderSetting]:
    """Convert settings dictionary to list of ProviderSetting objects"""
    return [
        ProviderSetting(name=key, value=str(value))
        for key, value in settings_dict.items()
    ]


def convert_provider_details(details: Dict[str, str]) -> ProviderDetail:
    """Convert provider details dictionary to ProviderDetail object"""
    return ProviderDetail(
        name=details["name"],
        friendly_name=details.get("friendly_name", details["name"]),
        description=details["description"],
        services=details["services"],
        settings=convert_settings_to_type(details["settings"]),
    )


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
        user, auth = await get_user_from_context(info)

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

    @strawberry.field
    async def providers(self, info) -> Providers:
        """Get comprehensive provider details"""
        user = await get_user_from_context(info)
        provider_details = get_providers_with_details()
        providers = [
            convert_provider_details({"name": name, **details})
            for name, details in provider_details.items()
        ]
        return Providers(providers=providers)

    @strawberry.field
    async def prompt(self, info, name: str, category: str = "Default") -> PromptType:
        """Get a specific prompt by name and category"""
        user = await verify_api_key(info.context["request"])
        prompt_manager = Prompts(user=user)

        content = prompt_manager.get_prompt(prompt_name=name, prompt_category=category)
        if not content:
            raise Exception(f"Prompt {name} not found in category {category}")

        arguments = [
            PromptArgument(name=arg) for arg in prompt_manager.get_prompt_args(content)
        ]

        return PromptType(
            name=name,
            content=content,
            category=category,
            description="",  # Could be enhanced to store/retrieve descriptions
            arguments=arguments,
        )

    @strawberry.field
    async def prompts(self, info, category: str = "Default") -> List[str]:
        """Get all prompts in a category"""
        user = await verify_api_key(info.context["request"])
        prompt_manager = Prompts(user=user)
        return prompt_manager.get_prompts(prompt_category=category)

    @strawberry.field
    async def prompt_categories(self, info) -> List[str]:
        """Get all prompt categories"""
        user = await verify_api_key(info.context["request"])
        prompt_manager = Prompts(user=user)
        return prompt_manager.get_prompt_categories()

    @strawberry.field
    async def agents(self, info) -> List[AgentType]:
        """Get all available agents"""
        user, auth = await get_user_from_context(info)
        agents = get_agents(user=user)

        # Handle auto-creation of default agent if needed
        create_agent = str(getenv("CREATE_AGENT_ON_REGISTER")).lower() == "true"
        if create_agent:
            agent_list = [agent["name"] for agent in agents]
            agent_name = getenv("AGIXT_AGENT")
            if agent_name not in agent_list:
                agent_config = get_default_agent()
                agent_settings = agent_config["settings"]
                agent_commands = agent_config["commands"]
                create_agixt_agent = str(getenv("CREATE_AGIXT_AGENT")).lower() == "true"
                training_urls = (
                    get_agixt_training_urls()
                    if create_agixt_agent and agent_name == "AGiXT"
                    else agent_config["training_urls"]
                )

                add_agent(
                    agent_name=agent_name,
                    provider_settings=agent_settings,
                    commands=agent_commands,
                    user=user,
                )
                agents = get_agents(user=user)  # Refresh agent list

        return [
            AgentType(
                id=agent["id"],
                name=agent["name"],
                status=agent["status"],
                company_id=agent.get("company_id"),
                settings=[],  # These would need to be populated if needed
                commands=[],  # These would need to be populated if needed
            )
            for agent in agents
        ]

    @strawberry.field
    async def agent(self, info, name: str) -> AgentType:
        """Get a specific agent's configuration"""
        user, auth = await get_user_from_context(info)
        if not await is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(agent_name=name, user=user)
        config = agent.get_agent_config()

        settings = [
            AgentSetting(
                name=k,
                value=(
                    "HIDDEN"
                    if any(
                        x in k.upper() for x in ["KEY", "SECRET", "PASSWORD", "TOKEN"]
                    )
                    else v
                ),
            )
            for k, v in config["settings"].items()
        ]

        commands = [
            AgentCommand(name=k, enabled=v) for k, v in config["commands"].items()
        ]

        return AgentType(
            id=agent.agent_id,
            name=name,
            status=False,  # This could be updated if there's a status to track
            company_id=config["settings"].get("company_id"),
            settings=settings,
            commands=commands,
        )

    @strawberry.field
    async def agent_providers(self, info, agent_name: str) -> List[ProviderDetail]:
        """Get providers available to an agent"""
        user, auth = await get_user_from_context(info)
        agent = Agent(agent_name=agent_name, user=user)
        agent_settings = agent.AGENT_CONFIG["settings"]
        providers = get_providers_with_details()

        provider_details = []
        for provider in providers:
            provider_name = list(provider.keys())[0]
            details = list(provider.values())[0]
            provider_settings = details["settings"]

            # Check if provider is connected
            connected = any(
                key in agent_settings and agent_settings[key] != ""
                for key in provider_settings
            )

            provider_details.append(
                ProviderDetail(
                    name=provider_name,
                    connected=connected,
                    friendly_name=details.get("friendly_name", provider_name),
                    description=details["description"],
                    settings=[
                        AgentSetting(name=k, value=v)
                        for k, v in provider_settings.items()
                    ],
                )
            )

        return provider_details


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
        user, auth = await get_user_from_context(info)
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
        user, auth = await get_user_from_context(info)
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
        user, auth = await get_user_from_context(info)
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
        user, auth = await get_user_from_context(info)
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
        user, auth = await get_user_from_context(info)
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

    @strawberry.mutation
    async def create_prompt(self, info, input: CreatePromptInput) -> PromptResponse:
        """Create a new prompt"""
        user, auth = await get_user_from_context(info)
        try:
            prompt_manager = Prompts(user=user)
            prompt_manager.add_prompt(
                prompt_name=input.name,
                prompt=input.content,
                prompt_category=input.category,
            )
            return PromptResponse(
                success=True, message=f"Prompt '{input.name}' created successfully"
            )
        except Exception as e:
            return PromptResponse(success=False, message=str(e))

    @strawberry.mutation
    async def update_prompt(self, info, input: UpdatePromptInput) -> PromptResponse:
        """Update an existing prompt"""
        user, auth = await get_user_from_context(info)
        try:
            prompt_manager = Prompts(user=user)
            prompt_manager.update_prompt(
                prompt_name=input.name,
                prompt=input.content,
                prompt_category=input.category,
            )
            return PromptResponse(
                success=True, message=f"Prompt '{input.name}' updated successfully"
            )
        except Exception as e:
            return PromptResponse(success=False, message=str(e))

    @strawberry.mutation
    async def delete_prompt(
        self, info, name: str, category: str = "Default"
    ) -> PromptResponse:
        """Delete a prompt"""
        user, auth = await get_user_from_context(info)
        try:
            prompt_manager = Prompts(user=user)
            prompt_manager.delete_prompt(prompt_name=name, prompt_category=category)
            return PromptResponse(
                success=True, message=f"Prompt '{name}' deleted successfully"
            )
        except Exception as e:
            return PromptResponse(success=False, message=str(e))

    @strawberry.mutation
    async def rename_prompt(self, info, input: RenamePromptInput) -> PromptResponse:
        """Rename a prompt"""
        user, auth = await get_user_from_context(info)
        try:
            prompt_manager = Prompts(user=user)
            prompt_manager.rename_prompt(
                prompt_name=input.old_name,
                new_prompt_name=input.new_name,
                prompt_category=input.category,
            )
            return PromptResponse(
                success=True,
                message=f"Prompt '{input.old_name}' renamed to '{input.new_name}' successfully",
            )
        except Exception as e:
            return PromptResponse(success=False, message=str(e))

    @strawberry.mutation
    async def create_agent(self, info, input: CreateAgentInput) -> AgentResponse:
        """Create a new agent"""
        user, auth = await get_user_from_context(info)
        if not await is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        settings = {s.name: s.value for s in input.settings}
        commands = {c.name: c.enabled for c in input.commands}

        result = add_agent(
            agent_name=input.name,
            provider_settings=settings,
            commands=commands,
            user=user,
        )

        if input.training_urls:
            agent = Agent(agent_name=input.name, user=user)
            reader = Websearch(collection_number="0", agent=agent, user=user)
            for url in input.training_urls:
                await reader.get_web_content(url=url)
            message = "Agent created and trained successfully"
        else:
            message = "Agent created successfully"

        return AgentResponse(success=True, message=message)

    @strawberry.mutation
    async def update_agent_settings(
        self, info, agent_name: str, input: UpdateAgentSettingsInput
    ) -> AgentResponse:
        """Update an agent's settings"""
        user, auth = await get_user_from_context(info)
        if not await is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(agent_name=agent_name, user=user)
        settings = {s.name: s.value for s in input.settings}

        # Filter out HIDDEN values to not overwrite sensitive data
        new_settings = {k: v for k, v in settings.items() if v != "HIDDEN"}

        result = agent.update_agent_config(
            new_config=new_settings, config_key="settings"
        )

        return AgentResponse(success=True, message=result)

    @strawberry.mutation
    async def update_agent_commands(
        self, info, agent_name: str, input: UpdateAgentCommandsInput
    ) -> AgentResponse:
        """Update an agent's commands"""
        user, auth = await get_user_from_context(info)
        if not await is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(agent_name=agent_name, user=user)
        commands = {c.name: c.enabled for c in input.commands}

        result = agent.update_agent_config(new_config=commands, config_key="commands")

        return AgentResponse(success=True, message=result)

    @strawberry.mutation
    async def delete_agent(self, info, name: str) -> AgentResponse:
        """Delete an agent"""
        user, auth = await get_user_from_context(info)
        if not await is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(agent_name=name, user=user)
        websearch = Websearch(collection_number="0", agent=agent, user=user)
        await websearch.agent_memory.wipe_memory()

        result = delete_agent(agent_name=name, user=user)
        return AgentResponse(success=True, message=f"Agent {name} deleted successfully")

    @strawberry.mutation
    async def rename_agent(self, info, old_name: str, new_name: str) -> AgentResponse:
        """Rename an agent"""
        user, auth = await get_user_from_context(info)
        if not await is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        result = rename_agent(agent_name=old_name, new_name=new_name, user=user)
        return AgentResponse(
            success=True, message=f"Agent renamed from {old_name} to {new_name}"
        )

    @strawberry.mutation
    async def prompt_agent(
        self, info, agent_name: str, input: AgentPromptInput
    ) -> AgentPromptResponse:
        """Send a prompt to an agent"""
        user, auth = await get_user_from_context(info)

        conversation_name = input.prompt_args.conversation_name or None
        if conversation_name != "-":
            try:
                conversation_id = str(uuid.UUID(conversation_name))
                if conversation_id:
                    auth = MagicalAuth(token=auth)
                    conversation_name = get_conversation_name_by_id(
                        conversation_id=conversation_id, user_id=auth.user_id
                    )
            except:
                pass

        agent = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=conversation_name,
        )

        # Convert input to messages format
        messages = []
        if input.prompt_args.file_urls:
            content = [{"type": "text", "text": input.prompt_args.user_input or ""}]
            for url in input.prompt_args.file_urls:
                content.append({"type": "file_url", "file_url": {"url": url}})
            messages.append(
                {
                    "role": "user",
                    "content": content,
                    **{
                        k: v
                        for k, v in input.prompt_args.__dict__.items()
                        if k not in ["user_input", "file_urls"]
                    },
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": input.prompt_args.user_input or "",
                    **{
                        k: v
                        for k, v in input.prompt_args.__dict__.items()
                        if k != "user_input"
                    },
                }
            )

        response = await agent.chat_completions(
            prompt=ChatCompletions(
                model=agent_name, user=conversation_name, messages=messages
            )
        )

        return AgentPromptResponse(
            response=response["choices"][0]["message"]["content"]
        )

    @strawberry.mutation
    async def plan_task(
        self, info, agent_name: str, input: TaskPlanInput
    ) -> AgentPromptResponse:
        """Plan a task for the agent"""
        user, auth = await get_user_from_context(info)

        agent = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=input.conversation_name,
        )

        result = await agent.plan_task(
            user_input=input.user_input,
            websearch=input.websearch,
            websearch_depth=input.websearch_depth,
            log_user_input=input.log_user_input,
            log_output=input.log_output,
            enable_new_command=input.enable_new_command,
        )

        return AgentPromptResponse(response=result)


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
