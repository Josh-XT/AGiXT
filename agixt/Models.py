from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic.fields import Field
from Globals import getenv


# Auth Models
class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: str
    role_id: int


class CompanyResponse(BaseModel):
    id: str
    name: str
    company_id: Optional[str] = None
    status: Optional[bool] = True
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    users: List[UserResponse]
    children: List["CompanyResponse"] = []


class NewCompanyResponse(BaseModel):
    id: str
    name: str


class InvitationCreate(BaseModel):
    email: str
    company_id: Optional[str] = None
    role_id: int


class InvitationResponse(BaseModel):
    id: str
    invitation_link: str
    email: str
    company_id: str
    role_id: int
    inviter_id: str
    created_at: datetime
    is_accepted: bool

    class Config:
        from_attributes = True


class Login(BaseModel):
    email: str
    token: str


class Register(BaseModel):
    email: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    invitation_id: Optional[str] = ""


class Invitation(BaseModel):
    email: str
    company_id: str
    role_id: int


class UserInfo(BaseModel):
    first_name: str
    last_name: str


class Detail(BaseModel):
    detail: str


# Agent Models
class AgentName(BaseModel):
    agent_name: str


class AgentNewName(BaseModel):
    new_name: str
    company_id: Optional[str] = None


class AgentPrompt(BaseModel):
    prompt_name: str
    prompt_args: dict


class ThinkingPrompt(BaseModel):
    user_input: str
    agent_name: str
    conversation_id: Optional[str] = ""
    prompt_args: Optional[dict] = {}


class AgentMemoryQuery(BaseModel):
    user_input: str
    limit: int = 5
    min_relevance_score: float = 0.0


class UserInput(BaseModel):
    user_input: str
    injected_memories: Optional[int] = 100


class LogInteraction(BaseModel):
    role: str
    message: str
    conversation_name: Optional[str] = ""


# Memory and Context Models
class FileInput(BaseModel):
    file_name: str
    file_content: str
    collection_number: Optional[Any] = "0"
    company_id: Optional[str] = None


class ExternalSource(BaseModel):
    external_source: str
    collection_number: Optional[str] = "0"
    company_id: Optional[str] = None


class TextMemoryInput(BaseModel):
    user_input: str
    text: str
    collection_number: Optional[str] = "0"


# Conversation Models
class ConversationHistoryModel(BaseModel):
    agent_name: Optional[str] = ""
    conversation_name: str
    conversation_content: List[dict] = []


class RenameConversationModel(BaseModel):
    agent_name: str
    conversation_name: str
    new_conversation_name: Optional[str] = "-"


class ConversationFork(BaseModel):
    conversation_name: str
    message_id: str


class UpdateMessageModel(BaseModel):
    conversation_name: str
    message_id: str
    new_message: str


class DeleteMessageModel(BaseModel):
    conversation_name: str


# Agent Configuration Models
class AgentSettings(BaseModel):
    agent_name: str
    settings: Optional[Dict[str, Any]] = {}
    commands: Optional[Dict[str, Any]] = {}
    training_urls: Optional[List[str]] = []


class AgentConfig(BaseModel):
    agent_name: str
    settings: Dict[str, Any]
    commands: Dict[str, Any]


class ToggleCommandPayload(BaseModel):
    command_name: str
    enable: bool


# AI Service Models
class ChatCompletions(BaseModel):
    model: Optional[str] = None  # This is the agent name
    messages: List[dict] = None
    temperature: Optional[float] = 0.9
    top_p: Optional[float] = 1.0
    tools: Optional[List[dict]] = None
    tools_choice: Optional[str] = "auto"
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    max_tokens: Optional[int] = 4096
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = "Chat"  # This is the conversation name


class TextToSpeech(BaseModel):
    input: str
    model: Optional[str] = "XT"
    voice: Optional[str] = "default"
    language: Optional[str] = "en"
    user: Optional[str] = None


class ImageCreation(BaseModel):
    prompt: str
    model: Optional[str] = "dall-e-3"
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"


class EmbeddingModel(BaseModel):
    input: Union[str, List[str]]
    model: str
    user: Optional[str] = None


# Chain Models
class ChainData(BaseModel):
    chain_name: str
    steps: Dict[str, Any]


class RunChain(BaseModel):
    prompt: str
    agent_override: Optional[str] = ""
    all_responses: Optional[bool] = False
    from_step: Optional[int] = 1
    chain_args: Optional[dict] = {}
    conversation_name: Optional[str] = ""


class RunChainStep(BaseModel):
    prompt: str
    agent_override: Optional[str] = ""
    chain_args: Optional[dict] = {}
    chain_run_id: Optional[str] = ""
    conversation_name: Optional[str] = ""


class ChainStep(BaseModel):
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: dict


# History and Feedback Models
class HistoryModel(BaseModel):
    agent_name: Optional[str] = getenv("AGENT_NAME")
    conversation_name: Optional[str] = None
    limit: Optional[int] = 100
    page: Optional[int] = 1


class FeedbackInput(BaseModel):
    user_input: str
    message: str
    feedback: str
    positive: Optional[bool] = True
    conversation_name: Optional[str] = ""


# Integration Models
class GitHubInput(BaseModel):
    github_repo: str
    github_user: Optional[str] = None
    github_token: Optional[str] = None
    github_branch: Optional[str] = "main"
    use_agent_settings: Optional[bool] = False
    collection_number: Optional[int] = 0


class ArxivInput(BaseModel):
    query: Optional[str] = None
    article_ids: Optional[str] = None
    max_results: Optional[int] = 5
    collection_number: Optional[int] = 0


class WebhookUser(BaseModel):
    email: str
    agent_name: Optional[str] = ""
    settings: Optional[Dict[str, Any]] = {}
    commands: Optional[Dict[str, Any]] = {}
    training_urls: Optional[List[str]] = []
    github_repos: Optional[List[str]] = []
    zip_file_content: Optional[str] = ""


class WebhookModel(BaseModel):
    success: str


class TasksToDo(BaseModel):
    tasks: List[str]


class ChainCommandName(BaseModel):
    command_name: str


class TranslationRequest(BaseModel):
    target_language_translated_text: str


class Dataset(BaseModel):
    batch_size: int = 5


class FinetuneAgentModel(BaseModel):
    model: Optional[str] = "unsloth/mistral-7b-v0.2"
    max_seq_length: Optional[int] = 16384
    huggingface_output_path: Optional[str] = "JoshXT/finetuned-mistral-7b-v0.2"
    private_repo: Optional[bool] = True


class Objective(BaseModel):
    objective: str


class Prompt(BaseModel):
    prompt: str


class PromptName(BaseModel):
    prompt_name: str


class PromptList(BaseModel):
    prompts: List[str]


class PromptCategoryList(BaseModel):
    prompt_categories: List[str]


class CustomPromptModel(BaseModel):
    prompt_name: str
    prompt: str


class ChainNewName(BaseModel):
    new_name: Optional[str] = None
    description: Optional[str] = None


class ChainName(BaseModel):
    chain_name: str
    description: Optional[str] = None


class StepInfo(BaseModel):
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: dict


class RunChainResponse(BaseModel):
    response: str
    agent_name: str
    prompt: dict
    prompt_type: str


class ChainStepNewInfo(BaseModel):
    old_step_number: int
    new_step_number: int


class ResponseMessage(BaseModel):
    message: str


class ConversationHistoryMessageModel(BaseModel):
    agent_name: Optional[str] = ""
    conversation_name: str
    message: str


class UpdateConversationHistoryMessageModel(BaseModel):
    agent_name: Optional[str] = ""
    conversation_name: str
    message: str
    new_message: str


class UrlInput(BaseModel):
    url: str
    collection_number: Optional[str] = "0"


class PersonaInput(BaseModel):
    persona: str
    company_id: Optional[str] = None


class TaskPlanInput(BaseModel):
    user_input: str
    websearch: Optional[bool] = False
    websearch_depth: Optional[int] = 3
    conversation_name: Optional[str] = "AGiXT Task Planning"
    log_user_input: Optional[bool] = True
    log_output: Optional[bool] = True
    enable_new_command: Optional[bool] = True


class YoutubeInput(BaseModel):
    video_id: str
    collection_number: Optional[str] = "0"


class AgentBrowsedLinks(BaseModel):
    agent_name: str
    links: List[Dict[str, Any]]


class AgentCommands(BaseModel):
    agent_name: str
    commands: Dict[str, Any]


class TaskOutput(BaseModel):
    output: str
    message: Optional[str] = None


class CommandExecution(BaseModel):
    command_name: str
    command_args: dict
    conversation_name: str = "AGiXT Terminal Command Execution"


class TTSInput(BaseModel):
    text: str


class ProvidersResponse(BaseModel):
    providers: List[str]


class ProviderSettings(BaseModel):
    settings: Dict[str, Any]


class ProviderWithSettings(BaseModel):
    providers: List[Dict[str, Dict[str, Any]]]


class EmbedderResponse(BaseModel):
    embedders: List[str]


class AgentResponse(BaseModel):
    message: str


class AgentListResponse(BaseModel):
    agents: List[Dict[str, Any]]


class AgentConfigResponse(BaseModel):
    agent: Dict[str, Any]


class AgentCommandsResponse(BaseModel):
    commands: Dict[str, bool]


class AgentBrowsedLinksResponse(BaseModel):
    links: List[Dict[str, Any]]


class AgentPromptResponse(BaseModel):
    response: str


class ChainStepDetail(BaseModel):
    step: int
    agent_name: str
    prompt_type: str
    prompt: Dict[str, Any]


class ChainDetailsResponse(BaseModel):
    id: str
    chain_name: str
    steps: List[ChainStepDetail]

    class Config:
        from_attributes = True


class CommandExecution(BaseModel):
    command_name: str
    command_args: Dict[str, Any] = {}
    conversation_name: Optional[str] = None


class ExtensionSettings(BaseModel):
    extension_settings: Dict[str, Dict[str, Any]]


class CommandArgs(BaseModel):
    command_args: Dict[str, Any]


class Extension(BaseModel):
    extension_name: str
    description: str
    settings: List[str]
    commands: List[Dict[str, Any]]


class ExtensionsModel(BaseModel):
    extensions: List[Extension]


class PromptArgsResponse(BaseModel):
    prompt_args: List[str]


# Add these to Models.py if not already present
class ConversationListResponse(BaseModel):
    conversations: List[str]
    conversations_with_ids: Dict[str, str]


class ConversationDetailResponse(BaseModel):
    conversations: Dict[str, Dict[str, Any]]


class ConversationHistoryResponse(BaseModel):
    conversation_history: List[Dict[str, Any]]


class NewConversationHistoryResponse(BaseModel):
    id: str
    conversation_history: List[Dict[str, Any]]


class NotificationResponse(BaseModel):
    notifications: List[Dict[str, Any]]


class MessageIdResponse(BaseModel):
    message: str  # Contains the message ID


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]


class EmbeddingData(BaseModel):
    embedding: List[float]
    index: int
    object: str = "embedding"


class EmbeddingResponse(BaseModel):
    data: List[EmbeddingData]
    model: str
    object: str = "list"
    usage: Dict[str, int]


class AudioTranscriptionResponse(BaseModel):
    text: str


class AudioTranslationResponse(BaseModel):
    text: str


class TextToSpeechResponse(BaseModel):
    url: str


class ImageGenerationResponse(BaseModel):
    created: int
    data: List[Dict[str, str]]


class MemoryResponse(BaseModel):
    memories: List[Dict[str, Any]]


class MemoryCollectionResponse(BaseModel):
    external_sources: List[str]


class DPOResponse(BaseModel):
    prompt: str
    chosen: str
    rejected: str


class NewCompanyInput(BaseModel):
    name: str
    parent_company_id: Optional[str] = None
    agent_name: Optional[str] = getenv("AGENT_NAME")
    status: Optional[bool] = True
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None


class UpdateUserRole(BaseModel):
    role_id: int
    company_id: str
    user_id: str


class RenameCompanyInput(BaseModel):
    name: str


class UpdateCompanyInput(BaseModel):
    name: Optional[str] = None
    status: Optional[bool] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None


# Wallet Models
class WalletResponseModel(BaseModel):
    private_key: str
    passphrase: str


# Webhook System Models
class WebhookIncomingCreate(BaseModel):
    """Model for creating an incoming webhook"""

    name: str
    agent_id: str
    description: Optional[str] = None
    active: Optional[bool] = True


class WebhookIncomingUpdate(BaseModel):
    """Model for updating an incoming webhook"""

    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class WebhookIncomingResponse(BaseModel):
    """Response model for incoming webhook details"""

    webhook_id: str
    name: str
    agent_id: str
    api_key: str
    webhook_url: str  # Full URL for the webhook endpoint
    description: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookOutgoingCreate(BaseModel):
    """Model for creating an outgoing webhook subscription"""

    name: str
    target_url: str
    event_types: List[str]  # List of event types to subscribe to
    headers: Optional[Dict[str, str]] = {}  # Custom headers to include
    secret: Optional[str] = None  # Secret for webhook signature verification
    retry_count: Optional[int] = 3
    retry_delay: Optional[int] = 60  # Seconds between retries
    timeout: Optional[int] = 30  # Request timeout in seconds
    active: Optional[bool] = True
    filters: Optional[Dict[str, Any]] = {}  # Event filters (e.g., agent_name, user_id)


class WebhookOutgoingUpdate(BaseModel):
    """Model for updating an outgoing webhook"""

    name: Optional[str] = None
    target_url: Optional[str] = None
    event_types: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    secret: Optional[str] = None
    retry_count: Optional[int] = None
    retry_delay: Optional[int] = None
    timeout: Optional[int] = None
    active: Optional[bool] = None
    filters: Optional[Dict[str, Any]] = None


class WebhookOutgoingResponse(BaseModel):
    """Response model for outgoing webhook details"""

    id: str
    name: str
    target_url: str
    event_types: List[str]
    headers: Dict[str, str]
    secret: Optional[str] = None
    retry_count: int
    retry_delay: int
    timeout: int
    active: bool
    filters: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    consecutive_failures: int
    total_events_sent: int
    successful_deliveries: int
    failed_deliveries: int

    class Config:
        from_attributes = True


class WebhookEventPayload(BaseModel):
    """Standard payload structure for webhook events"""

    event_id: str
    event_type: str  # e.g., "command.executed", "chat.completed", "agent.created"
    timestamp: datetime
    user_id: str
    company_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    data: Dict[str, Any]  # Event-specific data
    metadata: Optional[Dict[str, Any]] = {}  # Additional metadata


class WebhookLogResponse(BaseModel):
    """Response model for webhook log entries"""

    id: str
    direction: str  # "incoming" or "outgoing"
    webhook_id: str
    payload: Optional[str] = None  # JSON payload as string
    response: Optional[str] = None  # Response data as string
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    retry_count: int
    timestamp: datetime

    class Config:
        from_attributes = True


class WebhookTestPayload(BaseModel):
    """Model for testing webhook endpoints"""

    webhook_id: str
    event_type: Optional[str] = "webhook.test"  # Allow custom event type
    test_payload: Optional[Dict[str, Any]] = {
        "test": True,
        "message": "Test webhook payload",
    }


class WebhookStatistics(BaseModel):
    """Statistics for webhook usage"""

    webhook_id: str
    webhook_type: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_processing_time_ms: float
    last_request_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class WebhookEventTypeList(BaseModel):
    """Available webhook event types"""

    event_types: List[Dict[str, str]]  # List of {type, description}
