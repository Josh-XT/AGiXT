import json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header
from XT import AGiXT
from Websearch import Websearch
from Globals import getenv, get_default_agent, get_agixt_training_urls
from ApiClient import (
    Agent,
    add_agent,
    delete_agent,
    rename_agent,
    get_agents,
    verify_api_key,
    get_api_client,
)
from MagicalAuth import require_scope
from Agent import (
    can_user_access_agent,
    clone_agent as clone_agent_func,
    get_agent_commands_only,
)
from MagicalAuth import get_user_id
from Models import (
    AgentNewName,
    AgentPrompt,
    ToggleCommandPayload,
    ToggleExtensionCommandsPayload,
    AgentCommands,
    AgentCommandsV1,
    AgentSettings,
    AgentConfig,
    AgentResponse,
    AgentListResponse,
    AgentConfigResponse,
    AgentCommandsResponse,
    AgentBrowsedLinksResponse,
    AgentPromptResponse,
    ResponseMessage,
    UrlInput,
    TTSInput,
    TaskPlanInput,
    PersonaInput,
    ChatCompletions,
    ThinkingPrompt,
    WalletResponseModel,
)
import logging
import base64
import uuid
import os
from Conversations import get_conversation_name_by_id, get_conversation_id_by_name
from MagicalAuth import MagicalAuth
import traceback


def sanitize_path_component_local(component):
    """Local path sanitization for CodeQL compliance"""
    import re

    if not component or not isinstance(component, str):
        raise ValueError("Path component must be a non-empty string")

    component = component.strip()
    if not component:
        raise ValueError("Path component is empty")

    # Only allow alphanumeric, hyphens, and underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", component):
        raise ValueError(f"Invalid characters in path component: {component}")

    if len(component) > 255:
        raise ValueError("Path component too long")

    return component


app = APIRouter()


# V1 Agent List and Create Endpoints


@app.get(
    "/v1/agent",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get all agents",
    description="Retrieves a list of all available agents with their IDs for the authenticated user.",
    response_model=AgentListResponse,
)
async def get_agents_v1(
    user=Depends(verify_api_key), authorization: str = Header(None)
):
    agents = get_agents(user=user)
    create_agent = str(getenv("CREATE_AGENT_ON_REGISTER")).lower() == "true"
    if create_agent:
        agent_list = [agent["name"] for agent in agents]
        agent_name = getenv("AGENT_NAME")
        if agent_name not in agent_list:
            agent_config = get_default_agent()
            agent_settings = agent_config["settings"]
            agent_commands = agent_config["commands"]
            create_agixt_agent = str(getenv("CREATE_AGIXT_AGENT")).lower() == "true"
            training_urls = (
                get_agixt_training_urls()
                if create_agixt_agent and agent_name == "AGiXT"
                else agent_config["training_urls"]
            )
            ApiClient = get_api_client(authorization=authorization)
            ApiClient.add_agent(
                agent_name=agent_name,
                settings=agent_settings,
                commands=agent_commands,
                training_urls=training_urls,
            )
    return {"agents": agents}


@app.post(
    "/v1/agent",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Create a new agent",
    description="Creates a new agent with specified settings and optionally trains it with provided URLs. Returns the agent ID.",
    response_model=AgentResponse,
)
async def add_agent_v1(
    agent: AgentSettings,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, str]:
    result = add_agent(
        agent_name=agent.agent_name,
        provider_settings=agent.settings,
        commands=agent.commands,
        user=user,
    )
    agent_id = result.get("id") if isinstance(result, dict) else None
    if agent.training_urls != [] and agent.training_urls != None:
        if len(agent.training_urls) < 1:
            return {"message": "Agent added.", "id": agent_id}
        ApiClient = get_api_client(authorization=authorization)
        _agent = Agent(agent_name=agent.agent_name, user=user, ApiClient=ApiClient)
        reader = Websearch(
            collection_number="0",
            agent=_agent,
            user=user,
            ApiClient=ApiClient,
        )
        for url in agent.training_urls:
            await reader.get_web_content(url=url)
        return {"message": "Agent added and trained.", "id": agent_id}
    return {"message": "Agent added.", "id": agent_id}


@app.post(
    "/v1/agent/import",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Import an agent configuration",
    description="Imports an existing agent configuration including settings and commands. Returns the agent ID.",
    response_model=AgentResponse,
)
async def import_agent_v1(
    agent: AgentConfig, user=Depends(verify_api_key), authorization: str = Header(None)
) -> Dict[str, str]:
    result = add_agent(
        agent_name=agent.agent_name,
        provider_settings=agent.settings,
        commands=agent.commands,
        user=user,
    )
    return result


@app.post(
    "/v1/agent/think",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Make agent think",
    description="Triggers the agent to perform deep thinking and reflection on the provided input.",
    response_model=AgentPromptResponse,
)
async def think(
    agent_prompt: ThinkingPrompt,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if "conversation_name" in agent_prompt.prompt_args:
        agent_prompt.conversation_id = get_conversation_id_by_name(
            conversation_name=agent_prompt.prompt_args["conversation_name"]
        )
    if "log_user_input" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["log_user_input"] = False
    if "log_output" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["log_output"] = False
    if "tts" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["tts"] = False
    if "analyze_user_input" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["analyze_user_input"] = False
    if "browse_links" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["browse_links"] = False
    if "websearch" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["websearch"] = False
    if "disable_commands" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["disable_commands"] = True
    think_deep = f"**The assistant should think deeply on the user's input and available context, reflect while being critical of the assistant's thoughts to ensure the most well reasoned response to the user. The assistant has 100 available thinking and reflection tokens to think through the response and is encouraged to use them liberally anywhere the assistant finds a higher reward could be achieved on responses. During reflection, the assistant should act as a critical judge that expects only the best, most well reasoned thoughts before answering the user, and should provide guidance for the next thoughts to be guided by for improved reasoning.**"
    if "context" in agent_prompt.prompt_args:
        agent_prompt.prompt_args["context"] += f"\n\n{think_deep}"
    else:
        agent_prompt.prompt_args["context"] = think_deep
    agent_prompt.prompt_args["user_input"] = agent_prompt.user_input
    ApiClient = get_api_client(authorization=authorization)
    return ApiClient.prompt_agent(
        agent_name=agent_prompt.agent_name,
        agent_prompt=AgentPrompt(
            prompt_name="Think About It",
            prompt_args=agent_prompt.prompt_args,
        ),
        user=user,
        authorization=authorization,
    )


from Providers import get_providers_with_details, get_provider_options


# Get connected agent providers
@app.get(
    "/v1/agent/{agent_id}/providers",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent providers",
    description="Retrieves the list of providers connected to a specific agent.",
    response_model=Dict[str, Any],
)
async def get_providers_v1(
    agent_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, str]:
    from DB import ServerExtensionSetting, get_session, decrypt_config_value
    from Globals import getenv

    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    providers = get_providers_with_details()

    # Get server-level extension settings (API keys configured by admin)
    server_api_keys = {}
    with get_session() as db:
        db_settings = (
            db.query(ServerExtensionSetting)
            .filter(ServerExtensionSetting.setting_key.like("%_API_KEY"))
            .all()
        )
        for setting in db_settings:
            value = setting.setting_value
            if setting.is_sensitive and value:
                value = decrypt_config_value(value)
            if value:  # Only store if actually has a value
                server_api_keys[setting.setting_key] = value

    new_providers = {}
    # Check each provider against server extension settings to determine connected status
    # A provider is "connected" only if it has an API key configured at the server level
    for provider_name, provider_details in providers.items():
        provider_settings = provider_details["settings"]
        connected = False
        for key in provider_settings:
            if key.endswith("_API_KEY"):
                # Check if this API key is set at server level
                if key in server_api_keys:
                    connected = True
                    break
                # Also check environment variable fallback
                env_value = getenv(key)
                if env_value:
                    connected = True
                    break
        new_providers[provider_name] = {
            "connected": connected,
            **provider_details,
        }
    return {"providers": new_providers}


@app.delete(
    "/v1/agent/{agent_id}/provider/{provider_name}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Delete agent provider",
    description="Deletes a specific provider from the agent's configuration.",
    response_model=ResponseMessage,
)
async def delete_provider_v1(
    agent_id: str,
    provider_name: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    provider = get_provider_options(provider_name)
    # Find what keys have the word "KEY", "SECRET", "PASSWORD", or "TOKEN" in them
    keys = [
        key
        for key in provider.keys()
        if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD", "TOKEN"])
    ]
    new_settings = {key: "" for key in keys}
    update_config = agent.update_agent_config(
        new_config=new_settings, config_key="settings"
    )
    config = agent.get_agent_config()
    logging.info(
        f"Agent {agent_id} provider {provider_name} deleted. New config: {json.dumps(config, indent=2)}"
    )
    return ResponseMessage(message=update_config)


# V1 Agent Endpoints using agent_id instead of agent_name


@app.patch(
    "/v1/agent/{agent_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Rename an agent by ID",
    description="Changes the name of an existing agent using agent ID.",
    response_model=ResponseMessage,
)
async def renameagent_v1(
    agent_id: str,
    new_name: AgentNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    rename_agent(agent_name=agent.agent_name, new_name=new_name.new_name, user=user)
    return ResponseMessage(message="Agent renamed.")


@app.put(
    "/v1/agent/{agent_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Update agent settings by ID",
    description="Updates the settings for an existing agent using agent ID.",
    response_model=ResponseMessage,
)
async def update_agent_settings_v1(
    agent_id: str,
    settings: AgentSettings,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    update_config = agent.update_agent_config(
        new_config=settings.settings, config_key="settings"
    )
    logging.debug(f"Agent {agent_id} settings updated")
    return ResponseMessage(message=update_config)


@app.put(
    "/v1/agent/{agent_id}/persona",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Update agent persona by ID",
    description="Updates the persona settings for an agent using agent ID, optionally within a company context.",
    response_model=ResponseMessage,
)
async def update_persona_v1(
    agent_id: str,
    persona: PersonaInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    if persona.company_id is not None:
        auth = MagicalAuth(token=authorization)
        if auth.get_user_role(persona.company_id) > 2:
            raise HTTPException(status_code=403, detail="Access Denied")
        else:
            response = auth.set_training_data(
                training_data=persona.persona, company_id=persona.company_id
            )
            return ResponseMessage(message=response)
    update_config = Agent(
        agent_id=agent_id, user=user, ApiClient=ApiClient
    ).update_agent_config(
        new_config={"persona": persona.persona}, config_key="settings"
    )
    return ResponseMessage(message=update_config)


@app.get(
    "/v1/agent/{agent_id}/persona",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent persona by ID",
    description="Retrieves the current persona settings for an agent using agent ID.",
    response_model=Dict[str, str],
)
async def get_persona_v1(
    agent_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    if "persona" not in agent.AGENT_CONFIG["settings"]:
        if "PERSONA" not in agent.AGENT_CONFIG["settings"]:
            agent.AGENT_CONFIG["settings"]["persona"] = ""
        else:
            agent.AGENT_CONFIG["settings"]["persona"] = agent.AGENT_CONFIG["settings"][
                "PERSONA"
            ]
    return {"message": agent.AGENT_CONFIG["settings"]["persona"]}


@app.get(
    "/v1/agent/{agent_id}/persona/{company_id}",
    dependencies=[Depends(verify_api_key)],
    summary="Get agent persona by ID with company",
    tags=["Agent"],
)
async def get_persona_company_v1(
    agent_id: str,
    company_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    user_persona = False
    if auth.get_user_role(company_id) > 2:
        user_persona = True
    if user_persona:
        ApiClient = get_api_client(authorization=authorization)
        agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
        return {"message": agent.AGENT_CONFIG["settings"]["persona"]}
    else:
        response = auth.get_training_data(company_id)
        return {"message": response}


@app.put(
    "/v1/agent/{agent_id}/persona/{company_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Update agent persona by ID with company",
)
async def update_persona_company_v1(
    agent_id: str,
    company_id: str,
    persona: PersonaInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    if company_id is not None:
        auth = MagicalAuth(token=authorization)
        if auth.get_user_role(company_id) > 2:
            raise HTTPException(status_code=403, detail="Access Denied")
        else:
            response = auth.set_training_data(
                training_data=persona.persona, company_id=company_id
            )
            return ResponseMessage(message=response)
    update_config = Agent(
        agent_id=agent_id, user=user, ApiClient=ApiClient
    ).update_agent_config(
        new_config={"persona": persona.persona}, config_key="settings"
    )
    return ResponseMessage(message=update_config)


@app.put(
    "/v1/agent/{agent_id}/commands",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Update agent commands by ID",
    description="Updates the available commands for an agent using agent ID.",
    response_model=ResponseMessage,
)
async def update_agent_commands_v1(
    agent_id: str,
    commands: AgentCommandsV1,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    update_config = Agent(
        agent_id=agent_id, user=user, ApiClient=ApiClient
    ).update_agent_config(new_config=commands.commands, config_key="commands")
    return ResponseMessage(message=update_config)


@app.delete(
    "/v1/agent/{agent_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:delete"))],
    summary="Delete an agent by ID",
    description="Deletes an agent and all associated data including memory and configurations using agent ID.",
    response_model=ResponseMessage,
)
async def deleteagent_v1(
    agent_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    await Websearch(
        collection_number="0",
        agent=agent,
        user=user,
        ApiClient=ApiClient,
    ).agent_memory.wipe_memory()
    delete_result, status_code = delete_agent(
        agent_name=agent.agent_name, agent_id=agent.agent_id, user=user
    )
    if status_code != 200:
        detail = delete_result.get("message", "Failed to delete agent.")
        raise HTTPException(status_code=status_code, detail=detail)
    return ResponseMessage(message=delete_result.get("message", "Agent deleted."))


@app.get(
    "/v1/agent/{agent_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:read"))],
    summary="Get agent configuration by ID",
    description="Retrieves the complete configuration for a specific agent using agent ID.",
    response_model=AgentConfigResponse,
)
async def get_agentconfig_v1(
    agent_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_id=agent_id, user=user, ApiClient=ApiClient
    ).get_agent_config()
    for key, value in agent_config["settings"].items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() != "":
            if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD"]):
                agent_config["settings"][key] = "HIDDEN"
            else:
                agent_config["settings"][key] = value
    return {"agent": agent_config}


@app.post(
    "/v1/agent/{agent_id}/prompt",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Prompt an agent by ID",
    description="Sends a prompt to an agent and receives a response using agent ID. Can include various prompt arguments and conversation context.",
    response_model=AgentPromptResponse,
)
async def prompt_agent_v1(
    agent_id: str,
    agent_prompt: AgentPrompt,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        # Get agent name from agent_id
        ApiClient = get_api_client(authorization=authorization)
        agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
        agent_name = agent.agent_name

        if "conversation_name" not in agent_prompt.prompt_args:
            conversation_name = None
            agent_prompt.prompt_args["log_user_input"] = False
            agent_prompt.prompt_args["log_output"] = False
        else:
            conversation_name = agent_prompt.prompt_args["conversation_name"]
            # Handle case where SDK passes dict instead of string (e.g., full conversation object)
            if isinstance(conversation_name, dict):
                if "id" in conversation_name:
                    conversation_name = str(conversation_name["id"])
                elif "name" in conversation_name:
                    conversation_name = str(conversation_name["name"])
                else:
                    conversation_name = None
            elif conversation_name is not None:
                conversation_name = str(conversation_name)
            del agent_prompt.prompt_args["conversation_name"]
        if "user_input" not in agent_prompt.prompt_args:
            agent_prompt.prompt_args["user_input"] = ""
        if conversation_name != "-":
            try:
                conversation_id = str(uuid.UUID(conversation_name))
            except:
                conversation_id = None
            if conversation_id:
                auth = MagicalAuth(token=authorization)
                conversation_name = get_conversation_name_by_id(
                    conversation_id=conversation_id, user_id=auth.user_id
                )
        agixt_agent = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=authorization,
            conversation_name=conversation_name,
        )
        agent_prompt.prompt_args["prompt_name"] = agent_prompt.prompt_name
        if "prompt_category" not in agent_prompt.prompt_args:
            agent_prompt.prompt_args["prompt_category"] = "Default"
        if "tts" in agent_prompt.prompt_args:
            agent_prompt.prompt_args["voice_response"] = (
                str(agent_prompt.prompt_args["tts"]).lower() == "true"
            )
            del agent_prompt.prompt_args["tts"]
        if "context_results" in agent_prompt.prompt_args:
            agent_prompt.prompt_args["injected_memories"] = int(
                agent_prompt.prompt_args["context_results"]
            )
            del agent_prompt.prompt_args["context_results"]
        if "conversation_results" not in agent_prompt.prompt_args:
            agent_prompt.prompt_args["conversation_results"] = 10
        prompt_args = agent_prompt.prompt_args.copy()
        if "user_input" in prompt_args:
            del prompt_args["user_input"]
        messages = []
        if "file_urls" in agent_prompt.prompt_args:
            file_list = agent_prompt.prompt_args["file_urls"]
            del agent_prompt.prompt_args["file_urls"]
            messages.append(
                {
                    "role": "user",
                    **prompt_args,
                    "prompt_args": prompt_args,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                agent_prompt.prompt_args["user_input"]
                                if "user_input" in agent_prompt.prompt_args
                                else ""
                            ),
                        },
                    ],
                }
            )
            for file_url in file_list:
                messages[0]["content"] += [
                    {
                        "type": "file_url",
                        "file_url": {"url": file_url},
                    }
                ]
        else:
            messages = [
                {
                    "role": "user",
                    **prompt_args,
                    "prompt_args": prompt_args,
                    "content": (
                        agent_prompt.prompt_args["user_input"]
                        if "user_input" in agent_prompt.prompt_args
                        else ""
                    ),
                }
            ]
        response = await agixt_agent.chat_completions(
            prompt=ChatCompletions(
                model=agent_name,
                user=conversation_name,
                messages=messages,
            )
        )
        response = response["choices"][0]["message"]["content"]
        return {"response": str(response)}
    except HTTPException:
        # Re-raise HTTP exceptions (like 402 Payment Required) without modification
        raise
    except Exception as e:
        logging.error(f"Error prompting agent: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/v1/agent/{agent_id}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:read"))],
    summary="Get agent commands by ID",
    description="Retrieves the list of available commands for an agent using agent ID.",
    response_model=AgentCommandsResponse,
)
async def get_commands_v1(
    agent_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    # Use lightweight function instead of creating full Agent object
    user_id = get_user_id(user=user)
    commands = get_agent_commands_only(agent_id=agent_id, user_id=user_id)
    return {"commands": commands}


@app.patch(
    "/v1/agent/{agent_id}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Toggle agent command by ID",
    description="Enables or disables a specific command for an agent using agent ID.",
    response_model=ResponseMessage,
)
async def toggle_command_v1(
    agent_id: str,
    payload: ToggleCommandPayload,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    update_config = agent.update_agent_config(
        new_config={payload.command_name: payload.enable}, config_key="commands"
    )
    return ResponseMessage(message=update_config)


@app.patch(
    "/v1/agent/{agent_id}/extension/commands",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Toggle all commands for a specific extension by agent ID",
    description="Enables or disables all commands for a specific extension for an agent using agent ID.",
    response_model=ResponseMessage,
)
async def toggle_extension_commands_v1(
    agent_id: str,
    payload: ToggleExtensionCommandsPayload,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)

    # Get all extensions to find the commands for the specified extension
    extensions = agent.get_agent_extensions()

    # Find the extension and get all its commands
    extension_commands = []
    for extension in extensions:
        if extension["extension_name"] == payload.extension_name:
            for command in extension["commands"]:
                extension_commands.append(command["friendly_name"])
            break

    if not extension_commands:
        raise HTTPException(
            status_code=404,
            detail=f"Extension '{payload.extension_name}' not found or has no commands",
        )

    # Create a config update for all commands in the extension
    new_config = {command: payload.enable for command in extension_commands}

    # Update the agent configuration
    update_config = agent.update_agent_config(
        new_config=new_config, config_key="commands"
    )

    return ResponseMessage(
        message=f"Successfully {'enabled' if payload.enable else 'disabled'} {len(extension_commands)} commands for extension '{payload.extension_name}'"
    )


@app.get(
    "/v1/agent/{agent_id}/browsed_links/{collection_number}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:read"))],
    summary="Get agent browsed links by ID",
    description="Retrieves the list of URLs that have been browsed by the agent in a specific collection using agent ID.",
    response_model=AgentBrowsedLinksResponse,
)
async def get_agent_browsed_links_v1(
    agent_id: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    return {"links": agent.get_browsed_links(conversation_id=collection_number)}


@app.delete(
    "/v1/agent/{agent_id}/browsed_links",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:write"))],
    summary="Delete browsed link by ID",
    description="Removes a specific URL from the agent's browsed links history using agent ID.",
    response_model=ResponseMessage,
)
async def delete_browsed_link_v1(
    agent_id: str,
    url: UrlInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    websearch = Websearch(
        collection_number=str(url.collection_number),
        agent=agent,
        user=user,
        ApiClient=ApiClient,
    )
    await websearch.agent_memory.delete_memories_from_external_source(url=url.url)
    agent.delete_browsed_link(url=url.url, conversation_id=url.collection_number)
    return {"message": "Browsed links deleted."}


@app.post(
    "/v1/agent/{agent_id}/text_to_speech",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Convert text to speech by ID",
    description="Converts text to speech using the agent's configured TTS provider using agent ID.",
    response_model=Dict[str, str],
)
async def text_to_speech_v1(
    agent_id: str,
    text: TTSInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    AGIXT_URI = getenv("AGIXT_URI")
    if agent.TTS_PROVIDER != None:
        tts_response = await agent.text_to_speech(text=text.text)
    else:
        raise HTTPException(status_code=400, detail="No TTS provider available")
    if not str(tts_response).startswith("http"):
        import tempfile
        import shutil
        from datetime import datetime

        file_type = "wav"

        # CodeQL ultra-safe pattern: Complete data flow isolation
        # Create secure temporary directory completely isolated from user input
        with tempfile.TemporaryDirectory() as temp_base:
            # Create agent subdirectory using only system-generated paths
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            secure_filename = f"agent_{timestamp}.{file_type}"

            # Write audio data to secure temp file
            temp_audio_path = f"{temp_base}/{secure_filename}"
            audio_data = base64.b64decode(tts_response)
            with open(temp_audio_path, "wb") as f:
                f.write(audio_data)

            # Create final secure location in workspace using hardcoded paths only
            workspace_outputs = "WORKSPACE/outputs"
            os.makedirs(workspace_outputs, exist_ok=True)

            # Move to final location with system-generated filename
            final_audio_path = f"{workspace_outputs}/{secure_filename}"
            shutil.move(temp_audio_path, final_audio_path)

            tts_response = f"{AGIXT_URI}/outputs/{secure_filename}"
    return {"url": tts_response}


@app.post(
    "/v1/agent/{agent_id}/plan/task",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Plan a task by ID",
    description="Creates a task plan for the agent to execute using agent ID, optionally including web search capabilities.",
    response_model=Dict[str, str],
)
async def plan_task_v1(
    agent_id: str,
    task: TaskPlanInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    # Get agent name from agent_id
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

    agixt_agent = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=task.conversation_name,
    )
    planned_task = await agixt_agent.plan_task(
        user_input=task.user_input,
        websearch=task.websearch,
        websearch_depth=task.websearch_depth,
        log_user_input=task.log_user_input,
        log_output=task.log_output,
        enable_new_command=task.enable_new_command,
    )
    return {"response": planned_task}


@app.get(
    "/v1/agent/{agent_id}/wallet",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet by ID",
    description="Retrieves the private key and passphrase for the agent's Solana wallet using agent ID. If wallet doesn't exist or is empty, creates a new one automatically.",
    response_model=WalletResponseModel,
)
async def get_agent_wallet_v1(
    agent_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    agent = Agent(
        agent_id=agent_id,
        user=user,
        ApiClient=get_api_client(authorization=authorization),
    )
    wallet_info = agent.get_agent_wallet()
    return WalletResponseModel(
        private_key=wallet_info["private_key"],
        passphrase=wallet_info["passphrase"],
    )


@app.post(
    "/v1/agent/{agent_id}/clone",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Clone an agent by ID",
    description="Creates a copy of an agent with all its settings and commands. User must have access to the source agent. The cloned agent is private by default (shared flag is removed).",
    response_model=ResponseMessage,
)
async def clone_agent_v1(
    agent_id: str,
    new_name: AgentNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    # Get user_id from auth
    auth = MagicalAuth(token=authorization)

    # Check if user has access to the agent
    can_access, is_owner, access_level = can_user_access_agent(
        user_id=auth.user_id, agent_id=agent_id
    )

    if not can_access:
        raise HTTPException(
            status_code=403, detail="You do not have access to this agent"
        )

    # Clone the agent
    result = clone_agent_func(
        agent_id=agent_id, new_agent_name=new_name.new_name, user=user
    )

    return ResponseMessage(message=result.get("message", "Agent cloned successfully"))
