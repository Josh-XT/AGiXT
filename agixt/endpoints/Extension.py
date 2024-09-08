from fastapi import APIRouter, HTTPException, Depends, Header
from Extensions import Extensions
from ApiClient import Agent, Conversations, verify_api_key, get_api_client, is_admin
from Models import CommandExecution


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


@app.get(
    "/api/agent/{agent_name}/extensions",
    tags=["Extensions"],
    dependencies=[Depends(verify_api_key)],
)
async def get_agent_extensions(agent_name: str, user=Depends(verify_api_key)):
    ApiClient = get_api_client()
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    agent_config = agent.get_agent_config()
    agent_settings = agent_config["settings"]
    extensions = Extensions().get_extensions()
    new_extensions = []
    # Get required keys for each extension
    for extension in extensions:
        required_keys = extension["settings"]
        new_extension = extension.copy()
        for key in required_keys:
            if key not in agent_settings:
                if "missing_keys" not in new_extension:
                    new_extension["missing_keys"] = []
                new_extension["missing_keys"].append(key)
                new_extension["commands"] = []
            else:
                if agent_settings[key] == "" or agent_settings[key] == None:
                    new_extension["commands"] = []
        new_extensions.append(new_extension)
    agent_commands = agent_config["commands"]
    for extension in new_extensions:
        for command in extension["commands"]:
            if command["friendly_name"] in agent_commands:
                command["enabled"] = agent_commands[command["friendly_name"]]
            else:
                command["enabled"] = False
    return {"extensions": new_extensions}


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
