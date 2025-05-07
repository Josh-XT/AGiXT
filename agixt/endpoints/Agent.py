import json
import uuid
from typing import Dict
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
    is_admin,
)
from Models import (
    AgentNewName,
    AgentPrompt,
    ToggleCommandPayload,
    AgentCommands,
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
import time
import os
from providers.default import DefaultProvider
from Conversations import get_conversation_name_by_id, get_conversation_id_by_name
from MagicalAuth import MagicalAuth, get_user_id
import traceback

app = APIRouter()


@app.post(
    "/api/agent",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Create a new agent",
    description="Creates a new agent with specified settings and optionally trains it with provided URLs.",
    response_model=AgentResponse,
)
async def addagent(
    agent: AgentSettings,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, str]:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    add_agent(
        agent_name=agent.agent_name,
        provider_settings=agent.settings,
        commands=agent.commands,
        user=user,
    )
    if agent.training_urls != [] and agent.training_urls != None:
        if len(agent.training_urls) < 1:
            return {"message": "Agent added."}
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
        return {"message": "Agent added and trained."}
    return {"message": "Agent added."}


@app.post(
    "/api/agent/import",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Import an agent configuration",
    description="Imports an existing agent configuration including settings and commands.",
    response_model=AgentResponse,
)
async def import_agent(
    agent: AgentConfig, user=Depends(verify_api_key), authorization: str = Header(None)
) -> Dict[str, str]:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    return add_agent(
        agent_name=agent.agent_name,
        provider_settings=agent.settings,
        commands=agent.commands,
        user=user,
    )


@app.patch(
    "/api/agent/{agent_name}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Rename an agent",
    description="Changes the name of an existing agent.",
    response_model=ResponseMessage,
)
async def renameagent(
    agent_name: str,
    new_name: AgentNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    rename_agent(agent_name=agent_name, new_name=new_name.new_name, user=user)
    return ResponseMessage(message="Agent renamed.")


@app.put(
    "/api/agent/{agent_name}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Update agent settings",
    description="Updates the settings for an existing agent.",
    response_model=ResponseMessage,
)
async def update_agent_settings(
    agent_name: str,
    settings: AgentSettings,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    update_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).update_agent_config(new_config=settings.settings, config_key="settings")
    return ResponseMessage(message=update_config)


@app.put(
    "/api/agent/{agent_name}/persona",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Update agent persona",
    description="Updates the persona settings for an agent, optionally within a company context.",
    response_model=ResponseMessage,
)
async def update_persona(
    agent_name: str,
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
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).update_agent_config(
        new_config={"persona": persona.persona}, config_key="settings"
    )
    return ResponseMessage(message=update_config)


@app.get(
    "/api/agent/{agent_name}/persona",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent persona",
    description="Retrieves the current persona settings for an agent.",
    response_model=Dict[str, str],
)
async def get_persona(
    agent_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    if "persona" not in agent.AGENT_CONFIG["settings"]:
        if "PERSONA" not in agent.AGENT_CONFIG["settings"]:
            agent.AGENT_CONFIG["settings"]["persona"] = ""
        else:
            agent.AGENT_CONFIG["settings"]["persona"] = agent.AGENT_CONFIG["settings"][
                "PERSONA"
            ]
    return {"message": agent.AGENT_CONFIG["settings"]["persona"]}


@app.get(
    "/api/agent/{agent_name}/persona/{company_id}",
    dependencies=[Depends(verify_api_key)],
    summary="Get agent persona",
    tags=["Agent"],
)
async def get_persona(
    agent_name: str,
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
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        return {"message": agent.AGENT_CONFIG["settings"]["persona"]}
    else:
        response = auth.get_training_data(id if company_id is None else company_id)
        return {"message": response}


@app.put(
    "/api/agent/{agent_name}/persona/{company_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def update_persona(
    agent_name: str,
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
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).update_agent_config(
        new_config={"persona": persona.persona}, config_key="settings"
    )
    return ResponseMessage(message=update_config)


@app.put(
    "/api/agent/{agent_name}/commands",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Update agent commands",
    description="Updates the available commands for an agent.",
    response_model=ResponseMessage,
)
async def update_agent_commands(
    agent_name: str,
    commands: AgentCommands,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    update_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).update_agent_config(new_config=commands.commands, config_key="commands")
    return ResponseMessage(message=update_config)


@app.delete(
    "/api/agent/{agent_name}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Delete an agent",
    description="Deletes an agent and all associated data including memory and configurations.",
    response_model=ResponseMessage,
)
async def deleteagent(
    agent_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    await Websearch(
        collection_number="0",
        agent=agent,
        user=user,
        ApiClient=ApiClient,
    ).agent_memory.wipe_memory()
    delete_agent(agent_name=agent_name, user=user)
    return ResponseMessage(message=f"Agent {agent_name} deleted.")


@app.get(
    "/api/agent",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get all agents",
    description="Retrieves a list of all available agents for the authenticated user.",
    response_model=AgentListResponse,
)
async def getagents(user=Depends(verify_api_key), authorization: str = Header(None)):
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


@app.get(
    "/api/agent/{agent_name}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent configuration",
    description="Retrieves the complete configuration for a specific agent.",
    response_model=AgentConfigResponse,
)
async def get_agentconfig(
    agent_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    for key, value in agent_config["settings"].items():
        logging.info(f"Checking {key} for {agent_name}.")
        if value.strip() != "":
            logging.info(f"{key} has value: {value} for {agent_name}")
            if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD"]):
                logging.info(f"Masking hidden agent setting: {key} for {agent_name}")
                agent_config["settings"][key] = "HIDDEN"
            else:
                logging.info(f"Not masking setting {key} for {agent_name}")
                agent_config["settings"][key] = value
        else:
            logging.info(f"Skipping empty agent setting: {key} for {agent_name}")
    logging.info(json.dumps(agent_config, indent=4))
    return {"agent": agent_config}


@app.post(
    "/api/agent/{agent_name}/prompt",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Prompt an agent",
    description="Sends a prompt to an agent and receives a response. Can include various prompt arguments and conversation context.",
    response_model=AgentPromptResponse,
)
async def prompt_agent(
    agent_name: str,
    agent_prompt: AgentPrompt,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        conversation_name = agent_prompt.prompt_args.get("conversation_name")
        if conversation_name and conversation_name != "-":
            try:
                conversation_id = str(uuid.UUID(conversation_name))
                user_id_for_conv = get_user_id(user)
                conversation_name = get_conversation_name_by_id(
                    conversation_id=conversation_id, user_id=user_id_for_conv
                )
            except ValueError:
                pass  # It's already a name
            except Exception as e:
                logging.error(
                    f"Error resolving conversation name for /api/agent/prompt: {e}"
                )

        # Construct the ChatCompletions compatible messages list
        messages_for_chat_completions = []
        prompt_args_for_message = agent_prompt.prompt_args.copy()

        # Remove specific keys that are part of the ChatCompletions model or handled separately
        user_input_content = prompt_args_for_message.pop("user_input", "")
        # Add other keys that are part of the ChatCompletions message structure if needed
        # For example, if AgentPrompt has a 'role' field, use it. Defaulting to 'user'.
        # Ensure all relevant prompt_args are passed to the message, not just user_input.

        content_list = [{"type": "text", "text": user_input_content}]
        if "file_urls" in prompt_args_for_message:
            for file_url in prompt_args_for_message["file_urls"]:
                content_list.append({"type": "file_url", "file_url": {"url": file_url}})
            del prompt_args_for_message["file_urls"]  # Remove it after processing

        messages_for_chat_completions.append(
            {
                "role": "user",  # Assuming 'user' role for this endpoint's primary input
                "content": content_list,
                **prompt_args_for_message,  # Add remaining prompt_args to the message
            }
        )

        # Instantiate AGiXT
        agixt_instance = AGiXT(
            user=user,
            agent_name=agent_name,
            api_key=authorization,
            conversation_name=conversation_name,
        )

        # Create the ChatCompletions model instance
        chat_completions_prompt = ChatCompletions(
            model=agent_name,
            user=conversation_name,  # This is the conversation_name for AGiXT
            messages=messages_for_chat_completions,
            stream=False,  # Explicitly set stream to False for this endpoint
            # Add other ChatCompletions fields if agent_prompt.prompt_args contains them
            # e.g., temperature=agent_prompt.prompt_args.get('temperature', 0.7)
        )

        logging.info(
            f"Prompting agent '{agent_name}' via /api/agent/prompt with: {chat_completions_prompt.messages}"
        )

        # Iterate through the async generator and collect the response
        final_response_content = ""
        # Default values for reconstructing a ChatCompletionResponse-like structure
        completion_id = f"chatcmpl-{uuid.uuid4()}"
        model_name_used = agent_name
        created_time = int(time.time())
        finish_reason = "stop"

        async for chunk_str in agixt_instance.chat_completions(
            prompt=chat_completions_prompt
        ):
            if chunk_str.startswith("event: message\ndata: "):
                data_json = chunk_str.split("data: ", 1)[1].strip()
                if data_json == "[DONE]":
                    break
                try:
                    data = json.loads(data_json)
                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content_part = delta.get("content", "")
                    if content_part:
                        final_response_content += content_part
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
                    # Capture id, model, created from the first relevant chunk
                    if (
                        not completion_id.startswith("chatcmpl-")
                        or completion_id == f"chatcmpl-{uuid.uuid4()}"
                    ):  # Heuristic to check if it's default
                        completion_id = data.get("id", completion_id)
                    model_name_used = data.get("model", model_name_used)
                    created_time = data.get("created", created_time)

                except json.JSONDecodeError:
                    logging.error(
                        f"Failed to decode stream chunk in /api/agent/prompt: {data_json}"
                    )
                except Exception as e:
                    logging.error(
                        f"Error processing stream chunk in /api/agent/prompt: {e}"
                    )
            elif chunk_str.strip() == "data: [DONE]":
                break

        if finish_reason == "error":
            raise HTTPException(
                status_code=500,
                detail=final_response_content or "Agent processing failed.",
            )

        # Simulate token usage calculation if needed, or ideally get it from a more structured response
        # For now, just returning the content as per AgentPromptResponse model
        return AgentPromptResponse(response=str(final_response_content))

    except HTTPException as http_exc:
        logging.error(f"HTTP Exception in /api/agent/prompt: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logging.error(f"Error in /api/agent/prompt: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/agent/{agent_name}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent commands",
    description="Retrieves the list of available commands for an agent.",
    response_model=AgentCommandsResponse,
)
async def get_commands(
    agent_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    return {"commands": agent.AGENT_CONFIG["commands"]}


@app.patch(
    "/api/agent/{agent_name}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Toggle agent command",
    description="Enables or disables a specific command for an agent.",
    response_model=ResponseMessage,
)
async def toggle_command(
    agent_name: str,
    payload: ToggleCommandPayload,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    update_config = agent.update_agent_config(
        new_config={payload.command_name: payload.enable}, config_key="commands"
    )
    return ResponseMessage(message=update_config)


# Get agent browsed links


@app.get(
    "/api/agent/{agent_name}/browsed_links/{collection_number}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent browsed links",
    description="Retrieves the list of URLs that have been browsed by the agent in a specific collection.",
    response_model=AgentBrowsedLinksResponse,
)
async def get_agent_browsed_links(
    agent_name: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    return {"links": agent.get_browsed_links(conversation_id=collection_number)}


# Delete browsed link from memory
@app.delete(
    "/api/agent/{agent_name}/browsed_links",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Delete browsed link",
    description="Removes a specific URL from the agent's browsed links history.",
    response_model=ResponseMessage,
)
async def delete_browsed_link(
    agent_name: str,
    url: UrlInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
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
    "/api/agent/{agent_name}/text_to_speech",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Convert text to speech",
    description="Converts text to speech using the agent's configured TTS provider.",
    response_model=Dict[str, str],
)
async def text_to_speech(
    agent_name: str,
    text: TTSInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    AGIXT_URI = getenv("AGIXT_URI")
    if agent.TTS_PROVIDER != None:
        tts_response = await agent.text_to_speech(text=text.text)
    else:
        tts_response = await DefaultProvider().text_to_speech(text=text.text)
    if not str(tts_response).startswith("http"):
        file_type = "wav"
        file_name = f"{uuid.uuid4().hex}.{file_type}"
        audio_path = os.path.join(agent.working_directory, file_name)
        audio_data = base64.b64decode(tts_response)
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        tts_response = f"{AGIXT_URI}/outputs/{agent.agent_id}/{file_name}"
    return {"url": tts_response}


# Plan task


@app.post(
    "/api/agent/{agent_name}/plan/task",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Plan a task",
    description="Creates a task plan for the agent to execute, optionally including web search capabilities.",
    response_model=Dict[str, str],
)
async def plan_task(
    agent_name: str,
    task: TaskPlanInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    agent = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=task.conversation_name,
    )
    planned_task = await agent.plan_task(
        user_input=task.user_input,
        websearch=task.websearch,
        websearch_depth=task.websearch_depth,
        log_user_input=task.log_user_input,
        log_output=task.log_output,
        enable_new_command=task.enable_new_command,
    )
    return {"response": planned_task}


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
    return await prompt_agent(
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
    response_model=Dict[str, str],
)
async def get_providers(
    agent_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, str]:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_id, user=user, ApiClient=ApiClient)
    agent_settings = agent.AGENT_CONFIG["settings"]
    providers = get_providers_with_details()
    new_providers = {}
    # Check each provider against agent settings for a match to see if the key is defined in agent settings and is not empty
    # If it is, set connected = True, else connected = False
    for provider in providers:
        provider_name = list(provider.keys())[0]
        provider_details = list(provider.values())[0]
        provider_settings = provider_details["settings"]
        connected = False
        for key in provider_settings:
            if key in agent_settings and agent_settings[key] != "":
                connected = True
        new_providers[provider_name] = {
            "connected": connected,
            **provider_details,
        }
    return {"providers": new_providers}


# `DEL /v1/agent/{agent_id}/provider/{provider_name}` ?
@app.delete(
    "/v1/agent/{agent_id}/provider/{provider_name}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Delete agent provider",
    description="Deletes a specific provider from the agent's configuration.",
    response_model=ResponseMessage,
)
async def delete_provider(
    agent_id: str,
    provider_name: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_id, user=user, ApiClient=ApiClient)
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
    return ResponseMessage(message=update_config)


@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet",
    description="Retrieves the private key and passphrase for the agent's Solana wallet. Assumes wallet exists if agent exists.",
    response_model=WalletResponseModel,
)
async def get_agent_wallet(
    agent_name: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    agent = Agent(
        agent_name=agent_name,
        user=user,
        ApiClient=get_api_client(authorization=authorization),
    )
    wallet_info = agent.get_agent_wallet()
    return WalletResponseModel(
        private_key=wallet_info["private_key"],
        passphrase=wallet_info["passphrase"],
    )
