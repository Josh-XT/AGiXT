from fastapi import APIRouter, HTTPException, Depends, Header
from Extensions import Extensions
from ApiClient import Agent, log_interaction, verify_api_key, get_api_client
from Models import CommandExecution
import logging


app = APIRouter()


@app.get(
    "/api/extensions/settings",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def get_extension_settings(user=Depends(verify_api_key)):
    try:
        return {"extension_settings": Extensions().get_extension_settings()}
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to retrieve settings.")


@app.get(
    "/api/extensions/{command_name}/args",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def get_command_args(command_name: str, user=Depends(verify_api_key)):
    return {"command_args": Extensions().get_command_args(command_name=command_name)}


@app.get("/api/extensions", tags=["Extensions"], dependencies=[Depends(verify_api_key)])
async def get_extensions(user=Depends(verify_api_key)):
    extensions = Extensions().get_extensions()
    return {"extensions": extensions}


@app.post(
    "/api/agent/{agent_name}/command",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def run_command(
    agent_name: str,
    command: CommandExecution,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    logging.info(f"Autorization: {authorization}")
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    command_output = await Extensions(
        agent_name=agent_name,
        agent_config=agent_config,
        conversation_name=command.conversation_name,
        ApiClient=ApiClient,
        api_key=authorization,
        user=user,
    ).execute_command(
        command_name=command.command_name, command_args=command.command_args
    )
    log_interaction(
        agent_name=agent_name,
        conversation_name=command.conversation_name,
        role=agent_name,
        message=command_output,
        user=user,
    )
    return {
        "response": command_output,
    }
