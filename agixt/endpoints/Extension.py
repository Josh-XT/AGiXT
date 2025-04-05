from fastapi import APIRouter, HTTPException, Depends, Header
from Extensions import Extensions
from ApiClient import Agent, Conversations, verify_api_key, get_api_client, is_admin
from Models import CommandExecution, CommandArgs, ExtensionsModel, ExtensionSettings
from typing import Dict, Any


app = APIRouter()


@app.get(
    "/api/extensions/settings",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionSettings,
    summary="Get Extension Settings",
    description="Retrieves all extension settings for the authenticated user. This includes settings for all available extensions and chains.",
)
async def get_extension_settings(user=Depends(verify_api_key)):
    # try:
    ApiClient = get_api_client()
    ext = Extensions(user=user, ApiClient=ApiClient)
    return {"extension_settings": ext.get_extension_settings()}


@app.get(
    "/api/extensions/{command_name}/args",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=CommandArgs,
    summary="Get Command Arguments",
    description="Retrieves the available arguments for a specific command.",
)
async def get_command_args(command_name: str, user=Depends(verify_api_key)):
    return {"command_args": Extensions().get_command_args(command_name=command_name)}


@app.get(
    "/api/extensions",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionsModel,
    summary="Get All Extensions",
    description="Retrieves all available extensions and their commands for the authenticated user.",
)
async def get_extensions(user=Depends(verify_api_key)):
    ext = Extensions(user=user)
    extensions = ext.get_extensions()
    return {"extensions": extensions}


@app.get(
    "/api/agent/{agent_name}/extensions",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=ExtensionsModel,
    summary="Get Agent Extensions",
    description="Retrieves all extensions and their enabled/disabled status for a specific agent.",
)
async def get_agent_extensions(agent_name: str, user=Depends(verify_api_key)):
    ApiClient = get_api_client()
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    extensions = agent.get_agent_extensions()
    return {"extensions": extensions}


@app.post(
    "/api/agent/{agent_name}/command",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
    response_model=Dict[str, Any],
    summary="Execute Agent Command",
    description="Executes a specific command for an agent. This endpoint requires admin privileges.",
)
async def run_command(
    agent_name: str,
    command: CommandExecution,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    agent_config = agent.get_agent_config()
    c = Conversations(conversation_name=command.conversation_name)
    command_output = await Extensions(
        agent_name=agent_name,
        agent_config=agent_config,
        agent_id=agent.agent_id,
        conversation_name=command.conversation_name,
        conversation_id=c.get_conversation_id(),
        ApiClient=ApiClient,
        api_key=authorization,
        user=user,
    ).execute_command(
        command_name=command.command_name, command_args=command.command_args
    )
    if (
        command.conversation_name != ""
        and command.conversation_name != None
        and command_output != None
    ):
        c = Conversations(conversation_name=command.conversation_name, user=user)
        c.log_interaction(role=agent_name, message=command_output)
    return {
        "response": command_output,
    }
