import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from Interactions import Interactions
from Agent import Agent, add_agent, delete_agent, rename_agent, get_agents
from Chain import Chain, import_chain
from Prompts import Prompts
from typing import Optional, Dict, List, Any
from provider import get_provider_options, get_providers
from Embedding import get_embedding_providers
from Extensions import Extensions
import os
import logging
import base64
import time
import string
import random

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


class AgentName(BaseModel):
    agent_name: str


class AgentNewName(BaseModel):
    new_name: str


class AgentPrompt(BaseModel):
    user_input: str
    prompt_name: str
    prompt_args: dict
    websearch: bool
    websearch_depth: int
    context_results: int


class Objective(BaseModel):
    objective: str


class Prompt(BaseModel):
    prompt: str


class PromptName(BaseModel):
    prompt_name: str


class PromptList(BaseModel):
    prompts: List[str]


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


class FileInput(BaseModel):
    file_name: str
    file_content: str


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


@app.get("/api/provider", tags=["Provider"])
async def getproviders():
    providers = get_providers()
    return {"providers": providers}


@app.get("/api/provider/{provider_name}", tags=["Provider"])
async def get_provider_settings(provider_name: str):
    settings = get_provider_options(provider_name=provider_name)
    return {"settings": settings}


@app.get("/api/embedding_providers", tags=["Provider"])
async def get_embed_providers():
    providers = get_embedding_providers()
    return {"providers": providers}


@app.post("/api/agent", tags=["Agent"])
async def addagent(agent: AgentSettings) -> Dict[str, str]:
    return add_agent(agent_name=agent.agent_name, provider_settings=agent.settings)


@app.post("/api/agent/import", tags=["Agent"])
async def import_agent(agent: AgentConfig) -> Dict[str, str]:
    return add_agent(
        agent_name=agent.agent_name,
        provider_settings=agent.settings,
        commands=agent.commands,
    )


@app.patch("/api/agent/{agent_name}", tags=["Agent"])
async def renameagent(agent_name: str, new_name: AgentNewName) -> ResponseMessage:
    rename_agent(agent_name=agent_name, new_name=new_name.new_name)
    return ResponseMessage(message="Agent renamed.")


@app.put("/api/agent/{agent_name}", tags=["Agent"])
async def update_agent_settings(
    agent_name: str, settings: AgentSettings
) -> ResponseMessage:
    update_config = Agent(agent_name=agent_name).update_agent_config(
        new_config=settings.settings, config_key="settings"
    )
    return ResponseMessage(message=update_config)


@app.post("/api/agent/{agent_name}/learn/file", tags=["Agent"])
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
        memories = Agent(agent_name=agent_name).get_memories()
        await memories.mem_read_file(file_path=file_path)
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


@app.post("/api/agent/{agent_name}/learn/url", tags=["Agent"])
async def learn_url(agent_name: str, url: UrlInput) -> ResponseMessage:
    try:
        memories = Agent(agent_name=agent_name).get_memories()
        await memories.read_website(url=url.url)
        return ResponseMessage(message="Agent learned the content from the url.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/agent/{agent_name}/commands", tags=["Agent"])
async def update_agent_commands(
    agent_name: str, commands: AgentCommands
) -> ResponseMessage:
    update_config = Agent(agent_name=agent_name).update_agent_config(
        new_config=commands.commands, config_key="commands"
    )
    return ResponseMessage(message=update_config)


@app.delete("/api/agent/{agent_name}", tags=["Agent"])
async def deleteagent(agent_name: str) -> ResponseMessage:
    delete_agent(agent_name=agent_name)
    return ResponseMessage(message=f"Agent {agent_name} deleted.")


@app.get("/api/agent", tags=["Agent"])
async def getagents():
    agents = get_agents()
    return {"agents": agents}


@app.get("/api/agent/{agent_name}", tags=["Agent"])
async def get_agentconfig(agent_name: str):
    agent_config = Agent(agent_name=agent_name).get_agent_config()
    return {"agent": agent_config}


@app.get("/api/{agent_name}/chat", tags=["Agent"])
async def get_chat_history(agent_name: str):
    chat_history = Agent(agent_name=agent_name).get_history()
    return {"chat_history": chat_history}


@app.delete("/api/agent/{agent_name}/history", tags=["Agent"])
async def delete_history(agent_name: str) -> ResponseMessage:
    Agent(agent_name=agent_name).delete_history()
    return ResponseMessage(message=f"History for agent {agent_name} deleted.")


@app.delete("/api/agent/{agent_name}/history/message", tags=["Agent"])
async def delete_history_message(
    agent_name: str, message: ResponseMessage
) -> ResponseMessage:
    Agent(agent_name=agent_name).delete_history_message(message.message)
    return ResponseMessage(message=f"Message deleted.")


@app.delete("/api/agent/{agent_name}/memory", tags=["Agent"])
async def wipe_agent_memories(agent_name: str) -> ResponseMessage:
    Agent(agent_name=agent_name).wipe_agent_memories()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.post("/api/agent/{agent_name}/instruct", tags=["Agent"])
async def instruct(agent_name: str, prompt: Prompt):
    agent = Interactions(agent_name=agent_name)
    response = await agent.run(
        user_input=prompt.prompt,
        prompt="instruct",
    )
    return {"response": str(response)}


@app.post("/api/agent/{agent_name}/prompt", tags=["Agent"])
async def prompt_agent(agent_name: str, agent_prompt: AgentPrompt):
    agent = Interactions(agent_name=agent_name)
    response = await agent.run(
        prompt=agent_prompt.prompt_name,
        websearch=agent_prompt.websearch,
        websearch_depth=agent_prompt.websearch_depth,
        context_results=agent_prompt.context_results,
        **agent_prompt.prompt_args,
    )
    return {"response": str(response)}


@app.post("/api/agent/{agent_name}/smartinstruct/{shots}", tags=["Agent"])
async def smartinstruct(agent_name: str, shots: int, prompt: Prompt):
    agent = Interactions(agent_name=agent_name)
    response = await agent.smart_instruct(user_input=prompt.prompt, shots=int(shots))
    return {"response": str(response)}


@app.post("/api/agent/{agent_name}/chat", tags=["Agent"])
async def chat(agent_name: str, prompt: Prompt):
    agent = Interactions(agent_name=agent_name)
    response = await agent.run(
        user_input=prompt.prompt, prompt="Chat", context_results=6
    )
    return {"response": str(response)}


@app.post("/api/v1/completions", tags=["Agent"])
async def completion(prompt: Completions):
    # prompt.model is the agent name
    agent = Interactions(agent_name=prompt.model)
    agent_config = Agent(agent_name=prompt.model).get_agent_config()
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
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    return res_model


@app.post("/api/v1/chat/completions", tags=["Agent"])
async def chat_completion(prompt: Completions):
    # prompt.model is the agent name
    agent = Interactions(agent_name=prompt.model)
    agent_config = Agent(agent_name=prompt.model).get_agent_config()
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
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    return res_model


@app.post("/api/agent/{agent_name}/smartchat/{shots}", tags=["Agent"])
async def smartchat(agent_name: str, shots: int, prompt: Prompt):
    agent = Interactions(agent_name=agent_name)
    response = await agent.smart_chat(user_input=prompt.prompt, shots=shots)
    return {"response": str(response)}


@app.get("/api/agent/{agent_name}/command", tags=["Agent"])
async def get_commands(agent_name: str):
    agent = Agent(agent_name=agent_name)
    return {"commands": agent.agent_config["commands"]}


@app.patch("/api/agent/{agent_name}/command", tags=["Agent"])
async def toggle_command(
    agent_name: str, payload: ToggleCommandPayload
) -> ResponseMessage:
    agent = Agent(agent_name=agent_name)
    try:
        if payload.command_name == "*":
            for each_command_name in agent.agent_config["commands"]:
                agent.agent_config["commands"][each_command_name] = payload.enable

            agent.update_agent_config(
                new_config=agent.agent_config["commands"], config_key="commands"
            )
            return ResponseMessage(
                message=f"All commands enabled for agent '{agent_name}'."
            )
        else:
            agent.agent_config["commands"][payload.command_name] = payload.enable
            agent.update_agent_config(
                new_config=agent.agent_config["commands"], config_key="commands"
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


@app.get("/api/chain", tags=["Chain"])
async def get_chains():
    chains = Chain().get_chains()
    return chains


@app.get("/api/chain/{chain_name}", tags=["Chain"])
async def get_chain(chain_name: str):
    try:
        chain_data = Chain().get_chain(chain_name=chain_name)
        return {"chain": chain_data}
    except:
        raise HTTPException(status_code=404, detail="Chain not found")


@app.get("/api/chain/{chain_name}/responses", tags=["Chain"])
async def get_chain_responses(chain_name: str):
    try:
        chain_data = Chain().get_step_response(chain_name=chain_name, step_number="all")
        return {"chain": chain_data}
    except:
        raise HTTPException(status_code=404, detail="Chain not found")


@app.post("/api/chain/{chain_name}/run", tags=["Chain"])
async def run_chain(chain_name: str, user_input: RunChain):
    chain_response = await Interactions(agent_name="").run_chain(
        chain_name=chain_name,
        user_input=user_input.prompt,
        agent_override=user_input.agent_override,
        all_responses=user_input.all_responses,
        from_step=user_input.from_step,
    )
    return chain_response


@app.post("/api/chain", tags=["Chain"])
async def add_chain(chain_name: ChainName) -> ResponseMessage:
    Chain().add_chain(chain_name=chain_name.chain_name)
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")


@app.post("/api/chain/import", tags=["Chain"])
async def importchain(chain: ChainData) -> ResponseMessage:
    print(chain)
    response = import_chain(chain_name=chain.chain_name, steps=chain.steps)
    return ResponseMessage(message=response)


@app.put("/api/chain/{chain_name}", tags=["Chain"])
async def rename_chain(chain_name: str, new_name: ChainNewName) -> ResponseMessage:
    Chain().rename_chain(chain_name=chain_name, new_name=new_name.new_name)
    return ResponseMessage(
        message=f"Chain '{chain_name}' renamed to '{new_name.new_name}'."
    )


@app.delete("/api/chain/{chain_name}", tags=["Chain"])
async def delete_chain(chain_name: str) -> ResponseMessage:
    Chain().delete_chain(chain_name=chain_name)
    return ResponseMessage(message=f"Chain '{chain_name}' deleted.")


@app.post("/api/chain/{chain_name}/step", tags=["Chain"])
async def add_step(chain_name: str, step_info: StepInfo) -> ResponseMessage:
    Chain().add_chain_step(
        chain_name=chain_name,
        step_number=step_info.step_number,
        prompt_type=step_info.prompt_type,
        prompt=step_info.prompt,
        agent_name=step_info.agent_name,
    )
    return {"message": f"Step {step_info.step_number} added to chain '{chain_name}'."}


@app.put("/api/chain/{chain_name}/step/{step_number}", tags=["Chain"])
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


@app.patch("/api/chain/{chain_name}/step/move", tags=["Chain"])
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


@app.delete("/api/chain/{chain_name}/step/{step_number}", tags=["Chain"])
async def delete_step(chain_name: str, step_number: int) -> ResponseMessage:
    Chain().delete_step(chain_name=chain_name, step_number=step_number)
    return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}


@app.post("/api/prompt", tags=["Prompt"])
async def add_prompt(prompt: CustomPromptModel) -> ResponseMessage:
    try:
        Prompts().add_prompt(prompt_name=prompt.prompt_name, prompt=prompt.prompt)
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' added.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/prompt/{prompt_name}", tags=["Prompt"], response_model=CustomPromptModel)
async def get_prompt(prompt_name: str):
    # try:
    prompt_content = Prompts().get_prompt(prompt_name=prompt_name)
    return {"prompt_name": prompt_name, "prompt": prompt_content}
    # except Exception as e:
    #    raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/prompt", response_model=PromptList, tags=["Prompt"])
async def get_prompts():
    prompts = Prompts().get_prompts()
    return {"prompts": prompts}


@app.delete("/api/prompt/{prompt_name}", tags=["Prompt"])
async def delete_prompt(prompt_name: str) -> ResponseMessage:
    try:
        Prompts().delete_prompt(prompt_name=prompt_name)
        return ResponseMessage(message=f"Prompt '{prompt_name}' deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/api/prompt/{prompt_name}", tags=["Prompt"])
async def update_prompt(prompt: CustomPromptModel) -> ResponseMessage:
    try:
        Prompts().update_prompt(prompt_name=prompt.prompt_name, prompt=prompt.prompt)
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/prompt/{prompt_name}/args", tags=["Prompt"])
async def get_prompt_arg(prompt_name: str):
    return {"prompt_args": Prompts().get_prompt_args(prompt_name)}


@app.get("/api/extensions/settings", tags=["Extensions"])
async def get_extension_settings():
    try:
        return {"extension_settings": Extensions().get_extension_settings()}
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to retrieve settings.")


@app.get("/api/extensions/{command_name}/args", tags=["Extension"])
async def get_command_args(command_name: str):
    return {"command_args": Extensions().get_command_args(command_name=command_name)}


@app.get("/api/extensions", tags=["Extension"])
async def get_extensions():
    return {"extensions": Extensions().get_extensions()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7437)
