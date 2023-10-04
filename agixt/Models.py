from pydantic import BaseModel
from typing import Optional, Dict, List, Any


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


class Completions(BaseModel):
    model: str = None  # Model is actually the agent_name
    prompt: str = None
    suffix: str = None
    max_tokens: int = 100
    temperature: float = 0.9
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    logprobs: int = None
    echo: bool = False
    stop: List[str] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    best_of: int = 1
    logit_bias: Dict[str, float] = None
    user: str = None


class ChatCompletions(BaseModel):
    model: str = None  # Model is actually the agent_name
    messages: List[dict] = None
    functions: List[dict] = None
    function_call: str = None
    temperature: float = 0.9
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    stop: List[str] = None
    max_tokens: int = 8192
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    logit_bias: Dict[str, float] = None
    user: str = None


class EmbeddingModel(BaseModel):
    input: str
    model: str
    user: str = None


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


class RunChainStep(BaseModel):
    prompt: str
    agent_override: Optional[str] = ""
    chain_args: Optional[dict] = {}


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
    collection_number: int = 0


class FileInput(BaseModel):
    file_name: str
    file_content: str
    collection_number: int = 0


class TextMemoryInput(BaseModel):
    user_input: str
    text: str
    collection_number: int = 0


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
    settings: Dict[str, Any]


class AgentConfig(BaseModel):
    agent_name: str
    settings: Dict[str, Any]
    commands: Dict[str, Any]


class AgentCommands(BaseModel):
    agent_name: str
    commands: Dict[str, Any]


class HistoryModel(BaseModel):
    agent_name: str
    conversation_name: str
    limit: int = 100
    page: int = 1


class ConversationHistoryModel(BaseModel):
    agent_name: str
    conversation_name: str
    conversation_content: List[dict] = []


class ConversationHistoryMessageModel(BaseModel):
    agent_name: str
    conversation_name: str
    message: str


class GitHubInput(BaseModel):
    github_repo: str
    github_user: str = None
    github_token: str = None
    github_branch: str = "main"
    use_agent_settings: bool = False
    collection_number: int = 0


class ArxivInput(BaseModel):
    query: str = None
    article_ids: str = None
    max_articles: int = 5
    collection_number: int = 0


class CommandExecution(BaseModel):
    command_name: str
    command_args: dict
    conversation_name: str = "AGiXT Terminal Command Execution"
