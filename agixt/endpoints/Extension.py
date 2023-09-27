from fastapi import FastAPI, HTTPException, Depends
from Extensions import Extensions
from ApiClient import Agent, log_interaction, verify_api_key
from Models import CommandExecution


app = FastAPI()


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
