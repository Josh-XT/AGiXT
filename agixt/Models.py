from pydantic import BaseModel
from typing import Optional, Dict, List, Any, Union
from Globals import DEFAULT_USER


class AgentName(BaseModel):
    agent_name: str


class AgentNewName(BaseModel):
    new_name: str


class AgentPrompt(BaseModel):
    prompt_name: str
    prompt_args: dict


class AgentMemoryQuery(BaseModel):
    user_input: str
    limit: int = 5
    min_relevance_score: float = 0.0


class UserInput(BaseModel):
    user_input: str
    injected_memories: Optional[int] = 10


class LogInteraction(BaseModel):
    role: str
    message: str
    conversation_name: Optional[str] = ""


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


class ChatCompletions(BaseModel):
    model: str = "gpt-3.5-turbo"  # This is the agent name
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
    model: Optional[str] = "gpt4free"
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


class ChainNewName(BaseModel):
    new_name: str


class ChainName(BaseModel):
    chain_name: str


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


class ChainStep(BaseModel):
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: dict


class ChainStepNewInfo(BaseModel):
    old_step_number: int
    new_step_number: int


class ResponseMessage(BaseModel):
    message: str


class UrlInput(BaseModel):
    url: str
    collection_number: Optional[str] = "0"


class FileInput(BaseModel):
    file_name: str
    file_content: str
    collection_number: Optional[Any] = "0"


class TextMemoryInput(BaseModel):
    user_input: str
    text: str
    collection_number: Optional[str] = "0"


class FeedbackInput(BaseModel):
    user_input: str
    message: str
    feedback: str
    positive: Optional[bool] = True
    conversation_name: Optional[str] = ""


class TaskOutput(BaseModel):
    output: str
    message: Optional[str] = None


class ToggleCommandPayload(BaseModel):
    command_name: str
    enable: bool


class CustomPromptModel(BaseModel):
    prompt_name: str
    prompt: str


class AgentSettings(BaseModel):
    agent_name: str
    settings: Optional[Dict[str, Any]] = {}
    commands: Optional[Dict[str, Any]] = {}
    training_urls: Optional[List[str]] = []


class AgentConfig(BaseModel):
    agent_name: str
    settings: Dict[str, Any]
    commands: Dict[str, Any]


class AgentBrowsedLinks(BaseModel):
    agent_name: str
    links: List[Dict[str, Any]]


class AgentCommands(BaseModel):
    agent_name: str
    commands: Dict[str, Any]


class HistoryModel(BaseModel):
    agent_name: str
    conversation_name: str
    limit: int = 100
    page: int = 1


class ExternalSource(BaseModel):
    external_source: str
    collection_number: Optional[str] = "0"


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


class TTSInput(BaseModel):
    text: str


class WebhookModel(BaseModel):
    success: str


class ConversationHistoryMessageModel(BaseModel):
    agent_name: Optional[str] = ""
    conversation_name: str
    message: str


class UpdateConversationHistoryMessageModel(BaseModel):
    agent_name: Optional[str] = ""
    conversation_name: str
    message: str
    new_message: str


class UpdateMessageModel(BaseModel):
    conversation_name: str
    message_id: str
    new_message: str


class TranslationRequest(BaseModel):
    target_language_translated_text: str


class DeleteMessageModel(BaseModel):
    conversation_name: str


class TaskPlanInput(BaseModel):
    user_input: str
    websearch: Optional[bool] = False
    websearch_depth: Optional[int] = 3
    conversation_name: Optional[str] = "AGiXT Task Planning"
    log_user_input: Optional[bool] = True
    log_output: Optional[bool] = True
    enable_new_command: Optional[bool] = True


class TasksToDo(BaseModel):
    tasks: List[str]


class ChainCommandName(BaseModel):
    command_name: str


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


class YoutubeInput(BaseModel):
    video_id: str
    collection_number: Optional[str] = "0"


class CommandExecution(BaseModel):
    command_name: str
    command_args: dict
    conversation_name: str = "AGiXT Terminal Command Execution"


class WebhookUser(BaseModel):
    email: str
    agent_name: Optional[str] = ""
    settings: Optional[Dict[str, Any]] = {}
    commands: Optional[Dict[str, Any]] = {}
    training_urls: Optional[List[str]] = []
    github_repos: Optional[List[str]] = []
    zip_file_content: Optional[str] = ""


# Auth user models
class Login(BaseModel):
    email: str
    token: str


class Register(BaseModel):
    email: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


class UserInfo(BaseModel):
    first_name: str
    last_name: str


class Detail(BaseModel):
    detail: str
