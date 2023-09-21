import uvicorn
import os
import logging
import base64
import string
import random
import time
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from Interactions import Interactions, get_tokens
from Embedding import Embedding
from ApiClient import DB_CONNECTED
from dotenv import load_dotenv

load_dotenv()
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", None)

if DB_CONNECTED:
    from db.Agent import Agent, add_agent, delete_agent, rename_agent, get_agents
    from db.Chain import Chain
    from db.Prompts import Prompts
    from db.History import (
        get_conversation,
        delete_history,
        delete_message,
        get_conversations,
        new_conversation,
        log_interaction,
    )
else:
    from fb.Agent import Agent, add_agent, delete_agent, rename_agent, get_agents
    from fb.Chain import Chain
    from fb.Prompts import Prompts
    from fb.History import (
        get_conversation,
        delete_history,
        delete_message,
        get_conversations,
        new_conversation,
        log_interaction,
    )


from typing import Optional, Dict, List, Any
from Providers import get_provider_options, get_providers
from Embedding import get_embedding_providers, get_embedders
from Extensions import Extensions
from Chains import Chains
from readers.github import GithubReader
from readers.file import FileReader
from readers.website import WebsiteReader
from readers.arxiv import ArxivReader

os.environ["TOKENIZERS_PARALLELISM"] = "false"

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "version"), encoding="utf-8") as f:
    version = f.read().strip()

logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

app = FastAPI(
    title="AGiXT",
    description="AGiXT is an Artificial Intelligence Automation platform for creating and managing AI agents. Visit the GitHub repo for more information or to report issues. https://github.com/Josh-XT/AGiXT/",
    version=version,
    docs_url="/",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(authorization: str = Header(None)):
    # Check if the API key is set up in the environment
    if AGIXT_API_KEY:
        # If no authorization header is provided, raise an error
        if authorization is None:
            raise HTTPException(
                status_code=400, detail="Authorization header is missing"
            )
        scheme, _, api_key = authorization.partition(" ")
        # If the scheme isn't "Bearer", raise an error
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=400, detail="Authorization scheme is not Bearer"
            )
        # If the provided API key doesn't match the expected one, raise an error
        if api_key != AGIXT_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API Key")
        return api_key
    else:
        return 1


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
    # Everything in this class except prompt, n, and model (agent_name) are unused currently.
    prompt: str
    max_tokens: int = 100
    temperature: float = 0.9
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    logprobs: int = None
    stop: List[str] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    best_of: int = 1
    echo: bool = False
    user: str = None
    model: str = None  # Model is actually the agent_name
    stop_sequence: List[str] = None
    metadata: Dict[str, str] = None


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


class EmbeddingModel(BaseModel):
    input: str
    model: str


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


@app.get("/api/provider", tags=["Provider"], dependencies=[Depends(verify_api_key)])
async def getproviders():
    providers = get_providers()
    return {"providers": providers}


@app.get(
    "/api/provider/{provider_name}",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_provider_settings(provider_name: str):
    settings = get_provider_options(provider_name=provider_name)
    return {"settings": settings}


# Gets list of embedding providers
@app.get(
    "/api/embedding_providers",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_embed_providers():
    providers = get_embedding_providers()
    return {"providers": providers}


# Gets embedders with their details such as required parameters and chunk sizes
@app.get(
    "/api/embedders",
    tags=["Provider"],
    dependencies=[Depends(verify_api_key)],
)
async def get_embedder_info() -> Dict[str, Any]:
    return {"embedders": get_embedders()}


@app.post("/api/agent", tags=["Agent"], dependencies=[Depends(verify_api_key)])
async def addagent(agent: AgentSettings) -> Dict[str, str]:
    return add_agent(agent_name=agent.agent_name, provider_settings=agent.settings)


@app.post("/api/agent/import", tags=["Agent"], dependencies=[Depends(verify_api_key)])
async def import_agent(agent: AgentConfig) -> Dict[str, str]:
    return add_agent(
        agent_name=agent.agent_name,
        provider_settings=agent.settings,
        commands=agent.commands,
    )


@app.patch(
    "/api/agent/{agent_name}", tags=["Agent"], dependencies=[Depends(verify_api_key)]
)
async def renameagent(agent_name: str, new_name: AgentNewName) -> ResponseMessage:
    rename_agent(agent_name=agent_name, new_name=new_name.new_name)
    return ResponseMessage(message="Agent renamed.")


@app.put(
    "/api/agent/{agent_name}", tags=["Agent"], dependencies=[Depends(verify_api_key)]
)
async def update_agent_settings(
    agent_name: str, settings: AgentSettings
) -> ResponseMessage:
    update_config = Agent(agent_name=agent_name).update_agent_config(
        new_config=settings.settings, config_key="settings"
    )
    return ResponseMessage(message=update_config)


# Get memories
@app.post(
    "/api/agent/{agent_name}/memory/{collection_number}/query",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def query_memories(
    agent_name: str, memory: AgentMemoryQuery, collection_number=0
) -> Dict[str, Any]:
    try:
        collection_number = int(collection_number)
    except:
        collection_number = 0
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    memories = await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=collection_number,
    ).get_memories_data(
        user_input=memory.user_input,
        limit=memory.limit,
        min_relevance_score=memory.min_relevance_score,
    )
    return {"memories": memories}


@app.post(
    "/api/agent/{agent_name}/learn/text",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_text(agent_name: str, data: TextMemoryInput) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=data.collection_number,
    ).write_text_to_memory(
        user_input=data.user_input, text=data.text, external_source="user input"
    )
    return ResponseMessage(
        message="Agent learned the content from the text assocated with the user input."
    )


@app.post(
    "/api/agent/{agent_name}/learn/file",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_file(agent_name: str, file: FileInput) -> ResponseMessage:
    # Strip any path information from the file name
    file.file_name = os.path.basename(file.file_name)
    base_path = os.path.join(os.getcwd(), "WORKSPACE")
    file_path = os.path.normpath(os.path.join(base_path, file.file_name))
    if not file_path.startswith(base_path):
        raise Exception("Path given not allowed")
    file_content = base64.b64decode(file.file_content)
    with open(file_path, "wb") as f:
        f.write(file_content)
    try:
        agent_config = Agent(agent_name=agent_name).get_agent_config()
        await FileReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=file.collection_number,
        ).write_file_to_memory(file_path=file_path)
        try:
            os.remove(file_path)
        except Exception:
            pass
        return ResponseMessage(message="Agent learned the content from the file.")
    except Exception as e:
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/agent/{agent_name}/learn/url",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_url(agent_name: str, url: UrlInput) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=url.collection_number,
    ).write_website_to_memory(url=url.url)
    return ResponseMessage(message="Agent learned the content from the url.")


@app.post(
    "/api/agent/{agent_name}/learn/github",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_github_repo(agent_name: str, git: GitHubInput) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    await GithubReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=git.collection_number,
        use_agent_settings=git.use_agent_settings,
    ).write_github_repository_to_memory(
        github_repo=git.github_repo,
        github_user=git.github_user,
        github_token=git.github_token,
        github_branch=git.github_branch,
    )
    return ResponseMessage(
        message="Agent learned the content from the GitHub Repository."
    )


@app.post(
    "/api/agent/{agent_name}/learn/arxiv",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_arxiv(agent_name: str, arxiv_input: ArxivInput) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    await ArxivReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=arxiv_input.collection_number,
    ).write_arxiv_articles_to_memory(
        query=arxiv_input.query,
        article_ids=arxiv_input.article_ids,
        max_articles=arxiv_input.max_articles,
    )
    return ResponseMessage(message="Agent learned the content from the arXiv articles.")


@app.post(
    "/api/agent/{agent_name}/reader/{reader_name}",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def agent_reader(
    agent_name: str, reader_name: str, data: dict
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    collection_number = data["collection_number"] if "collection_number" in data else 0
    if reader_name == "file":
        response = await FileReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        ).write_file_to_memory(file_path=data["file_path"])
    elif reader_name == "website":
        response = await WebsiteReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        ).write_website_to_memory(url=data["url"])
    elif reader_name == "github":
        response = await GithubReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
            use_agent_settings=data["use_agent_settings"]
            if "use_agent_settings" in data
            else False,
        ).write_github_repository_to_memory(
            github_repo=data["github_repo"],
            github_user=data["github_user"] if "github_user" in data else None,
            github_token=data["github_token"] if "github_token" in data else None,
            github_branch=data["github_branch"] if "github_branch" in data else "main",
        )
    elif reader_name == "arxiv":
        response = await ArxivReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        ).write_arxiv_articles_to_memory(
            query=data["query"],
            article_ids=data["article_ids"],
            max_articles=data["max_articles"],
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid reader name.")
    if response == True:
        return ResponseMessage(
            message=f"Agent learned the content from the {reader_name}."
        )
    else:
        return ResponseMessage(message=f"Agent failed to learn the content.")


@app.delete(
    "/api/agent/{agent_name}/memory",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def wipe_agent_memories(agent_name: str) -> ResponseMessage:
    await WebsiteReader(agent_name=agent_name, collection_number=0).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.delete(
    "/api/agent/{agent_name}/memory/{collection_number}",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def wipe_agent_memories(agent_name: str, collection_number=0) -> ResponseMessage:
    try:
        collection_number = int(collection_number)
    except:
        collection_number = 0
    await WebsiteReader(
        agent_name=agent_name, collection_number=collection_number
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.delete(
    "/api/agent/{agent_name}/memory/{collection_number}/{memory_id}",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_agent_memory(
    agent_name: str, collection_number=0, memory_id=""
) -> ResponseMessage:
    try:
        collection_number = int(collection_number)
    except:
        collection_number = 0
    await WebsiteReader(
        agent_name=agent_name, collection_number=collection_number
    ).delete_memory(key=memory_id)
    return ResponseMessage(
        message=f"Memory {memory_id} for agent {agent_name} deleted."
    )


@app.put(
    "/api/agent/{agent_name}/commands",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def update_agent_commands(
    agent_name: str, commands: AgentCommands
) -> ResponseMessage:
    update_config = Agent(agent_name=agent_name).update_agent_config(
        new_config=commands.commands, config_key="commands"
    )
    return ResponseMessage(message=update_config)


@app.delete(
    "/api/agent/{agent_name}", tags=["Agent"], dependencies=[Depends(verify_api_key)]
)
async def deleteagent(agent_name: str) -> ResponseMessage:
    delete_agent(agent_name=agent_name)
    return ResponseMessage(message=f"Agent {agent_name} deleted.")


@app.get("/api/agent", tags=["Agent"])
async def getagents():
    agents = get_agents()
    return {"agents": agents}


@app.get(
    "/api/agent/{agent_name}", tags=["Agent"], dependencies=[Depends(verify_api_key)]
)
async def get_agentconfig(agent_name: str):
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    return {"agent": agent_config}


@app.get(
    "/api/{agent_name}/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list(agent_name: str):
    conversations = get_conversations(
        agent_name=agent_name,
    )
    if conversations is None:
        conversations = []
    return {"conversations": conversations}


@app.get(
    "/api/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list():
    conversations = get_conversations(
        agent_name="OpenAI",
    )
    if conversations is None:
        conversations = []
    return {"conversations": conversations}


@app.get(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(history: HistoryModel):
    conversation_history = get_conversation(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
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
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_data(
    conversation_name: str, agent_name: str = "OpenAI", limit: int = 100, page: int = 1
):
    conversation_history = get_conversation(
        agent_name=agent_name,
        conversation_name=conversation_name,
        limit=limit,
        page=page,
    )

    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


@app.post(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def new_conversation_history(history: ConversationHistoryModel):
    new_conversation(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
        conversation_content=history.conversation_content,
    )
    return {"conversation_history": history.conversation_content}


@app.delete(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_history(
    history: ConversationHistoryModel,
) -> ResponseMessage:
    delete_history(
        agent_name=history.agent_name, conversation_name=history.conversation_name
    )
    return ResponseMessage(
        message=f"Conversation `{history.conversation_name}` for agent {history.agent_name} deleted."
    )


@app.delete(
    "/api/conversation/message",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_history_message(
    history: ConversationHistoryMessageModel,
) -> ResponseMessage:
    delete_message(
        agent_name=history.agent_name,
        message=history.message,
        conversation_name=history.conversation_name,
    )
    return ResponseMessage(message=f"Message deleted.")


@app.post(
    "/api/agent/{agent_name}/prompt",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def prompt_agent(agent_name: str, agent_prompt: AgentPrompt):
    agent = Interactions(agent_name=agent_name)
    response = await agent.run(
        prompt=agent_prompt.prompt_name,
        **agent_prompt.prompt_args,
    )
    return {"response": str(response)}


@app.post(
    "/api/v1/completions", tags=["Completions"], dependencies=[Depends(verify_api_key)]
)
async def completion(prompt: Completions):
    # prompt.model is the agent name
    agent = Interactions(agent_name=prompt.model)
    agent_config = agent.agent.AGENT_CONFIG
    if "settings" in agent_config:
        if "AI_MODEL" in agent_config["settings"]:
            model = agent_config["settings"]["AI_MODEL"]
        else:
            model = "undefined"
    else:
        model = "undefined"
    response = await agent.run(
        user_input=prompt.prompt,
        prompt="Custom Input",
        context_results=3,
        shots=prompt.n,
    )
    characters = string.ascii_letters + string.digits
    prompt_tokens = get_tokens(prompt.prompt)
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    random_chars = "".join(random.choice(characters) for _ in range(15))
    res_model = {
        "id": f"cmpl-{random_chars}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "text": response,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    return res_model


@app.post(
    "/api/v1/chat/completions",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
)
async def chat_completion(prompt: Completions):
    # prompt.model is the agent name
    agent = Interactions(agent_name=prompt.model)
    agent_config = agent.agent.AGENT_CONFIG
    if "settings" in agent_config:
        if "AI_MODEL" in agent_config["settings"]:
            model = agent_config["settings"]["AI_MODEL"]
        else:
            model = "undefined"
    else:
        model = "undefined"
    response = await agent.run(
        user_input=prompt.prompt,
        prompt="Custom Input",
        context_results=3,
        shots=prompt.n,
    )
    characters = string.ascii_letters + string.digits
    prompt_tokens = get_tokens(prompt.prompt)
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    random_chars = "".join(random.choice(characters) for _ in range(15))
    res_model = {
        "id": f"chatcmpl-{random_chars}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": [
                    {
                        "role": "assistant",
                        "content": response,
                    },
                ],
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    return res_model


# Use agent name in the model field to use embedding.
@app.post(
    "/api/v1/embedding", tags=["Completions"], dependencies=[Depends(verify_api_key)]
)
async def embedding(embedding: EmbeddingModel):
    agent_name = embedding.model
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    agent_settings = agent_config["settings"] if "settings" in agent_config else None
    tokens = get_tokens(embedding.input)
    embedding = Embedding(agent_settings=agent_settings).embed_text(
        text=embedding.input
    )
    return {
        "data": [{"embedding": embedding, "index": 0, "object": "embedding"}],
        "model": agent_name,
        "object": "list",
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


@app.get(
    "/api/agent/{agent_name}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def get_commands(agent_name: str):
    agent = Agent(agent_name=agent_name)
    return {"commands": agent.AGENT_CONFIG["commands"]}


@app.patch(
    "/api/agent/{agent_name}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def toggle_command(
    agent_name: str, payload: ToggleCommandPayload
) -> ResponseMessage:
    agent = Agent(agent_name=agent_name)
    try:
        if payload.command_name == "*":
            for each_command_name in agent.AGENT_CONFIG["commands"]:
                agent.AGENT_CONFIG["commands"][each_command_name] = payload.enable

            agent.update_agent_config(
                new_config=agent.AGENT_CONFIG["commands"], config_key="commands"
            )
            return ResponseMessage(
                message=f"All commands enabled for agent '{agent_name}'."
            )
        else:
            agent.AGENT_CONFIG["commands"][payload.command_name] = payload.enable
            agent.update_agent_config(
                new_config=agent.AGENT_CONFIG["commands"], config_key="commands"
            )
            return ResponseMessage(
                message=f"Command '{payload.command_name}' toggled for agent '{agent_name}'."
            )
    except Exception as e:
        logging.info(e)
        raise HTTPException(
            status_code=500,
            detail=f"Error enabling all commands for agent '{agent_name}': {str(e)}",
        )


@app.get("/api/chain", tags=["Chain"], dependencies=[Depends(verify_api_key)])
async def get_chains():
    chains = Chain().get_chains()
    return chains


@app.get(
    "/api/chain/{chain_name}", tags=["Chain"], dependencies=[Depends(verify_api_key)]
)
async def get_chain(chain_name: str):
    # try:
    chain_data = Chain().get_chain(chain_name=chain_name)
    return {"chain": chain_data}
    # except:
    #    raise HTTPException(status_code=404, detail="Chain not found")


@app.get("/api/chain/{chain_name}/responses", tags=["Chain"])
async def get_chain_responses(chain_name: str):
    try:
        chain_data = Chain().get_step_response(chain_name=chain_name, step_number="all")
        return {"chain": chain_data}
    except:
        raise HTTPException(status_code=404, detail="Chain not found")


@app.post(
    "/api/chain/{chain_name}/run",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def run_chain(chain_name: str, user_input: RunChain):
    chain_response = await Chains().run_chain(
        chain_name=chain_name,
        user_input=user_input.prompt,
        agent_override=user_input.agent_override,
        all_responses=user_input.all_responses,
        from_step=user_input.from_step,
        chain_args=user_input.chain_args,
    )
    try:
        if "Chain failed to complete" in chain_response:
            raise HTTPException(status_code=500, detail=f"{chain_response}")
    except:
        return f"{chain_response}"
    return chain_response


@app.post(
    "/api/chain/{chain_name}/run/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def run_chain_step(chain_name: str, step_number: str, user_input: RunChainStep):
    chain = Chain()
    chain_steps = chain.get_chain(chain_name=chain_name)
    try:
        step = chain_steps["step"][step_number]
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Step {step_number} not found. {e}"
        )
    chain_step_response = await Chains().run_chain_step(
        step=step,
        chain_name=chain_name,
        user_input=user_input.prompt,
        agent_override=user_input.agent_override,
        chain_args=user_input.chain_args,
    )
    if chain_step_response == None:
        raise HTTPException(
            status_code=500,
            detail=f"Error running step {step_number} in chain {chain_name}",
        )
    if "Chain failed to complete" in chain_step_response:
        raise HTTPException(status_code=500, detail=chain_step_response)
    return chain_step_response


# Get chain args
@app.get(
    "/api/chain/{chain_name}/args",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def get_chain_args(chain_name: str):
    chain_args = Chains().get_chain_args(chain_name=chain_name)
    return {"chain_args": chain_args}


@app.post("/api/chain", tags=["Chain"], dependencies=[Depends(verify_api_key)])
async def add_chain(chain_name: ChainName) -> ResponseMessage:
    Chain().add_chain(chain_name=chain_name.chain_name)
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")


@app.post("/api/chain/import", tags=["Chain"], dependencies=[Depends(verify_api_key)])
async def importchain(chain: ChainData) -> ResponseMessage:
    response = Chain().import_chain(chain_name=chain.chain_name, steps=chain.steps)
    return ResponseMessage(message=response)


@app.put(
    "/api/chain/{chain_name}", tags=["Chain"], dependencies=[Depends(verify_api_key)]
)
async def rename_chain(chain_name: str, new_name: ChainNewName) -> ResponseMessage:
    Chain().rename_chain(chain_name=chain_name, new_name=new_name.new_name)
    return ResponseMessage(
        message=f"Chain '{chain_name}' renamed to '{new_name.new_name}'."
    )


@app.delete(
    "/api/chain/{chain_name}", tags=["Chain"], dependencies=[Depends(verify_api_key)]
)
async def delete_chain(chain_name: str) -> ResponseMessage:
    Chain().delete_chain(chain_name=chain_name)
    return ResponseMessage(message=f"Chain '{chain_name}' deleted.")


@app.post(
    "/api/chain/{chain_name}/step",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def add_step(chain_name: str, step_info: StepInfo) -> ResponseMessage:
    Chain().add_chain_step(
        chain_name=chain_name,
        step_number=step_info.step_number,
        prompt_type=step_info.prompt_type,
        prompt=step_info.prompt,
        agent_name=step_info.agent_name,
    )
    return {"message": f"Step {step_info.step_number} added to chain '{chain_name}'."}


@app.put(
    "/api/chain/{chain_name}/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def update_step(
    chain_name: str, step_number: int, chain_step: ChainStep
) -> ResponseMessage:
    Chain().update_step(
        chain_name=chain_name,
        step_number=chain_step.step_number,
        prompt_type=chain_step.prompt_type,
        prompt=chain_step.prompt,
        agent_name=chain_step.agent_name,
    )
    return {
        "message": f"Step {chain_step.step_number} updated for chain '{chain_name}'."
    }


@app.patch(
    "/api/chain/{chain_name}/step/move",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def move_step(
    chain_name: str, chain_step_new_info: ChainStepNewInfo
) -> ResponseMessage:
    Chain().move_step(
        chain_name=chain_name,
        current_step_number=chain_step_new_info.old_step_number,
        new_step_number=chain_step_new_info.new_step_number,
    )
    return {
        "message": f"Step {chain_step_new_info.old_step_number} moved to {chain_step_new_info.new_step_number} in chain '{chain_name}'."
    }


@app.delete(
    "/api/chain/{chain_name}/step/{step_number}",
    tags=["Chain"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_step(chain_name: str, step_number: int) -> ResponseMessage:
    Chain().delete_step(chain_name=chain_name, step_number=step_number)
    return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}


@app.post(
    "/api/prompt/{prompt_category}",
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def add_prompt(
    prompt: CustomPromptModel, prompt_category: str = "Default"
) -> ResponseMessage:
    try:
        Prompts().add_prompt(
            prompt_name=prompt.prompt_name,
            prompt=prompt.prompt,
            prompt_category=prompt_category,
        )
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' added.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Prompt"],
    response_model=CustomPromptModel,
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_with_category(prompt_name: str, prompt_category: str = "Default"):
    prompt_content = Prompts().get_prompt(
        prompt_name=prompt_name, prompt_category=prompt_category
    )
    return {
        "prompt_name": prompt_name,
        "prompt_category": prompt_category,
        "prompt": prompt_content,
    }


@app.get(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Prompt"],
    response_model=CustomPromptModel,
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt(prompt_name: str, prompt_category: str = "Default"):
    prompt_content = Prompts().get_prompt(
        prompt_name=prompt_name, prompt_category=prompt_category
    )
    return {"prompt_name": prompt_name, "prompt": prompt_content}


@app.get(
    "/api/prompt",
    response_model=PromptList,
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts():
    prompts = Prompts().get_prompts()
    return {"prompts": prompts}


# Get prompt categories
@app.get(
    "/api/prompt/categories",
    response_model=PromptCategoryList,
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_categories():
    prompt_categories = Prompts().get_prompt_categories()
    return {"prompt_categories": prompt_categories}


@app.get(
    "/api/prompt/{prompt_category}",
    response_model=PromptList,
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts(prompt_category: str = "Default"):
    prompts = Prompts().get_prompts(prompt_category=prompt_category)
    return {"prompts": prompts}


@app.delete(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_prompt(
    prompt_name: str, prompt_category: str = "Default"
) -> ResponseMessage:
    try:
        Prompts().delete_prompt(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        return ResponseMessage(message=f"Prompt '{prompt_name}' deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# Rename prompt
@app.patch(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def rename_prompt(
    prompt_name: str, new_name: PromptName, prompt_category: str = "Default"
) -> ResponseMessage:
    try:
        Prompts().rename_prompt(
            prompt_name=prompt_name,
            new_name=new_name.prompt_name,
            prompt_category=prompt_category,
        )
        return ResponseMessage(
            message=f"Prompt '{prompt_name}' renamed to '{new_name.prompt_name}'."
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def update_prompt(
    prompt: CustomPromptModel, prompt_category: str = "Default"
) -> ResponseMessage:
    try:
        Prompts().update_prompt(
            prompt_name=prompt.prompt_name,
            prompt=prompt.prompt,
            prompt_category=prompt_category,
        )
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get(
    "/api/prompt/{prompt_category}/{prompt_name}/args",
    tags=["Prompt"],
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_arg(prompt_name: str, prompt_category: str = "Default"):
    prompt_name = prompt_name.replace("%20", " ")
    prompt = Prompts().get_prompt(prompt_name=prompt_name, prompt_category="Default")
    return {"prompt_args": Prompts().get_prompt_args(prompt)}


@app.get(
    "/api/extensions/settings",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def get_extension_settings():
    try:
        return {"extension_settings": Extensions().get_extension_settings()}
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to retrieve settings.")


@app.get(
    "/api/extensions/{command_name}/args",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def get_command_args(command_name: str):
    return {"command_args": Extensions().get_command_args(command_name=command_name)}


@app.get("/api/extensions", tags=["Extensions"], dependencies=[Depends(verify_api_key)])
async def get_extensions():
    extensions = Extensions().get_extensions()
    return {"extensions": extensions}


class CommandExecution(BaseModel):
    command_name: str
    command_args: dict
    conversation_name: str = "AGiXT Terminal Command Execution"


@app.post(
    "/api/agent/{agent_name}/command",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def run_command(agent_name: str, command: CommandExecution):
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    command_output = await Extensions(
        agent_name=agent_name,
        agent_config=agent_config,
        conversation_name=command.conversation_name,
    ).execute_command(
        command_name=command.command_name, command_args=command.command_args
    )
    log_interaction(
        agent_name=agent_name,
        conversation_name=command.conversation_name,
        role=agent_name,
        message=command_output,
    )
    return {
        "response": command_output,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7437)
