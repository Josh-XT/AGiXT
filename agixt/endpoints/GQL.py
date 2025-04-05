from MagicalAuth import MagicalAuth, impersonate_user, verify_api_key, is_admin
from Conversations import Conversations, get_conversation_name_by_id
from Providers import get_providers_with_details
from contextlib import asynccontextmanager
from typing import List, Optional, Dict
from Models import ChatCompletions
from fastapi import HTTPException
from typing import AsyncGenerator
from broadcaster import Broadcast
from Extensions import Extensions
from Websearch import Websearch
from Memories import Memories
from datetime import datetime
from Prompts import Prompts
from Globals import getenv
from Chain import Chain
from XT import AGiXT
from Agent import (
    Agent,
    get_agents,
    add_agent,
    delete_agent,
    rename_agent,
)
import strawberry
import asyncio
import logging
import base64
import json
import uuid
import os

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


async def get_user_from_context(info):
    request = info.context["request"]
    try:
        # Try regular HTTP header first
        auth = request.headers.get("authorization")

        # For WebSocket connections, try connection params
        if not auth and "connection_params" in info.context:
            params = info.context["connection_params"]
            # Try nested connectionParams first
            if (
                "connectionParams" in params
                and "authorization" in params["connectionParams"]
            ):
                auth = params["connectionParams"]["authorization"]
            # Try direct authorization
            elif "authorization" in params:
                auth = params["authorization"]

        # Try cookies as last resort
        if not auth and hasattr(request, "cookies"):
            auth = request.cookies.get("jwt")

        if not auth:
            raise HTTPException(status_code=401, detail="No authorization header found")

        # Add "Bearer" prefix if it's missing
        if auth and not auth.startswith("Bearer "):
            auth = f"Bearer {auth}"

        user_data = verify_api_key(auth)
        magical = MagicalAuth(token=auth)
        user = magical.email
        return user, auth, magical
    except HTTPException as e:
        logging.error(f"Auth error: {str(e.detail)}")
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
    summary: Optional[str]
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
    default: bool
    company_id: Optional[str]
    settings: List[AgentSetting]
    commands: List[AgentCommand]


@strawberry.type
class ProviderDetails:
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


@strawberry.type
class MemoryMetadata:
    external_source_name: str
    id: str
    description: str
    additional_metadata: str
    timestamp: str


@strawberry.type
class Memory:
    key: str
    text: str
    embedding: List[float]
    relevance_score: Optional[float] = None
    external_source_name: str
    description: str
    timestamp: str
    additional_metadata: str
    id: str


@strawberry.type
class MemoryCollection:
    collection_name: str
    memories: List[Memory]


@strawberry.type
class DatasetConfig:
    model_name: Optional[str] = "unsloth/mistral-7b-v0.2"
    max_seq_length: Optional[int] = 16384
    huggingface_output_path: Optional[str] = "JoshXT/finetuned-mistral-7b-v0.2"
    private_repo: Optional[bool] = True


@strawberry.type
class DPOResult:
    prompt: str
    chosen: str
    rejected: str


# Input types
@strawberry.input
class MemoryQueryInput:
    user_input: str
    limit: int = 5
    min_relevance_score: float = 0.0


@strawberry.input
class TextMemoryInput:
    user_input: str
    text: str
    collection_number: str = "0"


@strawberry.input
class FileMemoryInput:
    file_name: str
    file_content: str
    collection_number: str = "0"
    company_id: Optional[str] = None


@strawberry.input
class UrlMemoryInput:
    url: str
    collection_number: str = "0"


@strawberry.input
class FeedbackInput:
    user_input: str
    message: str
    feedback: str
    positive: bool = True
    conversation_name: Optional[str] = ""


@strawberry.input
class DatasetInput:
    batch_size: int = 5


@strawberry.input
class FineTuneInput:
    model: Optional[str] = "unsloth/mistral-7b-v0.2"
    max_seq_length: Optional[int] = 16384
    huggingface_output_path: Optional[str] = "JoshXT/finetuned-mistral-7b-v0.2"
    private_repo: Optional[bool] = True


@strawberry.input
class DPOInput:
    user_input: str
    injected_memories: Optional[int] = 100


@strawberry.type
class ExtensionCommandArgs:
    required: List[str]
    optional: List[str]
    description: str


@strawberry.type
class ExtensionCommand:
    friendly_name: str
    description: str
    command_args: ExtensionCommandArgs
    extension_name: str


@strawberry.type
class Extension:
    extension_name: str
    description: str
    settings: List[str]
    commands: List[ExtensionCommand]
    missing_keys: Optional[List[str]] = None


@strawberry.type
class ExtensionSetting:
    name: str
    value: str


@strawberry.type
class CommandResult:
    response: str


@strawberry.type
class CommandArgValue:
    """Represents a single command argument value"""

    value: str


@strawberry.input
class CommandArgValueInput:
    """Input type for command argument values"""

    value: str


@strawberry.type
class CommandArgs:
    """Represents the arguments for a command"""

    args: List["CommandArg"]


@strawberry.type
class CommandArg:
    """Represents a single command argument with name and value"""

    name: str
    value: CommandArgValue


@strawberry.input
class CommandArgInput:
    """Input type for a single command argument"""

    name: str
    value: CommandArgValueInput


@strawberry.input
class CommandArgsInput:
    """Input type for command arguments"""

    args: List[CommandArgInput]


@strawberry.type
class ExtensionCommandArg:
    """Represents a single extension command argument"""

    name: str
    description: str
    required: bool
    type: str
    default: Optional[str] = None


@strawberry.type
class ProviderConfig:
    """Represents provider configuration"""

    settings: List["ProviderSetting"]


@strawberry.type
class ProviderSetting:
    """Represents a single provider setting"""

    name: str
    value: str
    description: Optional[str] = None
    required: bool = False
    type: str = "string"


@strawberry.input
class ProviderSettingInput:
    """Input type for provider settings"""

    name: str
    value: str
    description: Optional[str] = None
    required: bool = False
    type: str = "string"


@strawberry.input
class CommandExecutionInput:
    """Input type for executing commands with proper typing"""

    command_name: str
    command_args: List[CommandArgInput]
    conversation_name: Optional[str] = None


@strawberry.input
class CommandArgInput:
    """Input type for a single command argument"""

    name: str
    value: str


@strawberry.input
class ExtensionSettingInput:
    name: str
    value: str


@strawberry.type
class MemoryExportCollection:
    """Represents a collection of memories for export/import"""

    collection_id: str
    memories: List["MemoryExportEntry"]


@strawberry.type
class MemoryExportEntry:
    """Represents a single memory entry for export/import"""

    external_source_name: str
    description: str
    text: str
    timestamp: str


@strawberry.input
class MemoryImportCollection:
    """Input type for importing a collection of memories"""

    collection_id: str
    memories: List["MemoryImportEntry"]


@strawberry.input
class MemoryImportEntry:
    """Input type for importing a single memory entry"""

    external_source_name: str
    description: str
    text: str
    timestamp: Optional[str] = None


import json
from typing import Dict, Any


@strawberry.scalar(
    name="JSONObject",
    description="A JSON object that can contain any valid JSON data",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)
class JSONObject:
    @staticmethod
    def serialize(value: Dict[str, Any]) -> Dict[str, Any]:
        return value

    @staticmethod
    def parse_literal(node) -> Dict[str, Any]:
        if isinstance(node, dict):
            return node
        return json.loads(node)


@strawberry.type
class ChainStep:
    """Represents a step in a chain"""

    step: int
    agent_name: str
    prompt_type: str
    target_name: str
    prompt: JSONObject


class ChainDetails:
    """Represents a chain's full details"""

    id: str
    name: str
    description: Optional[str]
    steps: List[ChainStep]
    created_at: datetime
    updated_at: datetime
    user_id: str


@strawberry.type
class ChainRunStep:
    """Represents the result of running a chain step"""

    step_number: int
    content: str
    timestamp: datetime


@strawberry.type
class ChainRun:
    """Represents a complete chain execution"""

    id: str
    steps: List[ChainRunStep]
    timestamp: datetime


@strawberry.type
class DetailedChain:
    """Complete chain details"""

    id: str
    chain_name: str
    description: Optional[str]
    steps: List[ChainStep]


def convert_chain_to_detailed(chain_data: dict) -> DetailedChain:
    """Helper to convert chain data to DetailedChain type"""
    steps = []
    chain_steps = chain_data.get("steps", [])

    for step_dict in chain_steps:
        prompt_type = step_dict.get("prompt_type", "").lower()
        # Ensure prompt_content is always a dictionary, even if empty or None in source
        prompt_content = step_dict.get("prompt", {})
        if not isinstance(prompt_content, dict):
            logging.warning(
                f"Step prompt is not a dictionary: {prompt_content}. Setting to empty dict."
            )
            prompt_content = {}  # Default to empty dict if invalid

        target_name = ""
        prompt_args = {}

        # Extract the name and separate arguments
        if prompt_type == "prompt":
            target_name = prompt_content.get("prompt_name", "")
            prompt_args = {
                k: v
                for k, v in prompt_content.items()
                if k not in ["prompt_name", "prompt_category"]
            }
        elif prompt_type == "command":
            target_name = prompt_content.get("command_name", "")
            prompt_args = {
                k: v for k, v in prompt_content.items() if k != "command_name"
            }
        elif prompt_type == "chain":
            target_name = prompt_content.get("chain_name", "") or prompt_content.get(
                "chain", ""
            )
            prompt_args = {
                k: v
                for k, v in prompt_content.items()
                if k not in ["chain_name", "chain"]
            }
        else:  # Fallback or Unknown type
            # Attempt to stringify if it's not a dict, otherwise treat as args
            if not isinstance(prompt_content, dict):
                target_name = str(prompt_content)
                prompt_args = {}
            else:
                target_name = ""  # No specific name key found
                prompt_args = prompt_content  # Treat the whole dict as args

        # Ensure prompt_args is always a valid dictionary for JSONObject
        if not isinstance(prompt_args, dict):
            logging.warning(
                f"Final prompt_args is not a dictionary: {prompt_args}. Setting to empty dict."
            )
            prompt_args = {}

        new_step = ChainStep(
            step=step_dict.get("step", 0),
            agent_name=step_dict.get("agent_name", ""),
            prompt_type=step_dict.get("prompt_type", ""),
            target_name=target_name,
            prompt=prompt_args,
        )
        steps.append(new_step)

    # **** Explicitly retrieve and log the name before assignment ****
    retrieved_id = str(chain_data.get("id", ""))
    retrieved_name = chain_data.get("name", "")  # Use .get() directly on the dict
    retrieved_description = chain_data.get("description")
    # **** End Explicit Retrieval ****

    result = DetailedChain(
        id=retrieved_id,
        chain_name=retrieved_name,  # Assign the explicitly retrieved name
        description=retrieved_description,
        steps=steps,
    )
    return result


@strawberry.type
class ChainConfig:
    """Represents a chain's complete configuration"""

    id: str
    chain_name: str
    description: Optional[str]
    steps: List[ChainStep]


@strawberry.type
class ChainStepResponse:
    """Represents a response from a chain step execution"""

    step_number: int
    content: str
    timestamp: datetime


@strawberry.type
class ChainRunResponse:
    """Represents the output of a chain run"""

    chain_run_id: str
    steps: List[ChainStepResponse]


@strawberry.type
class ChainDependency:
    """Represents dependencies between chain steps"""

    step_number: str
    dependencies: List[int]


# Input types
@strawberry.input
class ChainPromptInput:
    """Input for chain step prompt configuration"""

    prompt_name: Optional[str] = None
    command_name: Optional[str] = None
    chain_name: Optional[str] = None
    prompt_category: Optional[str] = "Default"


@strawberry.input
class ChainStepInput:
    """Input for creating/updating a chain step"""

    step_number: int
    agent_name: str
    prompt_type: str
    prompt: ChainPromptInput


@strawberry.input
class ChainInput:
    """Input for creating a new chain"""

    chain_name: str
    steps: Optional[List[ChainStepInput]] = None


@strawberry.input
class ChainArgumentValue:
    """Represents a single argument value that can be a string, int, float, or bool"""

    string_value: Optional[str] = None
    int_value: Optional[int] = None
    float_value: Optional[float] = None
    bool_value: Optional[bool] = None


@strawberry.input
class ChainArgument:
    """A single chain argument with name and value"""

    name: str
    value: ChainArgumentValue


@strawberry.input
class ChainArguments:
    """Collection of chain arguments"""

    args: List[ChainArgument]


@strawberry.input
class RunChainInput:
    """Input for running a chain"""

    prompt: str
    agent_override: Optional[str] = None
    all_responses: bool = False
    from_step: int = 1
    chain_args: Optional[ChainArguments] = None
    conversation_name: Optional[str] = None


@strawberry.input
class RunChainStepInput:
    """Input for running a specific chain step"""

    prompt: str
    agent_override: Optional[str] = None
    chain_args: Optional[ChainArguments] = None
    chain_run_id: Optional[str] = None
    conversation_name: Optional[str] = None


def convert_chain_args_to_dict(chain_args: Optional[ChainArguments]) -> dict:
    """Helper function to convert ChainArguments to a dictionary for backwards compatibility"""
    if not chain_args:
        return {}

    result = {}
    for arg in chain_args.args:
        # Get the first non-None value from the ChainArgumentValue
        if arg.value.string_value is not None:
            result[arg.name] = arg.value.string_value
        elif arg.value.int_value is not None:
            result[arg.name] = arg.value.int_value
        elif arg.value.float_value is not None:
            result[arg.name] = arg.value.float_value
        elif arg.value.bool_value is not None:
            result[arg.name] = arg.value.bool_value

    return result


@strawberry.input
class MoveStepInput:
    """Input for moving a step within a chain"""

    old_step_number: int
    new_step_number: int


@strawberry.type
class UserPreference:
    """A single user preference setting"""

    key: str
    value: str


@strawberry.input
class UserPreferenceInput:
    """Input for updating a user preference"""

    key: str
    value: str


@strawberry.type
class MissingRequirement:
    """Represents a missing requirement for a user"""

    requirement_name: str
    requirement_value: str


@strawberry.type
class UserPreferences:
    """Collection of all user preferences"""

    timezone: Optional[str] = None
    input_tokens: Optional[int] = 0
    output_tokens: Optional[int] = 0
    phone_number: Optional[str] = ""
    stripe_id: Optional[str] = None
    missing_requirements: Optional[List[MissingRequirement]] = None
    custom_preferences: Optional[List[UserPreference]] = None


# Update UserDetail to use UserPreferences
@strawberry.type
class UserDetail:
    """Core user information"""

    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    companies: List["CompanyInfo"]
    preferences: UserPreferences  # Replace dict with structured type


@strawberry.type
class CompanyInfo:
    """Basic company information"""

    id: str
    name: str
    company_id: Optional[str]
    agents: List["AgentInfo"]
    role_id: Optional[int]
    primary: bool


@strawberry.type
class AgentInfo:
    """Agent information within a company"""

    name: str
    id: str
    status: bool
    default: bool
    company_id: Optional[str]


@strawberry.type
class InvitationInfo:
    """Invitation details"""

    id: str
    email: str
    company_id: str
    role_id: int
    inviter_id: str
    created_at: datetime
    is_accepted: bool


@strawberry.type
class AuthResponse:
    """Response for auth operations"""

    success: bool
    message: str
    token: Optional[str] = None
    otp_uri: Optional[str] = None
    magic_link: Optional[str] = None
    email: Optional[str] = None


@strawberry.type
class RegistrationResponse:
    """Response for registration"""

    success: bool
    message: str
    otp_uri: Optional[str] = None
    magic_link: Optional[str] = None
    mfa_token: Optional[str] = None


@strawberry.type
class SSOProviderInfo:
    """Information about an SSO provider"""

    name: str
    connected: bool
    account_name: Optional[str]


# Input types
@strawberry.input
class RegisterInput:
    """Input for user registration"""

    email: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    invitation_id: Optional[str] = None


@strawberry.input
class LoginInput:
    """Input for login attempts"""

    email: str
    token: str


@strawberry.input
class UserPreferenceUpdateInput:
    """Input for updating a single preference"""

    key: str
    value: str


@strawberry.input
class UserUpdateInput:
    """Input for updating user information"""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    preferences: Optional[List[UserPreferenceUpdateInput]] = None
    phone_number: Optional[str] = None
    timezone: Optional[str] = None


def convert_user_update_to_dict(input: UserUpdateInput) -> dict:
    """Convert UserUpdateInput to dictionary for backend compatibility"""
    result = {}

    if input.first_name is not None:
        result["first_name"] = input.first_name
    if input.last_name is not None:
        result["last_name"] = input.last_name
    if input.phone_number is not None:
        result["phone_number"] = input.phone_number
    if input.timezone is not None:
        result["timezone"] = input.timezone
    if input.preferences:
        for pref in input.preferences:
            result[pref.key] = pref.value

    return result


@strawberry.input
class LoginParamsInput:
    """Additional login parameters"""

    referrer: Optional[str] = None
    invitation_id: Optional[str] = None


@strawberry.input
class MFAVerificationInput:
    """Input for MFA verification"""

    code: str
    email: Optional[str] = None


@strawberry.input
class EmailVerificationInput:
    """Input for email verification"""

    email: str
    code: Optional[str] = None


@strawberry.input
class InvitationCreateInput:
    """Input for creating invitations"""

    email: str
    company_id: Optional[str] = None
    role_id: int


@strawberry.input
class CompanyCreateInput:
    """Input for creating a company"""

    name: str
    parent_company_id: Optional[str] = None
    agent_name: Optional[str] = "AGiXT"


@strawberry.input
class CompanyUpdateInput:
    """Input for updating a company"""

    name: str


def convert_preferences_to_type(pref_dict: dict) -> UserPreferences:
    """Convert preference dictionary to UserPreferences type"""
    custom_prefs = []
    missing_reqs = []

    # Handle known preferences
    timezone = pref_dict.get("timezone")
    input_tokens = int(pref_dict.get("input_tokens", 0))
    output_tokens = int(pref_dict.get("output_tokens", 0))
    phone_number = pref_dict.get("phone_number", "")
    stripe_id = pref_dict.get("stripe_id")

    # Handle missing requirements
    if "missing_requirements" in pref_dict:
        for req in pref_dict["missing_requirements"]:
            for key, value in req.items():
                missing_reqs.append(
                    MissingRequirement(
                        requirement_name=key, requirement_value=str(value)
                    )
                )

    # Handle any other custom preferences
    known_keys = {
        "timezone",
        "input_tokens",
        "output_tokens",
        "phone_number",
        "stripe_id",
        "missing_requirements",
        "email",
        "first_name",
        "last_name",
    }

    for key, value in pref_dict.items():
        if key not in known_keys:
            custom_prefs.append(UserPreference(key=key, value=str(value)))

    return UserPreferences(
        timezone=timezone,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        phone_number=phone_number,
        stripe_id=stripe_id,
        missing_requirements=missing_reqs if missing_reqs else None,
        custom_preferences=custom_prefs if custom_prefs else None,
    )


def convert_preferences_to_dict(prefs: UserPreferences) -> dict:
    """Convert UserPreferences type back to dictionary"""
    result = {}

    if prefs.timezone:
        result["timezone"] = prefs.timezone
    if prefs.input_tokens is not None:
        result["input_tokens"] = prefs.input_tokens
    if prefs.output_tokens is not None:
        result["output_tokens"] = prefs.output_tokens
    if prefs.phone_number:
        result["phone_number"] = prefs.phone_number
    if prefs.stripe_id:
        result["stripe_id"] = prefs.stripe_id

    if prefs.missing_requirements:
        result["missing_requirements"] = [
            {req.requirement_name: req.requirement_value}
            for req in prefs.missing_requirements
        ]

    if prefs.custom_preferences:
        for pref in prefs.custom_preferences:
            result[pref.key] = pref.value

    return result


def convert_extension(ext: dict) -> Extension:
    """Helper to convert raw extension data to Extension type"""
    return Extension(
        extension_name=ext.get("extension_name", ""),
        description=ext.get("description", ""),
        settings=ext.get("settings", []),
        commands=[convert_extension_command(cmd) for cmd in ext.get("commands", [])],
        missing_keys=ext.get("missing_keys", []),
    )


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


def convert_extension_command(raw_command: dict) -> ExtensionCommand:
    command_args = ExtensionCommandArgs(
        required=raw_command.get("command_args", {}).get("required", []),
        optional=raw_command.get("command_args", {}).get("optional", []),
        description=raw_command.get("command_args", {}).get("description", ""),
    )

    return ExtensionCommand(
        friendly_name=raw_command.get("friendly_name", ""),
        description=raw_command.get("description", ""),
        command_args=command_args,
        extension_name=raw_command.get("extension_name", ""),
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
class AppState:
    """Represents the complete application state"""

    user: UserDetail
    conversations: ConversationConnection
    current_conversation: Optional[ConversationDetail] = None
    notifications: Optional[List[ConversationNotification]] = None


@strawberry.type
class AppStateEvent:
    """Event type for app state updates"""

    state: AppState


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def app_state(
        self,
        info,
        conversation_id: Optional[str] = None,
        pagination: Optional[PaginationInput] = None,
    ) -> AsyncGenerator[AppStateEvent, None]:
        """
        Subscribe to app state updates including user details, conversations list,
        and optionally a specific conversation's details.
        """
        try:
            # Initialize auth manager with provided token
            user, auth, auth_manager = await get_user_from_context(info)

            async def get_app_state():
                # Get user details
                user_data = auth_manager.login(
                    ip_address=info.context["request"].client.host
                )
                preferences_dict = auth_manager.get_user_preferences()
                preferences = convert_preferences_to_type(preferences_dict)
                companies = auth_manager.get_user_companies_with_roles()

                user_detail = UserDetail(
                    id=str(user_data.id),
                    email=user_data.email,
                    first_name=user_data.first_name,
                    last_name=user_data.last_name,
                    companies=[
                        CompanyInfo(
                            id=str(company["id"]),
                            name=company["name"],
                            company_id=(
                                str(company["company_id"])
                                if company.get("company_id")
                                else None
                            ),
                            agents=[
                                AgentInfo(
                                    name=agent["name"],
                                    id=agent["id"],
                                    status=agent["status"],
                                    default=preferences_dict.get("agent_id")
                                    == agent["id"],
                                    company_id=agent.get("company_id"),
                                )
                                for agent in company.get("agents", [])
                            ],
                            role_id=company.get("role_id"),
                            primary=company.get("primary", False),
                        )
                        for company in companies
                    ],
                    preferences=preferences,
                )

                # Get conversations
                c = Conversations(user=user)
                result = c.get_conversations_with_detail()

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
                    for id, details in result.items()
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

                conversation_connection = ConversationConnection(
                    page_info=page_info, edges=conversations[start_idx:end_idx]
                )

                # Get current conversation if ID provided
                current_conversation = None
                if conversation_id:
                    conversation_name = get_conversation_name_by_id(
                        conversation_id=conversation_id, user_id=auth_manager.user_id
                    )
                    c = Conversations(user=user, conversation_name=conversation_name)
                    conv_result = {"conversations": c.get_conversations_with_detail()}

                    if conversation_id in conv_result["conversations"]:
                        details = conv_result["conversations"][conversation_id]
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

                        c = Conversations(user=user, conversation_name=metadata.name)
                        history_result = c.get_conversation()

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
                            for msg in history_result["interactions"]
                        ]

                        current_conversation = ConversationDetail(
                            metadata=metadata, messages=messages
                        )

                notification_data = c.get_notifications()
                notifications = [
                    ConversationNotification(
                        conversation_id=notif["conversation_id"],
                        conversation_name=notif["conversation_name"],
                        message_id=notif["message_id"],
                        message=notif["message"],
                        role=notif["role"],
                        timestamp=notif["timestamp"],
                    )
                    for notif in notification_data
                ]

                return AppState(
                    user=user_detail,
                    conversations=conversation_connection,
                    current_conversation=current_conversation,
                    notifications=(notifications if notifications else None),
                )

            # Subscribe to relevant channels
            broadcaster = Broadcast("memory://")
            await broadcaster.connect()

            try:
                # Subscribe to conversations channel
                async with broadcaster.subscribe(
                    f"conversations_{user}"
                ) as conversations_subscriber:
                    if conversation_id:
                        # For conversation-specific messages
                        async with broadcaster.subscribe(
                            f"messages_{conversation_id}"
                        ) as messages_subscriber:
                            # For notifications
                            async with broadcaster.subscribe(
                                f"notifications_{user}"
                            ) as notifications_subscriber:
                                # Send initial state
                                initial_state = await get_app_state()
                                yield AppStateEvent(state=initial_state)

                                async def handle_subscriber(subscriber):
                                    try:
                                        async for event in subscriber:
                                            updated_state = await get_app_state()
                                            return updated_state
                                    except Exception as e:
                                        logging.error(
                                            f"Subscriber handler error: {str(e)}"
                                        )
                                        return None

                                # Create tasks for all active subscribers
                                tasks = [
                                    asyncio.create_task(
                                        handle_subscriber(conversations_subscriber)
                                    ),
                                    asyncio.create_task(
                                        handle_subscriber(messages_subscriber)
                                    ),
                                    asyncio.create_task(
                                        handle_subscriber(notifications_subscriber)
                                    ),
                                ]

                                # Main subscription loop
                                while True:
                                    done, pending = await asyncio.wait(
                                        tasks, return_when=asyncio.FIRST_COMPLETED
                                    )

                                    for task in done:
                                        try:
                                            result = await task
                                            if result:
                                                yield AppStateEvent(state=result)
                                        except Exception as e:
                                            logging.error(f"Task error: {str(e)}")

                                        # Recreate the completed task
                                        if task in tasks:
                                            index = tasks.index(task)
                                            if index == 0:
                                                tasks[0] = asyncio.create_task(
                                                    handle_subscriber(
                                                        conversations_subscriber
                                                    )
                                                )
                                            elif index == 1:
                                                tasks[1] = asyncio.create_task(
                                                    handle_subscriber(
                                                        messages_subscriber
                                                    )
                                                )
                                            elif index == 2:
                                                tasks[2] = asyncio.create_task(
                                                    handle_subscriber(
                                                        notifications_subscriber
                                                    )
                                                )

                                    # Keep the pending tasks
                                    tasks = list(pending)
                    else:
                        # Without conversation_id, only subscribe to conversations and notifications
                        async with broadcaster.subscribe(
                            f"notifications_{user}"
                        ) as notifications_subscriber:
                            # Send initial state
                            initial_state = await get_app_state()
                            yield AppStateEvent(state=initial_state)

                            async def handle_subscriber(subscriber):
                                try:
                                    async for event in subscriber:
                                        updated_state = await get_app_state()
                                        return updated_state
                                except Exception as e:
                                    logging.error(f"Subscriber handler error: {str(e)}")
                                    return None

                            # Create tasks for active subscribers
                            tasks = [
                                asyncio.create_task(
                                    handle_subscriber(conversations_subscriber)
                                ),
                                asyncio.create_task(
                                    handle_subscriber(notifications_subscriber)
                                ),
                            ]

                            # Main subscription loop
                            while True:
                                done, pending = await asyncio.wait(
                                    tasks, return_when=asyncio.FIRST_COMPLETED
                                )

                                for task in done:
                                    try:
                                        result = await task
                                        if result:
                                            yield AppStateEvent(state=result)
                                    except Exception as e:
                                        logging.error(f"Task error: {str(e)}")

                                    # Recreate the completed task
                                    if task in tasks:
                                        index = tasks.index(task)
                                        if index == 0:
                                            tasks[0] = asyncio.create_task(
                                                handle_subscriber(
                                                    conversations_subscriber
                                                )
                                            )
                                        elif index == 1:
                                            tasks[1] = asyncio.create_task(
                                                handle_subscriber(
                                                    notifications_subscriber
                                                )
                                            )

                                # Keep the pending tasks
                                tasks = list(pending)

            finally:
                await broadcaster.disconnect()

        except Exception as e:
            logging.error(f"Subscription error: {str(e)}")
            raise Exception(f"Subscription failed: {str(e)}")


# Query type with pagination
@strawberry.type
class Query:
    @strawberry.field
    async def conversations(
        self, info, pagination: Optional[PaginationInput] = None
    ) -> ConversationConnection:
        """Get paginated list of conversations with details"""
        user, auth, magical = await get_user_from_context(info)
        c = Conversations(user=user)
        result = c.get_conversations_with_detail()

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
            for id, details in result.items()
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
        user, auth, magical = await get_user_from_context(info)
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=magical.user_id
        )
        # Get conversation metadata
        c = Conversations(user=user, conversation_name=conversation_name)
        result = {"conversations": c.get_conversations_with_detail()}
        if conversation_id not in result["conversations"]:
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
        c = Conversations(user=user, conversation_name=metadata.name)
        history_result = c.get_conversation()

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
            for msg in history_result["interactions"]
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
        user, auth, magical = await get_user_from_context(info)
        result = Conversations(user=user).get_notifications()

        notifications = [
            ConversationNotification(
                conversation_id=notif["conversation_id"],
                conversation_name=notif["conversation_name"],
                message_id=notif["message_id"],
                message=notif["message"],
                role=notif["role"],
                timestamp=notif["timestamp"],
            )
            for notif in result
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
    async def providers(self, info) -> List[ProviderDetail]:
        """Get comprehensive provider details"""
        user, auth, magical = await get_user_from_context(info)
        provider_details = get_providers_with_details()
        providers = [
            convert_provider_details({"name": name, **details})
            for name, details in provider_details.items()
        ]
        return providers

    @strawberry.field
    async def prompt(self, info, name: str, category: str = "Default") -> PromptType:
        """Get a specific prompt by name and category"""
        user, auth, magical = await get_user_from_context(info)
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
    async def prompts(self, info) -> List[PromptType]:
        """Get all prompts in a category"""
        user, auth, magical = await get_user_from_context(info)
        prompt_manager = Prompts(user=user)
        result = prompt_manager.get_user_prompts()
        return [
            PromptType(
                name=prompt["name"],
                content=prompt["content"],
                category=prompt["category"],
                description=prompt["description"],
                arguments=[PromptArgument(name=arg) for arg in prompt["arguments"]],
            )
            for prompt in result
        ]

    @strawberry.field
    async def promptLibrary(self, info) -> List[PromptType]:
        """Get all prompts in a category"""
        user, auth, magical = await get_user_from_context(info)
        prompt_manager = Prompts(user=user)
        result = prompt_manager.get_global_prompts()
        return [
            PromptType(
                name=prompt["name"],
                content=prompt["content"],
                category=prompt["category"],
                description=prompt["description"],
                arguments=[PromptArgument(name=arg) for arg in prompt["arguments"]],
            )
            for prompt in result
        ]

    @strawberry.field
    async def prompt_categories(self, info) -> List[str]:
        """Get all prompt categories"""
        user, auth, magical = await get_user_from_context(info)
        prompt_manager = Prompts(user=user)
        return prompt_manager.get_prompt_categories()

    @strawberry.field
    async def agents(self, info) -> List[AgentType]:
        """Get all available agents"""
        user, auth, magic = await get_user_from_context(info)
        agents = get_agents(user=user)

        result = []
        user_preferences = magic.get_user_preferences()
        user_agent_id = user_preferences.get("agent_id")

        for agent in agents:
            agent_name = agent["name"]
            agent_instance = Agent(
                agent_name=agent_name,
                user=user,
                ApiClient=magic.get_user_agent_session(),
            )
            config = agent_instance.get_agent_config()
            agent_settings = {}
            for key, value in config["settings"].items():
                if value.strip() != "":
                    if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD"]):
                        agent_settings[key] = "HIDDEN"
                    else:
                        agent_settings[key] = value

            settings = [
                AgentSetting(
                    name=k,
                    value=v,
                )
                for k, v in agent_settings.items()
            ]

            commands = [
                AgentCommand(name=k, enabled=v) for k, v in config["commands"].items()
            ]

            result.append(
                AgentType(
                    id=agent["id"],
                    name=agent["name"],
                    status=agent["status"],
                    default=user_agent_id == agent["id"],
                    company_id=agent.get("company_id"),
                    settings=settings,
                    commands=commands,
                )
            )

        return result

    @strawberry.field
    async def agent(self, info, name: str) -> AgentType:
        user, auth, magic = await get_user_from_context(info)
        agent = Agent(
            agent_name=name, user=user, ApiClient=magic.get_user_agent_session()
        )
        config = agent.get_agent_config()
        agents = get_agents(user=user)
        settings = []
        for key, value in config["settings"].items():
            if value.strip() != "":
                if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD"]):
                    settings.append(AgentSetting(name=key, value="HIDDEN"))
                else:
                    settings.append(AgentSetting(name=key, value=value))
        commands = [
            AgentCommand(name=k, enabled=v) for k, v in config["commands"].items()
        ]
        # Default is a bool from agents
        default = False
        status = False
        for a in agents:
            if a["name"] == name:
                default = a["default"]
                status = a["status"]
                break

        return AgentType(
            id=agent.agent_id,
            name=name,
            status=status,
            default=default,
            company_id=config["settings"].get("company_id"),
            settings=settings,
            commands=commands,
        )

    @strawberry.field
    async def agent_providers(self, info, agent_name: str) -> List[ProviderDetails]:
        """Get providers available to an agent"""
        user, auth, magic = await get_user_from_context(info)
        agent = Agent(
            agent_name=agent_name, user=user, ApiClient=magic.get_user_agent_session()
        )
        agent_settings = agent.AGENT_CONFIG["settings"]
        providers = get_providers_with_details()

        provider_details = []
        for provider_name, details in providers.items():
            provider_settings = details["settings"]

            # Check if provider is connected
            connected = any(
                key in agent_settings and agent_settings[key] != ""
                for key in provider_settings
            )

            provider_details.append(
                ProviderDetails(
                    name=provider_name,
                    connected=connected,
                    friendly_name=details.get("name", provider_name),
                    description=details["description"],
                    settings=[
                        AgentSetting(name=k, value=v)
                        for k, v in provider_settings.items()
                    ],
                )
            )

        return provider_details

    @strawberry.field
    async def memories(
        self,
        info,
        agent_name: str,
        input: MemoryQueryInput,
        collection_number: str = "0",
    ) -> List[Memory]:
        """Query agent memories from a specific collection"""
        user, auth, magic = await get_user_from_context(info)
        if not auth:
            raise Exception("Authorization required")
        ApiClient = magic.get_user_agent_session()
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        memories = Memories(
            agent_name=agent_name,
            agent_config=agent.get_agent_config(),
            collection_number=collection_number,
            user=user,
            ApiClient=ApiClient,
        )

        results = await memories.get_memories_data(
            user_input=input.user_input,
            limit=input.limit,
            min_relevance_score=input.min_relevance_score,
        )

        return [
            Memory(
                key=result["key"],
                text=result["text"],
                embedding=result["embedding"],
                relevance_score=result.get("relevance_score"),
                external_source_name=result["external_source_name"],
                description=result["description"],
                timestamp=result["timestamp"],
                additional_metadata=result["additional_metadata"],
                id=result["id"],
            )
            for result in results
        ]

    @strawberry.field
    async def memory_collections(self, info, agent_name: str) -> List[str]:
        user, auth, magic = await get_user_from_context(info)
        ApiClient = magic.get_user_agent_session()
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        memories = Memories(
            agent_name=agent_name,
            agent_config=agent.get_agent_config(),
            collection_number="0",
            user=user,
            ApiClient=ApiClient,
        )
        return await memories.get_collections()

    @strawberry.field
    async def external_sources(
        self, info, agent_name: str, collection_number: str = "0"
    ) -> List[str]:
        user, auth, magic = await get_user_from_context(info)
        ApiClient = magic.get_user_agent_session()
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        agent_config = agent.get_agent_config()

        memories = Memories(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
            user=user,
            ApiClient=ApiClient,
        )
        return await memories.get_external_data_sources()

    @strawberry.field
    async def extension_settings(self, info) -> List[ExtensionSetting]:
        """Get all extension settings"""
        user, auth, magical = await get_user_from_context(info)

        extensions = Extensions(user=user)
        settings = extensions.get_extension_settings()

        return [
            ExtensionSetting(name=name, value=str(value))
            for name, value in settings.items()
        ]

    @strawberry.field
    async def command_args(self, info, command_name: str) -> CommandArgs:
        """Get arguments for a specific command"""
        user, auth, magical = await get_user_from_context(info)

        extensions = Extensions()
        raw_args = extensions.get_command_args(command_name=command_name)

        # Convert dictionary to CommandArgs type
        args = [
            CommandArg(name=name, value=CommandArgValue(value=str(value)))
            for name, value in raw_args.items()
        ]

        return CommandArgs(args=args)

    @strawberry.field
    async def extensions(self, info) -> List[Extension]:
        """Get all available extensions"""
        user, auth, magic = await get_user_from_context(info)
        ApiClient = magic.get_user_agent_session()
        extensions = Extensions(user=user, ApiClient=ApiClient)
        extension_list = extensions.get_extensions()

        return [
            Extension(
                extension_name=ext["extension_name"],
                description=ext["description"],
                settings=ext["settings"],
                commands=[
                    ExtensionCommand(
                        friendly_name=cmd["friendly_name"],
                        description=cmd["description"],
                        command_args=ExtensionCommandArgs(
                            required=cmd["command_args"].get("required", []),
                            optional=cmd["command_args"].get("optional", []),
                            description=cmd["command_args"].get("description", ""),
                        ),
                        extension_name=ext["extension_name"],
                    )
                    for cmd in ext["commands"]
                ],
                missing_keys=ext.get("missing_keys", []),
            )
            for ext in extension_list
        ]

    @strawberry.field
    async def agent_extensions(self, info, agent_name: str) -> List[Extension]:
        user, auth, magic = await get_user_from_context(info)
        if not auth:
            raise Exception("Authorization required")
        agent = Agent(
            agent_name=agent_name, user=user, ApiClient=magic.get_user_agent_session()
        )
        extension_list = agent.get_agent_extensions()

        return [convert_extension(ext) for ext in extension_list]

    @strawberry.field
    async def chain_library(self, info) -> List[DetailedChain]:
        """Get all global chains"""
        user, auth, magical = await get_user_from_context(info)
        chain_manager = Chain(user=user)
        global_chains = chain_manager.get_global_chains()

        result = []
        for chain in global_chains:
            try:
                converted_chain = convert_chain_to_detailed(
                    {
                        "id": chain.get("id"),
                        "name": chain.get("name"),
                        "description": chain.get("description"),
                        "steps": chain.get("steps", []),
                    }
                )
                if converted_chain:
                    result.append(converted_chain)
            except Exception as e:
                logging.error(f"Error converting global chain {chain.get('name')}: {e}")
                continue
        return result

    @strawberry.field
    async def chains(self, info) -> List[DetailedChain]:
        """Get all user-specific chains"""
        user, auth, magical = await get_user_from_context(info)
        chain_manager = Chain(user=user)
        user_chains = chain_manager.get_user_chains()

        result = []
        for chain_dict in user_chains:  # Iterate through the list of dictionaries
            try:
                if not isinstance(chain_dict, dict):
                    logging.error(
                        f"Expected dictionary, got {type(chain_dict)}: {chain_dict}"
                    )
                    continue

                # Pass the dictionary directly to the conversion function
                converted_chain = convert_chain_to_detailed(chain_dict)
                if converted_chain:
                    result.append(converted_chain)
            except Exception as e:
                import traceback

                logging.error(
                    f"Error converting user chain {chain_dict.get('name', 'UNKNOWN')}: {e}"
                )
                logging.error(traceback.format_exc())  # Log full traceback
                continue
        return result

    @strawberry.field
    async def chain(self, info, chain_name: str) -> ChainConfig:
        """Get details of a specific chain"""
        user, auth, magical = await get_user_from_context(info)
        chain_manager = Chain(user=user)
        raw_chain_data = chain_manager.get_chain(chain_name=chain_name)

        if not raw_chain_data or not raw_chain_data.get("steps"):
            raise Exception(f"Chain '{chain_name}' not found or has no steps.")

        try:
            # Use the same conversion logic
            detailed_chain = convert_chain_to_detailed(raw_chain_data)
        except Exception as e:
            logging.error(f"Error converting raw chain data for '{chain_name}': {e}")
            raise Exception(f"Failed to process chain data for '{chain_name}'.")

        # Build ChainConfig from the converted DetailedChain
        return ChainConfig(
            id=detailed_chain.id,
            chain_name=detailed_chain.chain_name,
            description=detailed_chain.description,
            steps=detailed_chain.steps,
        )

    @strawberry.field
    async def chain_args(self, info, chain_name: str) -> List[str]:
        """Get available arguments for a chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        return chain_manager.get_chain_args(chain_name=chain_name)

    @strawberry.field
    async def chain_dependencies(self, info, chain_name: str) -> List[ChainDependency]:
        """Get dependencies between chain steps"""
        user, auth, magical = await get_user_from_context(info)

        chain_manager = Chain(user=user)
        deps = chain_manager.get_chain_step_dependencies(chain_name=chain_name)

        return [
            ChainDependency(step_number=step_num, dependencies=deps)
            for step_num, deps in deps.items()
        ]

    @strawberry.field
    async def user(self, info) -> UserDetail:
        """Get current user's details"""
        user, auth, auth_manager = await get_user_from_context(info)
        user_data = auth_manager.login(ip_address=info.context["request"].client.host)
        preferences_dict = auth_manager.get_user_preferences()
        preferences = convert_preferences_to_type(preferences_dict)
        companies = auth_manager.get_user_companies_with_roles()
        agents = get_agents(user=user)
        default_agent_id = None
        for agent in agents:
            if agent["default"]:
                default_agent_id = agent["id"]
                break
        return UserDetail(
            id=str(user_data.id),
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            companies=[
                CompanyInfo(
                    id=str(company["id"]),
                    name=company["name"],
                    company_id=(
                        str(company["company_id"])
                        if company.get("company_id")
                        else None
                    ),
                    agents=[
                        AgentInfo(
                            name=agent["name"],
                            id=agent["id"],
                            status=agent["status"],
                            default=default_agent_id == agent["id"],
                            company_id=agent.get("company_id"),
                        )
                        for agent in company.get("agents", [])
                    ],
                    role_id=company.get("role_id"),
                    primary=company.get("primary", False),
                )
                for company in companies
            ],
            preferences=preferences,
        )

    @strawberry.field
    async def user_exists(self, info, email: str) -> bool:
        """Check if a user exists"""
        auth_manager = MagicalAuth()
        return auth_manager.user_exists(email=email)

    @strawberry.field
    async def invitations(
        self, info, company_id: Optional[str] = None
    ) -> List[InvitationInfo]:
        """Get company invitations"""
        user, auth, auth_manager = await get_user_from_context(info)

        invites = auth_manager.get_invitations(company_id)
        return [
            InvitationInfo(
                id=invite["id"],
                email=invite["email"],
                company_id=invite["company_id"],
                role_id=invite["role_id"],
                inviter_id=invite["inviter_id"],
                created_at=invite["created_at"],
                is_accepted=invite["is_accepted"],
            )
            for invite in invites
        ]

    @strawberry.field
    async def sso_providers(self, info) -> List[SSOProviderInfo]:
        """Get SSO provider connections"""
        user, auth, auth_manager = await get_user_from_context(info)
        connections = auth_manager.get_sso_connections()
        return [
            SSOProviderInfo(
                name=provider,
                connected=True,
                account_name=None,  # Could be enhanced to include account info
            )
            for provider in connections
        ]


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
        user, auth, magical = await get_user_from_context(info)
        model = ConversationHistoryModel(**input.__dict__)
        c = Conversations(user=user)
        result = c.new_conversation(
            conversation_content=model.conversation_content,
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
            for msg in result
        ]

        return ConversationHistory(messages=messages)

    @strawberry.mutation
    async def delete_conversation(
        self, info, input: ConversationHistoryInput
    ) -> MutationResponse:
        """Delete a conversation"""
        user, auth, magical = await get_user_from_context(info)
        model = ConversationHistoryModel(**input.__dict__)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.delete_conversation()
        return MutationResponse(success=True, message=result)

    @strawberry.mutation
    async def rename_conversation(
        self,
        info,
        agent_name: str,
        conversation_name: str,
        new_conversation_name: str = "-",
    ) -> MutationResponse:
        """Rename a conversation"""
        user, auth, magical = await get_user_from_context(info)
        model = RenameConversationModel(
            agent_name=agent_name,
            conversation_name=conversation_name,
            new_conversation_name=new_conversation_name,
        )
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.rename_conversation(
            new_conversation_name=model.new_conversation_name
        )
        return MutationResponse(
            success=True,
            message=f"Conversation renamed to {result}",
        )

    @strawberry.mutation
    async def update_message(self, info, input: UpdateMessageInput) -> MutationResponse:
        """Update a conversation message"""
        user, auth, magical = await get_user_from_context(info)
        model = UpdateConversationHistoryMessageModel(**input.__dict__)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.update_message(message=model.message, new_message=model.new_message)
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def update_message_by_id(
        self, info, message_id: str, input: MessageByIdInput
    ) -> MutationResponse:
        """Update a message by its ID"""
        user, auth, magical = await get_user_from_context(info)
        model = UpdateMessageModel(**input.__dict__)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.update_message_by_id(
            message_id=message_id, new_message=model.new_message
        )
        return MutationResponse(success=True, message=result)

    @strawberry.mutation
    async def delete_message(
        self, info, input: ConversationHistoryMessageInput
    ) -> MutationResponse:
        """Delete a message by its content"""
        user, auth, magical = await get_user_from_context(info)
        model = ConversationHistoryMessageModel(**input.__dict__)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.delete_message(message=model.message)
        return MutationResponse(success=True, message=result)

    @strawberry.mutation
    async def delete_message_by_id(
        self, info, message_id: str, conversation_name: str
    ) -> MutationResponse:
        """Delete a message by its ID"""
        user, auth, magical = await get_user_from_context(info)
        model = DeleteMessageModel(conversation_name=conversation_name)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.delete_message_by_id(message_id=message_id)
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def fork_conversation(
        self, info, input: ConversationForkInput
    ) -> MutationResponse:
        """Fork a conversation"""
        user, auth, magical = await get_user_from_context(info)
        model = ConversationFork(**input.__dict__)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.fork_conversation(
            message_id=model.message_id,
        )
        return MutationResponse(success=True, message=result.message)

    @strawberry.mutation
    async def log_interaction(
        self, info, input: LogInteractionInput
    ) -> MutationResponse:
        """Log a conversation interaction"""
        user, auth, magical = await get_user_from_context(info)
        model = LogInteraction(**input.__dict__)
        c = Conversations(user=user, conversation_name=model.conversation_name)
        result = c.log_interaction(
            message=model.message,
            role=model.role,
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
        user, auth, magical = await get_user_from_context(info)
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
        user, auth, magical = await get_user_from_context(info)
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
        user, auth, magical = await get_user_from_context(info)
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
        user, auth, magical = await get_user_from_context(info)
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
        user, auth, magic = await get_user_from_context(info)
        if not is_admin(email=user, api_key=auth):
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
            agent = Agent(
                agent_name=input.name,
                user=user,
                ApiClient=magic.get_user_agent_session(),
            )
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
        user, auth, magic = await get_user_from_context(info)
        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(
            agent_name=agent_name, user=user, ApiClient=magic.get_user_agent_session()
        )
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
        user, auth, magic = await get_user_from_context(info)
        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(
            agent_name=agent_name, user=user, ApiClient=magic.get_user_agent_session()
        )
        commands = {c.name: c.enabled for c in input.commands}

        result = agent.update_agent_config(new_config=commands, config_key="commands")

        return AgentResponse(success=True, message=result)

    @strawberry.mutation
    async def delete_agent(self, info, name: str) -> AgentResponse:
        """Delete an agent"""
        user, auth, magic = await get_user_from_context(info)
        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent = Agent(
            agent_name=name, user=user, ApiClient=magic.get_user_agent_session()
        )
        websearch = Websearch(collection_number="0", agent=agent, user=user)
        await websearch.agent_memory.wipe_memory()

        result = delete_agent(agent_name=name, user=user)
        return AgentResponse(success=True, message=f"Agent {name} deleted successfully")

    @strawberry.mutation
    async def rename_agent(self, info, old_name: str, new_name: str) -> AgentResponse:
        """Rename an agent"""
        user, auth, magical = await get_user_from_context(info)
        if not is_admin(email=user, api_key=auth):
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
        user, auth, magic = await get_user_from_context(info)

        conversation_name = input.prompt_args.conversation_name or None
        if conversation_name != "-":
            try:
                conversation_id = str(uuid.UUID(conversation_name))
                if conversation_id:
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
        user, auth, magical = await get_user_from_context(info)

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

    @strawberry.mutation
    async def learn_text(self, info, agent_name: str, input: TextMemoryInput) -> bool:
        """Add text content to agent's memory"""
        user, auth, magic = await get_user_from_context(info)

        collection_number = input.collection_number
        if len(collection_number) > 4:
            conversation = Conversations(conversation_name=collection_number, user=user)
            collection_number = conversation.get_conversation_id()
        memories = Memories(
            agent_name=agent_name,
            collection_number=collection_number,
            user=user,
            ApiClient=magic.get_user_agent_session(),
        )

        return await memories.write_text_to_memory(
            user_input=input.user_input, text=input.text, external_source="user input"
        )

    @strawberry.mutation
    async def learn_file(self, info, agent_name: str, input: FileMemoryInput) -> bool:
        """Process and learn from file content"""
        user, auth, auth_manager = await get_user_from_context(info)

        # Handle company-specific learning if company_id provided
        if input.company_id:
            agixt = auth_manager.get_company_agent_session(company_id=input.company_id)
            response = agixt.learn_file(
                agent_name="AGiXT",
                file_name=input.file_name,
                file_content=input.file_content,
                collection_number=input.collection_number,
            )
            return response

        # Regular file learning
        collection_number = str(input.collection_number)
        conversation_name = None

        if len(collection_number) > 4:
            conversation = Conversations(conversation_name=collection_number, user=user)
            collection_number = conversation.get_conversation_id()
            conversation_name = collection_number

        agent = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=conversation_name,
            collection_id=collection_number,
        )

        file_name = os.path.basename(input.file_name)
        file_path = os.path.normpath(
            os.path.join(agent.agent_workspace, input.collection_number, file_name)
        )

        if not file_path.startswith(agent.agent_workspace):
            raise Exception("Path given not allowed")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            file_content = base64.b64decode(input.file_content)
        except:
            file_content = input.file_content.encode("utf-8")

        with open(file_path, "wb") as f:
            f.write(file_content)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_url = f"{agent.outputs}/{input.collection_number}/{file_name}"

        response = await agent.learn_from_file(
            file_url=file_url,
            file_name=file_name,
            user_input=f"File {file_name} uploaded on {timestamp}.",
            collection_id=str(input.collection_number),
        )

        agent.conversation.log_interaction(
            role=agent_name,
            message=f"File [{file_name}]({file_url}) learned on {timestamp} to collection `{input.collection_number}`.",
        )

        return True

    @strawberry.mutation
    async def learn_url(self, info, agent_name: str, input: UrlMemoryInput) -> bool:
        """Learn from URL content"""
        user, auth, magic = await get_user_from_context(info)

        agent = Agent(
            agent_name=agent_name, user=user, ApiClient=magic.get_user_agent_session()
        )
        url = input.url.replace(" ", "%20")

        websearch = Websearch(
            collection_number=input.collection_number, agent=agent, user=user
        )

        timestamp = datetime.now().strftime("%Y-%m-%d")
        conversation_name = f"{agent_name} Training on {timestamp}"

        await websearch.scrape_websites(
            user_input=f"I am browsing {url} and collecting data from it to learn more.",
            conversation_name=conversation_name,
        )

        conversation = Conversations(conversation_name=conversation_name, user=user)
        conversation.log_interaction(
            role=agent_name,
            message=f"URL [{url}]({url}) learned on {timestamp} to collection `{input.collection_number}`.",
        )

        return True

    @strawberry.mutation
    async def wipe_memories(
        self, info, agent_name: str, collection_number: Optional[str] = None
    ) -> bool:
        """Wipe agent memories - optionally from specific collection"""
        user, auth, magic = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")
        memories = Memories(
            agent_name=agent_name,
            collection_number=collection_number if collection_number else "0",
            user=user,
            ApiClient=magic.get_user_agent_session(),
        )

        return await memories.wipe_memory()

    @strawberry.mutation
    async def submit_feedback(
        self, info, agent_name: str, input: FeedbackInput
    ) -> bool:
        """Submit RLHF feedback for an interaction"""
        user, auth, magical = await get_user_from_context(info)

        agixt = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=input.conversation_name,
        )

        conversation = agixt.conversation
        if conversation.has_received_feedback(message=input.message):
            return False

        memory = (
            agixt.agent_interactions.agent_memory
            if input.positive
            else agixt.agent_interactions.agent_memory
        )

        reflection = await agixt.inference(
            user_input=input.user_input,
            input_kind="positive" if input.positive else "negative",
            assistant_response=input.message,
            feedback=input.feedback,
            log_user_input=False,
            log_output=False,
        )

        memory_message = f"""## Feedback received from a similar interaction in the past:
### User
{input.user_input}

### Assistant
{input.message}

### Feedback from User
{input.feedback}

### Reflection on the feedback
{reflection}
"""

        await memory.write_text_to_memory(
            user_input=input.user_input,
            text=memory_message,
            external_source="reflection from user feedback",
        )

        feedback_type = "Positive" if input.positive else "Negative"
        conversation.log_interaction(
            role=agent_name,
            message=f"[ACTIVITY][INFO] {feedback_type} feedback received.",
        )
        conversation.toggle_feedback_received(message=input.message)

        return True

    # @strawberry.mutation
    async def create_dataset(self, info, agent_name: str, input: DatasetInput) -> bool:
        """Create training dataset from memories"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        asyncio.create_task(
            AGiXT(
                agent_name=agent_name,
                user=user,
                api_key=auth,
                conversation_name=f"Dataset Creation on {timestamp}",
            ).create_dataset_from_memories(batch_size=input.batch_size)
        )

        return True

    # @strawberry.mutation
    async def generate_dpo(self, info, agent_name: str, input: DPOInput) -> DPOResult:
        """Generate DPO response for input"""
        user, auth, magical = await get_user_from_context(info)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agixt = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=f"DPO on {timestamp}",
        )

        prompt, chosen, rejected = await agixt.dpo(
            question=input.user_input, injected_memories=input.injected_memories
        )

        return DPOResult(prompt=prompt, chosen=chosen, rejected=rejected)

    @strawberry.mutation
    async def delete_memory(
        self, info, agent_name: str, memory_id: str, collection_number: str = "0"
    ) -> bool:
        """Delete a specific memory by ID"""
        user, auth, magic = await get_user_from_context(info)
        memories = Memories(
            agent_name=agent_name,
            collection_number=collection_number,
            user=user,
            ApiClient=magic.get_user_agent_session(),
        )

        return await memories.delete_memory(key=memory_id)

    @strawberry.mutation
    async def delete_external_source_memories(
        self, info, agent_name: str, external_source: str, collection_number: str = "0"
    ) -> bool:
        """Delete all memories from a specific external source"""
        user, auth, magic = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")
        memories = Memories(
            agent_name=agent_name,
            collection_number=collection_number,
            user=user,
            ApiClient=magic.get_user_agent_session(),
        )

        return await memories.delete_memories_from_external_source(
            external_source=external_source
        )

    @strawberry.mutation
    async def export_memories(
        self, info, agent_name: str
    ) -> List[MemoryExportCollection]:
        """Export all agent memories"""
        user, auth, magic = await get_user_from_context(info)
        ApiClient = magic.get_user_agent_session()
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        memories = Memories(
            agent_name=agent_name,
            agent_config=agent.get_agent_config(),
            user=user,
            ApiClient=ApiClient,
        )

        raw_data = await memories.export_collections_to_json()

        # Convert raw dictionary data to proper types
        return [
            MemoryExportCollection(
                collection_id=collection_id,
                memories=[
                    MemoryExportEntry(
                        external_source_name=memory["external_source_name"],
                        description=memory["description"],
                        text=memory["text"],
                        timestamp=memory["timestamp"],
                    )
                    for memory in memories
                ],
            )
            for collection_id, memories in raw_data.items()
        ]

    @strawberry.mutation
    async def import_memories(
        self, info, agent_name: str, collections: List[MemoryImportCollection]
    ) -> bool:
        """Import memories for an agent"""
        user, auth, magic = await get_user_from_context(info)
        ApiClient = magic.get_user_agent_session()
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        memories = Memories(
            agent_name=agent_name,
            agent_config=agent.get_agent_config(),
            user=user,
            ApiClient=ApiClient,
        )

        # Convert typed data to format expected by import function
        import_data = [
            {
                collection.collection_id: [
                    {
                        "external_source_name": memory.external_source_name,
                        "description": memory.description,
                        "text": memory.text,
                        "timestamp": memory.timestamp or datetime.now().isoformat(),
                    }
                    for memory in collection.memories
                ]
            }
            for collection in collections
        ]

        await memories.import_collections_from_json(import_data)
        return True

    @strawberry.mutation
    async def execute_command(
        self, info, agent_name: str, input: CommandExecutionInput
    ) -> CommandResult:
        """Execute a command for an agent"""
        user, auth, magic = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        # Convert input args to dictionary format expected by extensions
        command_args = {arg.name: arg.value for arg in input.command_args}
        agent = Agent(
            agent_name=agent_name, user=user, ApiClient=magic.get_user_agent_session()
        )
        agent_config = agent.get_agent_config()

        conversation_id = None
        if input.conversation_name:
            conversation = Conversations(conversation_name=input.conversation_name)
            conversation_id = conversation.get_conversation_id()

        extensions = Extensions(
            agent_name=agent_name,
            agent_config=agent_config,
            agent_id=agent.agent_id,
            conversation_name=input.conversation_name,
            conversation_id=conversation_id,
            user=user,
            api_key=auth,
        )

        command_output = await extensions.execute_command(
            command_name=input.command_name, command_args=command_args
        )

        if input.conversation_name and command_output:
            conversation = Conversations(
                conversation_name=input.conversation_name, user=user
            )
            conversation.log_interaction(role=agent_name, message=command_output)

        return CommandResult(response=command_output if command_output else "")

    @strawberry.mutation
    async def create_chain(self, info, input: ChainInput) -> bool:
        """Create a new chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.add_chain(chain_name=input.chain_name)

        if input.steps:
            for step in input.steps:
                chain_manager.add_chain_step(
                    chain_name=input.chain_name,
                    step_number=step.step_number,
                    agent_name=step.agent_name,
                    prompt_type=step.prompt_type,
                    prompt=step.prompt.__dict__,
                )

        return True

    @strawberry.mutation
    async def delete_chain(self, info, chain_name: str) -> bool:
        """Delete an existing chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.delete_chain(chain_name=chain_name)
        return True

    @strawberry.mutation
    async def rename_chain(self, info, old_name: str, new_name: str) -> bool:
        """Rename an existing chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.rename_chain(chain_name=old_name, new_name=new_name)
        return True

    @strawberry.mutation
    async def add_chain_step(self, info, chain_name: str, step: ChainStepInput) -> bool:
        """Add a step to an existing chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.add_chain_step(
            chain_name=chain_name,
            step_number=step.step_number,
            agent_name=step.agent_name,
            prompt_type=step.prompt_type,
            prompt=step.prompt.__dict__,
        )
        return True

    @strawberry.mutation
    async def update_chain_step(
        self, info, chain_name: str, step: ChainStepInput
    ) -> bool:
        """Update an existing chain step"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.update_step(
            chain_name=chain_name,
            step_number=step.step_number,
            agent_name=step.agent_name,
            prompt_type=step.prompt_type,
            prompt=step.prompt.__dict__,
        )
        return True

    @strawberry.mutation
    async def delete_chain_step(self, info, chain_name: str, step_number: int) -> bool:
        """Delete a step from a chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.delete_step(chain_name=chain_name, step_number=step_number)
        return True

    @strawberry.mutation
    async def move_chain_step(
        self, info, chain_name: str, input: MoveStepInput
    ) -> bool:
        """Move a step to a new position in the chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_manager.move_step(
            chain_name=chain_name,
            current_step_number=input.old_step_number,
            new_step_number=input.new_step_number,
        )
        return True

    @strawberry.mutation
    async def run_chain(self, info, chain_name: str, input: RunChainInput) -> str:
        """Execute a chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        agent_name = input.agent_override or "gpt4free"
        chain_args = convert_chain_args_to_dict(input.chain_args)
        chain_response = await AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=input.conversation_name,
        ).execute_chain(
            chain_name=chain_name,
            user_input=input.prompt,
            agent_override=input.agent_override,
            from_step=input.from_step,
            chain_args=chain_args,
            log_user_input=False,
        )

        if "Chain failed to complete" in chain_response:
            raise Exception(chain_response)

        return chain_response

    @strawberry.mutation
    async def run_chain_step(
        self, info, chain_name: str, step_number: int, input: RunChainStepInput
    ) -> str:
        """Execute a specific step in a chain"""
        user, auth, magical = await get_user_from_context(info)

        if not is_admin(email=user, api_key=auth):
            raise Exception("Access Denied")

        chain_manager = Chain(user=user)
        chain_steps = chain_manager.get_chain(chain_name=chain_name)

        try:
            step = chain_steps["steps"][step_number - 1]  # Convert to 0-based index
        except Exception as e:
            raise Exception(f"Step {step_number} not found. {e}")

        agent_name = input.agent_override or step["agent_name"]

        chain_step_response = await AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=auth,
            conversation_name=input.conversation_name,
        ).run_chain_step(
            chain_run_id=input.chain_run_id,
            step=step,
            chain_name=chain_name,
            user_input=input.prompt,
            agent_override=input.agent_override,
            chain_args=input.chain_args or {},
        )

        if chain_step_response is None:
            raise Exception(f"Error running step {step_number} in chain {chain_name}")

        if "Chain failed to complete" in chain_step_response:
            raise Exception(chain_step_response)

        return chain_step_response

    @strawberry.mutation
    async def register(self, info, input: RegisterInput) -> RegistrationResponse:
        """Register a new user"""
        auth_manager = MagicalAuth()

        if auth_manager.user_exists(email=input.email):
            return RegistrationResponse(
                success=False, message="User with this email already exists"
            )

        result = auth_manager.register(
            new_user=input, invitation_id=input.invitation_id
        )

        if isinstance(result, dict) and "error" in result:
            return RegistrationResponse(success=False, message=result["error"])

        return RegistrationResponse(
            success=True,
            message="Registration successful",
            otp_uri=result.get("otp_uri"),
            magic_link=result.get("magic_link"),
            mfa_token=result.get("mfa_token"),
        )

    @strawberry.mutation
    async def login(self, info, input: LoginInput) -> AuthResponse:
        """Login with email and OTP"""
        request = info.context["request"]
        auth_manager = MagicalAuth()

        magic_link = auth_manager.send_magic_link(
            ip_address=request.client.host, login=input, referrer=None
        )

        return AuthResponse(
            success=True,
            message=(
                "Login successful" if "has been sent" not in magic_link else magic_link
            ),
            token=auth_manager.token,
            email=input.email,
        )

    @strawberry.mutation
    async def update_user(self, info, input: UserUpdateInput) -> AuthResponse:
        """Update user details"""
        user, auth, auth_manager = await get_user_from_context(info)

        # Convert input to dictionary format expected by backend
        update_dict = convert_user_update_to_dict(input)

        result = auth_manager.update_user(**update_dict)
        return AuthResponse(success=True, message=result)

    @strawberry.mutation
    async def delete_user(self, info) -> AuthResponse:
        """Delete current user"""
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.delete_user()
        return AuthResponse(success=True, message=result)

    @strawberry.mutation
    async def create_invitation(
        self, info, input: InvitationCreateInput
    ) -> InvitationInfo:
        """Create a company invitation"""
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.create_invitation(input)
        return InvitationInfo(
            id=result.id,
            email=result.email,
            company_id=result.company_id,
            role_id=result.role_id,
            inviter_id=result.inviter_id,
            created_at=result.created_at,
            is_accepted=result.is_accepted,
        )

    @strawberry.mutation
    async def delete_invitation(self, info, invitation_id: str) -> AuthResponse:
        """Delete an invitation"""
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.delete_invitation(invitation_id)
        return AuthResponse(success=True, message=result)

    @strawberry.mutation
    async def create_company(self, info, input: CompanyCreateInput) -> CompanyInfo:
        """Create a new company"""
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.create_company_with_agent(
            name=input.name,
            parent_company_id=input.parent_company_id,
            agent_name=input.agent_name,
        )

        return CompanyInfo(
            id=result["id"],
            name=result["name"],
            company_id=None,
            agents=[],
            role_id=2,  # Company admin by default
            primary=True,
        )

    @strawberry.mutation
    async def update_company(
        self, info, company_id: str, input: CompanyUpdateInput
    ) -> CompanyInfo:
        """Update company details"""
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.update_company(company_id=company_id, name=input.name)

        return CompanyInfo(
            id=result.id,
            name=result.name,
            company_id=result.company_id,
            agents=[],
            role_id=None,
            primary=False,
        )

    @strawberry.mutation
    async def verify_mfa(self, info, input: MFAVerificationInput) -> AuthResponse:
        """Verify MFA code"""
        if input.email:  # Handle case where verifying without being logged in
            token = impersonate_user(input.email)
            auth_manager = MagicalAuth(token=token)
        else:
            raise Exception("Please include email address to verify MFA")
        result = auth_manager.verify_mfa(token=input.code)
        return AuthResponse(
            success=result,
            message=(
                "MFA verified successfully" if result else "MFA verification failed"
            ),
        )

    @strawberry.mutation
    async def verify_email(self, info, input: EmailVerificationInput) -> AuthResponse:
        """Verify email address"""
        auth_manager = MagicalAuth()
        auth_manager.email = input.email
        auth_manager.send_email_verification_link()
        return AuthResponse(
            success=True, message="Verification code has been sent via email"
        )

    @strawberry.mutation
    async def connect_sso(
        self, info, provider: str, code: str, referrer: Optional[str] = None
    ) -> AuthResponse:
        """Connect SSO provider"""
        request = info.context["request"]
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.sso(
            provider=provider,
            code=code,
            ip_address=request.client.host,
            referrer=referrer,
        )

        return AuthResponse(
            success=True, message="SSO connected successfully", magic_link=result
        )

    @strawberry.mutation
    async def disconnect_sso(self, info, provider: str) -> AuthResponse:
        """Disconnect SSO provider"""
        user, auth, auth_manager = await get_user_from_context(info)

        result = auth_manager.disconnect_sso(provider_name=provider)
        return AuthResponse(success=True, message=result)


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
