import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from Config import Config
from AgentLLM import AgentLLM
from Commands import Commands
import threading
from typing import Optional, Dict, List

CFG = Config()
app = FastAPI()
agent_instances = CFG.agent_instances

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
    prompt_type: str
    prompt: str

class ChainStep(BaseModel):
    chain_name: str
    step_number: int
    agent_name: str
    prompt_type: str
    prompt: str

class ChainStepNewInfo(BaseModel):
    chain_name: str
    old_step_number: int
    new_step_number: int
    prompt_type: str

class ResponseMessage(BaseModel):
    message: str

class TaskOutput(BaseModel):
    output: str
    message: Optional[str] = None

class ToggleCommandPayload(BaseModel):
    command_name: str
    enable: bool

class Prompt(BaseModel):
    prompt: str

@app.get("/api/provider", tags=["Provider"])
async def get_providers():
    providers = CFG.get_providers()
    return {"providers": providers}

@app.post("/api/agent", tags=["Agent"])
async def add_agent(agent_name: AgentName) -> Dict[str, str]:
    agent_info = CFG.add_agent(agent_name.agent_name)
    return {"message": "Agent added", "agent_file": agent_info['agent_file']}

@app.put("/api/agent/{agent_name}", tags=["Agent"])
async def rename_agent(agent_name: str, new_name: AgentNewName) -> ResponseMessage:
    CFG.rename_agent(agent_name, new_name.new_name)
    return ResponseMessage(message=f"Agent {agent_name} renamed to {new_name.new_name}.")

@app.delete("/api/agent/{agent_name}", tags=["Agent"])
async def delete_agent(agent_name: str) -> ResponseMessage:
    result, status_code = CFG.delete_agent(agent_name)
    if status_code == 200:
        return ResponseMessage(message=result["message"])
    else:
        raise HTTPException(status_code=status_code, detail=result["message"])

@app.get("/api/agent", tags=["Agent"])
async def get_agents():
    agents = CFG.get_agents()
    return {"agents": agents}

@app.get("/api/agent/{agent_name}", tags=["Agent"])
async def get_agent_config(agent_name: str):
    agent_config = CFG.get_agent_config(agent_name)
    return {"agent": agent_config}

@app.get("/api/{agent_name}/chat", tags=["Agent"])
async def get_chat_history(agent_name: str):
    chat_history = CFG.get_chat_history(agent_name)
    return {"chat_history": chat_history}

@app.delete("/api/agent/{agent_name}/memory", tags=["Agent"])
async def wipe_agent_memories(agent_name: str) -> ResponseMessage:
    CFG.wipe_agent_memories(agent_name)
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")

@app.post("/api/agent/{agent_name}/instruct", tags=["Agent"])
async def instruct(agent_name: str, prompt: Prompt):
    agent = AgentLLM(agent_name)
    response = agent.run(prompt.prompt, max_context_tokens=500, long_term_access=False)
    return {"response": str(response)}

@app.post("/api/agent/{agent_name}/chat", tags=["Agent"])
async def chat(agent_name: str, prompt: Prompt):
    agent = AgentLLM(agent_name)
    response = agent.run(prompt.prompt, max_context_tokens=500, long_term_access=False)
    return {"response": str(response)}

@app.get("/api/agent/{agent_name}/command", tags=["Agent"])
async def get_commands(agent_name: str):
    commands = Commands(agent_name)
    available_commands = commands.get_available_commands()
    return {"commands": available_commands}

@app.patch("/api/agent/{agent_name}/command", tags=["Agent"])
async def toggle_command(agent_name: str, payload: ToggleCommandPayload) -> ResponseMessage:
    try:
        if payload.command_name == "*":
            commands = Commands(agent_name)
            for each_command_name in commands.agent_config["commands"]:
                commands.agent_config["commands"][each_command_name] = payload.enable
            CFG.update_agent_config(agent_name, commands.agent_config)
            return ResponseMessage(message=f"All commands enabled for agent '{agent_name}'.")
        else:
            commands = Commands(agent_name)
            commands.agent_config["commands"][payload.command_name] = payload.enable
            CFG.update_agent_config(agent_name, commands.agent_config)
            return ResponseMessage(message=f"Command '{payload.command_name}' toggled for agent '{agent_name}'.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enabling all commands for agent '{agent_name}': {str(e)}")

@app.post("/api/agent/{agent_name}/task", tags=["Agent"])
async def toggle_task_agent(agent_name: str, objective: Objective) -> ResponseMessage:
    if agent_name not in agent_instances:
        agent_instances[agent_name] = AgentLLM(agent_name)
        agent_instances[agent_name].set_objective(objective.objective)
        agent_thread = threading.Thread(target=agent_instances[agent_name].run_task)
        agent_thread.start()
        return ResponseMessage(message="Task agent started")
    else:
        agent_instances[agent_name].stop_running()
        return ResponseMessage(message="Task agent stopped")

@app.get("/api/agent/{agent_name}/task", tags=["Agent"])
async def get_task_output(agent_name: str) -> TaskOutput:
    agent_instance = AgentLLM(agent_name)
    agent_instances[agent_name] = agent_instance
    output = agent_instances[agent_name].get_output_list()
    if agent_instance.get_status():
        return TaskOutput(output=output, message="Task agent is still running")
    return TaskOutput(output=f"{output}")

@app.get("/api/agent/{agent_name}/task/status", tags=["Agent"])
async def get_task_status(agent_name: str):
    if agent_name not in agent_instances:
        return {"status": False}
    status = agent_instances[agent_name].get_status()
    return {"status": status}

@app.get("/api/chain", tags=["Chain"])
async def get_chains():
    chains = CFG.get_chains()
    return chains

@app.get("/api/chain/{chain_name}", tags=["Chain"])
async def get_chain(chain_name: str):
    chain_data = CFG.get_chain(chain_name)
    return chain_data

@app.post("/api/chain", tags=["Chain"])
async def add_chain(chain_name: ChainName) -> ResponseMessage:
    CFG.add_chain(chain_name.chain_name)
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")

@app.put("/api/chain/{chain_name}", tags=["Chain"])
async def rename_chain(chain_name: str, new_name: ChainNewName) -> ResponseMessage:
    CFG.rename_chain(chain_name, new_name.new_name)
    return ResponseMessage(message=f"Chain '{chain_name}' renamed to '{new_name.new_name}'.")

@app.delete("/api/chain/{chain_name}", tags=["Chain"])
async def delete_chain(chain_name: str) -> ResponseMessage:
    CFG.delete_chain(chain_name)
    return ResponseMessage(message=f"Chain '{chain_name}' deleted.")

@app.post("/api/chain/{chain_name}/step", tags=["Chain"])
async def add_step(chain_name: str, step_info: StepInfo) -> ResponseMessage:
    CFG.add_step(chain_name, step_info.step_number, step_info.prompt_type, step_info.prompt)
    return {"message": f"Step {step_info.step_number} added to chain '{chain_name}'."}

@app.put("/api/chain/{chain_name}/step", tags=["Chain"])
async def update_step(chain_name: str, chain_step: ChainStep) -> ResponseMessage:
    CFG.update_step(chain_name, chain_step.step_number, chain_step.agent_name, chain_step.prompt_type, chain_step.prompt)
    return {"message": f"Step {chain_step.step_number} updated for chain '{chain_name}'."}

@app.patch("/api/chain/{chain_name}/step/move", tags=["Chain"])
async def move_step(chain_name: str, chain_step_new_info: ChainStepNewInfo) -> ResponseMessage:
    CFG.move_step(chain_name, chain_step_new_info.old_step_number, chain_step_new_info.new_step_number, chain_step_new_info.prompt_type)
    return {"message": f"Step {chain_step_new_info.old_step_number} moved to {chain_step_new_info.new_step_number} in chain '{chain_name}'."}

@app.delete("/api/chain/{chain_name}/step/{step_number}", tags=["Chain"])
async def delete_step(chain_name: str, step_number: int) -> ResponseMessage:
    CFG.delete_step(chain_name, step_number)
    return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}

@app.post("/api/prompt", tags=["Prompt"])
async def add_prompt(prompt_name: PromptName, prompt: Prompt) -> ResponseMessage:
    try:
        CFG.add_prompt(prompt_name.prompt_name, prompt.prompt)
        return ResponseMessage(message=f"Prompt '{prompt_name.prompt_name}' added.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/prompt/{prompt_name}", tags=["Prompt"], response_model=Prompt)
async def get_prompt(prompt_name: str):
    try:
        prompt_content = CFG.get_prompt(prompt_name)
        return {"prompt": prompt_content}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/prompt", response_model=PromptList, tags=["Prompt"])
async def get_prompts():
    prompts = CFG.get_prompts()
    return {"prompts": prompts}

@app.delete("/api/prompt/{prompt_name}", tags=["Prompt"])
async def delete_prompt(prompt_name: str) -> ResponseMessage:
    try:
        CFG.delete_prompt(prompt_name)
        return ResponseMessage(message=f"Prompt '{prompt_name}' deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/prompt/{prompt_name}", tags=["Prompt"])
async def update_prompt(prompt_name: str, prompt: Prompt) -> ResponseMessage:
    try:
        CFG.update_prompt(prompt_name, prompt.prompt)
        return ResponseMessage(message=f"Prompt '{prompt_name}' updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
