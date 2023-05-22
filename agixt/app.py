import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from Config import Config
from AGiXT import AGiXT
from Agent import Agent
from Commands import Commands
from Chain import Chain
from Tasks import Tasks
from CustomPrompt import CustomPrompt
from typing import Optional, Dict, List, Any
from provider import get_provider_options
from Embedding import get_embedding_providers
import os

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "version"), encoding="utf-8") as f:
    version = f.read().strip()

CFG = Config()
app = FastAPI(
    title="AGiXT",
    description="AGiXT is an Artificial Intelligence Automation platform for creating and managing AI agents. Visit the GitHub repo for more information or to report issues. https://github.com/Josh-XT/AGiXT/",
    version=version,
    docs_url="/",
)
agent_threads = {}
agent_stop_events = {}

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


class Objective(BaseModel):
    objective: str


class Prompt(BaseModel):
    prompt: str


class PromptName(BaseModel):
    prompt_name: str


class PromptList(BaseModel):
    prompts: List[str]


class ChainNewName(BaseModel):
    new_name: str


class ChainName(BaseModel):
    chain_name: str


class StepInfo(BaseModel):
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: str


class ChainStep(BaseModel):
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: str


class ChainStepNewInfo(BaseModel):
    old_step_number: int
    new_step_number: int


class ResponseMessage(BaseModel):
    message: str


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


@app.get("/api/provider", tags=["Provider"])
async def get_providers():
    providers = CFG.get_providers()
    return {"providers": providers}


@app.get("/api/provider/{provider_name}", tags=["Provider"])
async def get_provider_settings(provider_name: str):
    settings = get_provider_options(provider_name)
    return {"settings": settings}


@app.get("/api/embedding_providers", tags=["Provider"])
async def get_embed_providers():
    providers = get_embedding_providers()
    return {"providers": providers}


@app.post("/api/agent", tags=["Agent"])
async def add_agent(agent: AgentSettings) -> Dict[str, str]:
    agent_info = Agent(agent.agent_name).add_agent(agent.agent_name, agent.settings)
    return {"message": "Agent added", "agent_file": agent_info["agent_file"]}


@app.patch("/api/agent/{agent_name}", tags=["Agent"])
async def rename_agent(agent_name: str, new_name: AgentNewName) -> ResponseMessage:
    Agent(agent_name).rename_agent(agent_name, new_name.new_name)
    return ResponseMessage(
        message=f"Agent {agent_name} renamed to {new_name.new_name}."
    )


@app.put("/api/agent/{agent_name}", tags=["Agent"])
async def update_agent_settings(
    agent_name: str, settings: AgentSettings
) -> ResponseMessage:
    update_config = Agent(agent_name).update_agent_config(settings.settings, "settings")
    return ResponseMessage(message=update_config)


@app.delete("/api/agent/{agent_name}", tags=["Agent"])
async def delete_agent(agent_name: str) -> ResponseMessage:
    result, status_code = Agent(agent_name).delete_agent(agent_name)
    if status_code == 200:
        return ResponseMessage(message=result["message"])
    else:
        raise HTTPException(status_code=status_code, detail=result["message"])


@app.get("/api/agent", tags=["Agent"])
async def get_agents():
    agents = CFG.get_agents()
    return {"agents": agents}


@app.get("/api/agent/{agent_name}", tags=["Agent"])
async def get_agentconfig(agent_name: str):
    agent_config = Agent(agent_name).get_agent_config()
    return {"agent": agent_config}


@app.get("/api/{agent_name}/chat", tags=["Agent"])
async def get_chat_history(agent_name: str):
    chat_history = Agent(agent_name).get_chat_history(agent_name)
    return {"chat_history": chat_history}


@app.delete("/api/agent/{agent_name}/memory", tags=["Agent"])
async def wipe_agent_memories(agent_name: str) -> ResponseMessage:
    Agent(agent_name).wipe_agent_memories(agent_name)
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.post("/api/agent/{agent_name}/instruct", tags=["Agent"])
async def instruct(agent_name: str, prompt: Prompt):
    agent = AGiXT(agent_name)
    response = agent.run(
        task=prompt.prompt,
        prompt="instruct",
    )
    return {"response": str(response)}


@app.post("/api/agent/{agent_name}/smartinstruct/{shots}", tags=["Agent"])
async def smartinstruct(agent_name: str, shots: int, prompt: Prompt):
    agent = AGiXT(agent_name)
    response = agent.smart_instruct(task=prompt.prompt, shots=int(shots))
    return {"response": str(response)}


@app.post("/api/agent/{agent_name}/chat", tags=["Agent"])
async def chat(agent_name: str, prompt: Prompt):
    agent = AGiXT(agent_name)
    response = agent.run(prompt.prompt, prompt="Chat", context_results=6)
    return {"response": str(response)}


@app.post("/api/agent/{agent_name}/smartchat/{shots}", tags=["Agent"])
async def smartchat(agent_name: str, shots: int, prompt: Prompt):
    agent = AGiXT(agent_name)
    response = agent.smart_chat(prompt.prompt, shots=shots)
    return {"response": str(response)}


@app.get("/api/agent/{agent_name}/command", tags=["Agent"])
async def get_commands(agent_name: str):
    commands = Commands(agent_name)
    available_commands = commands.get_available_commands()
    return {"commands": available_commands}


@app.patch("/api/agent/{agent_name}/command", tags=["Agent"])
async def toggle_command(
    agent_name: str, payload: ToggleCommandPayload
) -> ResponseMessage:
    agent = Agent(agent_name)
    try:
        if payload.command_name == "*":
            commands = Commands(agent_name)
            for each_command_name in commands.agent_config["commands"]:
                commands.agent_config["commands"][each_command_name] = payload.enable
            agent.update_agent_config(commands.agent_config["commands"], "commands")
            return ResponseMessage(
                message=f"All commands enabled for agent '{agent_name}'."
            )
        else:
            commands = Commands(agent_name)
            commands.agent_config["commands"][payload.command_name] = payload.enable
            agent.update_agent_config(commands.agent_config["commands"], "commands")
            return ResponseMessage(
                message=f"Command '{payload.command_name}' toggled for agent '{agent_name}'."
            )
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=500,
            detail=f"Error enabling all commands for agent '{agent_name}': {str(e)}",
        )


@app.post("/api/agent/{agent_name}/task", tags=["Agent"])
async def start_task_agent(agent_name: str, objective: Objective) -> ResponseMessage:
    # If it's running stop it.
    task_status = Tasks(agent_name).get_status()
    if task_status != False:
        Tasks(agent_name).stop_tasks()
        return ResponseMessage(message="Task agent stopped")
    # If it's not running start it.
    Tasks(agent_name).run_task(objective=objective.objective)
    return ResponseMessage(message="Task agent started")


@app.get("/api/agent/{agent_name}/task", tags=["Agent"])
async def get_task_output(agent_name: str) -> TaskOutput:
    task_output = Tasks(agent_name).get_task_output()
    if task_output != False:
        return TaskOutput(
            output=task_output,
            message="Task agent is not running",
        )
    else:
        return TaskOutput(
            output="",
            message="Task agent is not running",
        )


@app.get("/api/agent/{agent_name}/task/status", tags=["Agent"])
async def get_task_status(agent_name: str):
    task_status = Tasks(agent_name).get_status()
    return {"status": task_status}


@app.get("/api/chain", tags=["Chain"])
async def get_chains():
    chains = Chain().get_chains()
    return chains


@app.get("/api/chain/{chain_name}", tags=["Chain"])
async def get_chain(chain_name: str):
    chain_data = Chain().get_chain(chain_name)
    return {"chain": chain_data}


@app.post("/api/chain/{chain_name}/run", tags=["Chain"])
async def run_chain(chain_name: str) -> ResponseMessage:
    Chain().run_chain(chain_name)
    return {"message": f"Chain '{chain_name}' started."}


@app.post("/api/chain", tags=["Chain"])
async def add_chain(chain_name: ChainName) -> ResponseMessage:
    Chain().add_chain(chain_name.chain_name)
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")


@app.put("/api/chain/{chain_name}", tags=["Chain"])
async def rename_chain(chain_name: str, new_name: ChainNewName) -> ResponseMessage:
    Chain().rename_chain(chain_name, new_name.new_name)
    return ResponseMessage(
        message=f"Chain '{chain_name}' renamed to '{new_name.new_name}'."
    )


@app.delete("/api/chain/{chain_name}", tags=["Chain"])
async def delete_chain(chain_name: str) -> ResponseMessage:
    Chain().delete_chain(chain_name)
    return ResponseMessage(message=f"Chain '{chain_name}' deleted.")


@app.post("/api/chain/{chain_name}/step", tags=["Chain"])
async def add_step(chain_name: str, step_info: StepInfo) -> ResponseMessage:
    Chain().add_chain_step(
        chain_name,
        step_info.step_number,
        step_info.prompt_type,
        step_info.prompt,
        step_info.agent_name,
    )
    return {"message": f"Step {step_info.step_number} added to chain '{chain_name}'."}


@app.put("/api/chain/{chain_name}/step/{step_number}", tags=["Chain"])
async def update_step(
    chain_name: str, step_number: int, chain_step: ChainStep
) -> ResponseMessage:
    Chain().update_step(
        chain_name,
        chain_step.step_number,
        chain_step.prompt_type,
        chain_step.prompt,
        chain_step.agent_name,
    )
    return {
        "message": f"Step {chain_step.step_number} updated for chain '{chain_name}'."
    }


@app.patch("/api/chain/{chain_name}/step/move", tags=["Chain"])
async def move_step(
    chain_name: str, chain_step_new_info: ChainStepNewInfo
) -> ResponseMessage:
    Chain().move_step(
        chain_name,
        chain_step_new_info.old_step_number,
        chain_step_new_info.new_step_number,
    )
    return {
        "message": f"Step {chain_step_new_info.old_step_number} moved to {chain_step_new_info.new_step_number} in chain '{chain_name}'."
    }


@app.delete("/api/chain/{chain_name}/step/{step_number}", tags=["Chain"])
async def delete_step(chain_name: str, step_number: int) -> ResponseMessage:
    Chain().delete_step(chain_name, step_number)
    return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}


@app.post("/api/prompt", tags=["Prompt"])
async def add_prompt(prompt: CustomPromptModel) -> ResponseMessage:
    try:
        CustomPrompt().add_prompt(prompt.prompt_name, prompt.prompt)
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' added.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/prompt/{prompt_name}", tags=["Prompt"], response_model=CustomPromptModel)
async def get_prompt(prompt_name: str):
    try:
        prompt_content = CustomPrompt().get_prompt(prompt_name)
        return {"prompt_name": prompt_name, "prompt": prompt_content}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/prompt", response_model=PromptList, tags=["Prompt"])
async def get_prompts():
    prompts = CustomPrompt().get_prompts()
    return {"prompts": prompts}


@app.delete("/api/prompt/{prompt_name}", tags=["Prompt"])
async def delete_prompt(prompt_name: str) -> ResponseMessage:
    try:
        CustomPrompt().delete_prompt(prompt_name)
        return ResponseMessage(message=f"Prompt '{prompt_name}' deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/api/prompt/{prompt_name}", tags=["Prompt"])
async def update_prompt(prompt: CustomPromptModel) -> ResponseMessage:
    try:
        CustomPrompt().update_prompt(prompt.prompt_name, prompt.prompt)
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7437)
