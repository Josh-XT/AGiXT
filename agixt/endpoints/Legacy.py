"""
Legacy API Endpoints for AGiXT

This file contains all legacy endpoints that use name-based parameters instead of IDs.
These endpoints are maintained for backwards compatibility but are deprecated.
Please use the v1 endpoints in the main endpoint files for new integrations.

Legacy endpoints are tagged with "*-Legacy" in Swagger documentation.
"""

import json
import os
import base64
import asyncio
import logging
import traceback
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
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
    WORKERS,
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
    WalletResponseModel,
    AgentMemoryQuery,
    TextMemoryInput,
    FileInput,
    Dataset,
    FinetuneAgentModel,
    ExternalSource,
    UserInput,
    FeedbackInput,
    MemoryResponse,
    MemoryCollectionResponse,
    DPOResponse,
    ExtensionsModel,
    CommandExecution,
    CustomPromptModel,
    PromptList,
    PromptCategoryList,
    PromptName,
    PromptArgsResponse,
    ChainDetailsResponse,
    RunChain,
    RunChainStep,
    ChainName,
    ChainData,
    ChainNewName,
    StepInfo,
    ChainStep,
    ChainStepNewInfo,
)
from Conversations import (
    Conversations,
    get_conversation_name_by_id,
    get_conversation_id_by_name,
)
from Memories import Memories
from Prompts import Prompts
from Chain import Chain
from Extensions import Extensions
from MagicalAuth import MagicalAuth
from providers.default import DefaultProvider


# Create router for legacy endpoints
app = APIRouter()


@app.post(
    "/api/agent",
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    update_config = agent.update_agent_config(
        new_config=settings.settings, config_key="settings"
    )
    config = agent.get_agent_config()
    logging.info(
        f"Agent {agent_name} updated. New config: {json.dumps(config, indent=2)}"
    )
    return ResponseMessage(message=update_config)


@app.put(
    "/api/agent/{agent_name}/persona",
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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


@app.put(
    "/api/agent/{agent_name}/persona/{company_id}",
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    delete_result, status_code = delete_agent(
        agent_name=agent_name, agent_id=agent.agent_id, user=user
    )
    if status_code != 200:
        detail = delete_result.get("message", "Failed to delete agent.")
        raise HTTPException(status_code=status_code, detail=detail)
    return ResponseMessage(message=delete_result.get("message", "Agent deleted."))


@app.get(
    "/api/agent",
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
        if value.strip() != "":
            if any(x in key.upper() for x in ["KEY", "SECRET", "PASSWORD"]):
                agent_config["settings"][key] = "HIDDEN"
            else:
                agent_config["settings"][key] = value
    return {"agent": agent_config}


@app.post(
    "/api/agent/{agent_name}/prompt",
    tags=["Legacy-Agent"],
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
        if "conversation_name" not in agent_prompt.prompt_args:
            conversation_name = None
            agent_prompt.prompt_args["log_user_input"] = False
            agent_prompt.prompt_args["log_output"] = False
        else:
            conversation_name = agent_prompt.prompt_args["conversation_name"]
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
        agent = AGiXT(
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
        response = await agent.chat_completions(
            prompt=ChatCompletions(
                model=agent_name,
                user=conversation_name,
                messages=messages,
            )
        )
        response = response["choices"][0]["message"]["content"]
        return {"response": str(response)}
    except Exception as e:
        logging.error(f"Error prompting agent: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/api/agent/{agent_name}/command",
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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


@app.get(
    "/api/agent/{agent_name}/wallet",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Get agent wallet",
    description="Retrieves the private key and passphrase for the agent's Solana wallet. If wallet doesn't exist or is empty, creates a new one automatically.",
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


@app.post(
    "/api/agent/{agent_name}/memory/{collection_number}/query",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryResponse,
    summary="Query agent memories from a specific collection",
    description="Retrieves memories based on user input with relevance scoring and limiting options.",
)
async def query_memories(
    agent_name: str,
    memory: AgentMemoryQuery,
    collection_number="0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    memories = await Memories(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=str(collection_number),
        ApiClient=ApiClient,
        user=user,
    ).get_memories_data(
        user_input=memory.user_input,
        limit=memory.limit,
        min_relevance_score=memory.min_relevance_score,
    )
    return {"memories": memories}


# Export all agent memories


@app.get(
    "/api/agent/{agent_name}/memory/export",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryResponse,
    summary="Export all agent memories",
    description="Exports all memories from all collections for the specified agent.",
)
async def export_agent_memories(
    agent_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> Dict[str, Any]:
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    memories = await Memories(
        agent_name=agent_name, agent_config=agent_config, ApiClient=ApiClient, user=user
    ).export_collections_to_json()
    return {"memories": memories}


@app.post(
    "/api/agent/{agent_name}/memory/import",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Import memories into agent",
    description="Imports a list of memories into the agent's various collections.",
)
async def import_agent_memories(
    agent_name: str,
    memories: List[dict],
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    await Memories(
        agent_name=agent_name, agent_config=agent_config, ApiClient=ApiClient, user=user
    ).import_collections_from_json(memories)
    return ResponseMessage(message="Memories imported.")


@app.post(
    "/api/agent/{agent_name}/learn/text",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Learn from text input",
    description="Adds text content to the agent's memory with associated user input context.",
)
async def learn_text(
    agent_name: str,
    data: TextMemoryInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    if len(data.collection_number) > 4:
        conversation = Conversations(
            conversation_name=data.collection_number, user=user
        )
        collection_number = conversation.get_conversation_id()
    else:
        collection_number = str(data.collection_number)
    memory = Memories(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    )
    await memory.write_text_to_memory(
        user_input=data.user_input, text=data.text, external_source="user input"
    )
    return ResponseMessage(
        message="Agent learned the content from the text assocated with the user input."
    )


@app.post(
    "/api/agent/{agent_name}/learn/file",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Learn from file content",
    description="Processes and adds file content to the agent's memory. Supports various file types including PDFs, docs, and spreadsheets.",
)
async def learn_file(
    agent_name: str,
    file: FileInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    collection_number = str(file.collection_number)
    conversation_name = None
    if len(collection_number) > 4:
        conversation = Conversations(conversation_name=collection_number, user=user)
        collection_number = conversation.get_conversation_id()
        conversation_name = collection_number
    agent = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=conversation_name,
        collection_id=collection_number,
    )
    file.file_name = os.path.basename(file.file_name)
    file_path = os.path.normpath(
        os.path.join(agent.agent_workspace, file.collection_number, file.file_name)
    )
    if not file_path.startswith(agent.agent_workspace):
        raise Exception("Path given not allowed")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        file_content = base64.b64decode(file.file_content)
    except:
        file_content = file.file_content.encode("utf-8")
    with open(file_path, "wb") as f:
        f.write(file_content)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    response = await agent.learn_from_file(
        file_url=f"{agent.outputs}/{file.collection_number}/{file.file_name}",
        file_name=file.file_name,
        user_input=f"File {file.file_name} uploaded on {timestamp}.",
        collection_id=str(file.collection_number),
    )
    agent.conversation.log_interaction(
        role=agent_name,
        message=f"File [{file.file_name}]({agent.outputs}/{file.collection_number}/{file.file_name}) learned on {timestamp} to collection `{file.collection_number}`.",
    )
    return ResponseMessage(message=response)


@app.post(
    "/api/agent/{agent_name}/learn/url",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Learn from URL content",
    description="Scrapes and learns from content at the specified URL.",
)
async def learn_url(
    agent_name: str,
    url: UrlInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    url.url = url.url.replace(" ", "%20")
    websearch = Websearch(
        collection_number=url.collection_number,
        agent=agent,
        user=user,
        ApiClient=ApiClient,
    )
    conversation_name = f"{agent_name} Training on {timestamp}"
    response = await websearch.scrape_websites(
        user_input=f"I am browsing {url.url} and collecting data from it to learn more.",
        conversation_name=conversation_name,
    )
    c = Conversations(conversation_name=conversation_name, user=user)
    c.log_interaction(
        role=agent_name,
        message=f"URL [{url.url}]({url.url}) learned on {timestamp} to collection `{url.collection_number}`.",
    )
    return ResponseMessage(message=response)


@app.delete(
    "/api/agent/{agent_name}/memory",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete all agent memories",
    description="Wipes all memories for the specified agent. Requires admin access.",
)
async def wipe_agent_memories(
    agent_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number="0",
        ApiClient=ApiClient,
        user=user,
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.delete(
    "/api/agent/{agent_name}/memory/{collection_number}",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete memories from specific collection",
    description="Wipes memories from a specific collection. Requires admin access.",
)
async def wipe_agent_memories(
    agent_name: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.delete(
    "/api/agent/{agent_name}/memory/{collection_number}/{memory_id}",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete specific memory",
    description="Deletes a specific memory by its ID from a collection.",
)
async def delete_agent_memory(
    agent_name: str,
    collection_number: str = "0",
    memory_id="",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    ).delete_memory(key=memory_id)
    return ResponseMessage(
        message=f"Memory {memory_id} for agent {agent_name} deleted."
    )


# Create dataset


@app.post(
    "/api/agent/{agent_name}/memory/dataset",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Create dataset from memories",
    description="Creates a training dataset from the agent's memories. Requires admin access.",
)
async def create_dataset(
    agent_name: str,
    dataset: Dataset,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    batch_size = dataset.batch_size if dataset.batch_size < (int(WORKERS) - 2) else 4
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    asyncio.create_task(
        AGiXT(
            agent_name=agent_name,
            user=user,
            api_key=authorization,
            conversation_name=f"Dataset Creation on {timestamp}",
        ).create_dataset_from_memories(batch_size=batch_size)
    )
    return ResponseMessage(
        message=f"Creation of dataset {dataset.dataset_name} for agent {agent_name} started."
    )


@app.post(
    "/api/agent/{agent_name}/dpo",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=DPOResponse,
    summary="Get DPO response for question",
    description="Generates a DPO (Direct Preference Optimization) response including prompt, chosen and rejected outputs.",
)
async def get_dpo_response(
    agent_name: str,
    user_input: UserInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    agixt = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=f"DPO on {timestamp}",
    )
    prompt, chosen, rejected = await agixt.dpo(
        question=user_input, injected_memories=int(user_input.injected_memories)
    )
    return {
        "prompt": prompt,
        "chosen": chosen,
        "rejected": rejected,
    }


# Train model


@app.post(
    "/api/agent/{agent_name}/memory/dataset/{dataset_name}/finetune",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Fine tune a language model with the agent's memories as a synthetic dataset",
)
async def fine_tune_model(
    agent_name: str,
    finetune: FinetuneAgentModel,
    dataset_name: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    from Tuning import fine_tune_llm

    ApiClient = get_api_client(authorization=authorization)
    asyncio.create_task(
        fine_tune_llm(
            agent_name=agent_name,
            dataset_name=dataset_name,
            model_name=finetune.model,
            max_seq_length=finetune.max_seq_length,
            huggingface_output_path=finetune.huggingface_output_path,
            private_repo=finetune.private_repo,
            ApiClient=ApiClient,
        )
    )
    return ResponseMessage(
        message=f"Fine-tuning of model {finetune.model_name} started. The agent's status has is now set to True, it will be set to False once the training is complete."
    )


# Delete memories from external source


@app.delete(
    "/api/agent/{agent_name}/memories/external_source",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete memories from external source",
    description="Deletes all memories from a specific external source. Requires admin access.",
)
async def delete_memories_from_external_source(
    agent_name: str,
    external_source: ExternalSource,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    if external_source.company_id is not None:
        auth = MagicalAuth(token=authorization)
        agixt = auth.get_company_agent_session(company_id=external_source.company_id)
        response = agixt.delete_memory_external_source(
            agent_name="AGiXT",
            external_source=external_source.external_source,
            collection_number=external_source.collection_number,
        )
        return ResponseMessage(message=response)
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=str(external_source.collection_number),
        ApiClient=ApiClient,
        user=user,
    ).delete_memories_from_external_source(
        external_source=external_source.external_source
    )
    return ResponseMessage(
        message=f"Memories from external source {external_source.external_source} for agent {agent_name} deleted."
    )


# Get unique external sources


@app.get(
    "/api/agent/{agent_name}/memory/external_sources/{collection_number}",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryCollectionResponse,
    summary="Get unique external sources",
    description="Retrieves a list of unique external sources in the specified collection.",
)
async def get_unique_external_sources(
    agent_name: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    external_sources = await Memories(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    ).get_external_data_sources()
    return {"external_sources": external_sources}


@app.post(
    "/api/agent/{agent_name}/learn/file/{company_id}",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Learn from file content",
    description="Processes and adds file content to the agent's memory. Supports various file types including PDFs, docs, and spreadsheets.",
)
async def learn_cfile(
    agent_name: str,
    company_id: str,
    file: FileInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    agixt = auth.get_company_agent_session(company_id=company_id)
    response = agixt.learn_file(
        agent_name="AGiXT",
        file_name=file.file_name,
        file_content=file.file_content,
        collection_number=file.collection_number,
    )
    return ResponseMessage(message=response)


# Get unique external sources


@app.get(
    "/api/agent/{agent_name}/memory/external_sources/{collection_number}/{company_id}",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryCollectionResponse,
    summary="Get unique external sources",
    description="Retrieves a list of unique external sources in the specified collection.",
)
async def get_cunique_external_sources(
    agent_name: str,
    company_id: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    agixt = auth.get_company_agent_session(company_id=company_id)
    response = agixt.get_memories_external_sources(
        agent_name="AGiXT",
        collection_number=collection_number,
    )
    return {"external_sources": response}


# RLHF endpoint


@app.post(
    "/api/agent/{agent_name}/feedback",
    tags=["Legacy-Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Submit RLHF feedback",
    description="Submits reinforcement learning from human feedback for an interaction.",
)
async def rlhf(
    agent_name: str,
    data: FeedbackInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    agixt = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=data.conversation_name,
    )
    c = agixt.conversation
    if c.has_received_feedback(message=data.message):
        return ResponseMessage(
            message="Feedback already received for this interaction."
        )
    if data.positive == True:
        memory = agixt.agent_interactions.agent_memory
    else:
        memory = agixt.agent_interactions.agent_memory
    reflection = await agixt.inference(
        user_input=data.user_input,
        input_kind="positive" if data.positive == True else "negative",
        assistant_response=data.message,
        feedback=data.feedback,
        log_user_input=False,
        log_output=False,
    )
    memory_message = f"""## Feedback received from a similar interaction in the past:
### User
{data.user_input}

### Assistant
{data.message}

### Feedback from User
{data.feedback}

### Reflection on the feedback
{reflection}
"""
    await memory.write_text_to_memory(
        user_input=data.user_input,
        text=memory_message,
        external_source="reflection from user feedback",
    )
    response_message = (
        f"{'Positive' if data.positive == True else 'Negative'} feedback received."
    )
    c.log_interaction(
        role=agent_name,
        message=f"[ACTIVITY][INFO] {response_message}",
    )
    c.toggle_feedback_received(message=data.message)
    return ResponseMessage(message=response_message)


# V1 Memory Endpoints using agent_id instead of agent_name


@app.get(
    "/api/agent/{agent_name}/extensions",
    tags=["Legacy-Agent"],
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
    tags=["Legacy-Agent"],
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


# V1 Extension Endpoints using agent_id instead of agent_name


@app.post(
    "/api/prompt/{prompt_category}",
    tags=["Legacy-Prompt"],
    response_model=ResponseMessage,
    summary="Add a new prompt",
    description="Create a new prompt in the specified category. Requires admin privileges.",
    dependencies=[Depends(verify_api_key)],
)
async def add_prompt(
    prompt: CustomPromptModel,
    prompt_category: str = "Default",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        Prompts(user=user).add_prompt(
            prompt_name=prompt.prompt_name,
            prompt=prompt.prompt,
            prompt_category=prompt_category,
        )
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' added.")
    except Exception as e:
        logging.error(f"Error adding prompt: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Legacy-Prompt"],
    response_model=CustomPromptModel,
    summary="Get a specific prompt",
    description="Retrieve a prompt by its name and category.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_with_category(
    prompt_name: str, prompt_category: str = "Default", user=Depends(verify_api_key)
):
    prompt_content = Prompts(user=user).get_prompt(
        prompt_name=prompt_name, prompt_category=prompt_category
    )
    return {
        "prompt_name": prompt_name,
        "prompt_category": prompt_category,
        "prompt": prompt_content,
    }


@app.get(
    "/api/prompt",
    response_model=PromptList,
    tags=["Legacy-Prompt"],
    summary="Get all prompts",
    description="Retrieve a list of all available prompts in the default category.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts(user=Depends(verify_api_key)):
    prompts = Prompts(user=user).get_prompts()
    return {"prompts": prompts}


@app.get(
    "/api/prompt/categories",
    response_model=PromptCategoryList,
    tags=["Legacy-Prompt"],
    summary="Get all prompt categories",
    description="Retrieve a list of all available prompt categories.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_categories(user=Depends(verify_api_key)):
    prompt_categories = Prompts(user=user).get_prompt_categories()
    return {"prompt_categories": prompt_categories}


@app.get(
    "/api/prompt/{prompt_category}",
    response_model=PromptList,
    tags=["Legacy-Prompt"],
    summary="Get prompts by category",
    description="Retrieve all prompts in a specific category.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts(prompt_category: str = "Default", user=Depends(verify_api_key)):
    prompts = Prompts(user=user).get_prompts(prompt_category=prompt_category)
    return {"prompts": prompts}


@app.delete(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Legacy-Prompt"],
    response_model=ResponseMessage,
    summary="Delete a prompt",
    description="Delete a specific prompt from a category. Requires admin privileges.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_prompt(
    prompt_name: str,
    prompt_category: str = "Default",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        Prompts(user=user).delete_prompt(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        return ResponseMessage(message=f"Prompt '{prompt_name}' deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.patch(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Legacy-Prompt"],
    response_model=ResponseMessage,
    summary="Rename a prompt",
    description="Rename an existing prompt in a category. Requires admin privileges.",
    dependencies=[Depends(verify_api_key)],
)
async def rename_prompt(
    prompt_name: str,
    new_name: PromptName,
    prompt_category: str = "Default",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        Prompts(user=user).rename_prompt(
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
    tags=["Legacy-Prompt"],
    response_model=ResponseMessage,
    summary="Update a prompt",
    description="Update the content of an existing prompt. Requires admin privileges.",
    dependencies=[Depends(verify_api_key)],
)
async def update_prompt(
    prompt: CustomPromptModel,
    prompt_category: str = "Default",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        Prompts(user=user).update_prompt(
            prompt_name=prompt.prompt_name,
            prompt=prompt.prompt,
            prompt_category=prompt_category,
        )
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get(
    "/api/prompt/{prompt_category}/{prompt_name}/args",
    tags=["Legacy-Prompt"],
    response_model=PromptArgsResponse,
    summary="Get prompt arguments",
    description="Retrieve the arguments required by a specific prompt.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_arg(
    prompt_name: str, prompt_category: str = "Default", user=Depends(verify_api_key)
):
    try:
        prompt_name = prompt_name.replace("%20", " ")
        prompt_category = prompt_category.replace("%20", " ")
        prompt = Prompts(user=user).get_prompt(
            prompt_name=prompt_name, prompt_category=prompt_category
        )
        return {"prompt_args": Prompts(user=user).get_prompt_args(prompt)}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Prompt not found.")


# V1 Prompt Endpoints using prompt_id instead of prompt_category/prompt_name


@app.get(
    "/api/chain",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=List[str],
    summary="Get all chains",
    description="Retrieves a list of all available chains for the authenticated user and global chains.",
)
async def get_chains(user=Depends(verify_api_key), authorization: str = Header(None)):
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    chains = Chain(user=user).get_chains()
    return chains


@app.get(
    "/api/chain/{chain_name}",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=Dict[str, ChainDetailsResponse],
    summary="Get chain details",
    description="Retrieves detailed information about a specific chain, including all steps and configurations.",
)
async def get_chain(chain_name: str, user=Depends(verify_api_key)):
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    chain_data = Chain(user=user).get_chain(chain_name=chain_name)
    if isinstance(chain_data["id"], UUID):  # Add this check and conversion
        chain_data["id"] = str(chain_data["id"])
    return {"chain": chain_data}


@app.post(
    "/api/chain/{chain_name}/run",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=str,
    summary="Run chain",
    description="Executes a chain with the specified name and returns the final output.",
)
async def run_chain(
    chain_name: str,
    user_input: RunChain,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    agents = get_agents(user=user)
    agent_name = agents[0]["name"]
    if user_input.agent_override:
        if user_input.agent_override in agents:
            agent_name = user_input.agent_override

    conversation_name = user_input.conversation_name
    chain_response = await AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=conversation_name,
    ).execute_chain(
        chain_name=chain_name,
        user_input=user_input.prompt,
        agent_override=user_input.agent_override,
        from_step=user_input.from_step,
        chain_args=user_input.chain_args,
        log_user_input=False,
        log_output=False,
    )
    try:
        if "Chain failed to complete" in chain_response:
            raise HTTPException(status_code=500, detail=f"{chain_response}")
    except:
        return f"{chain_response}"
    return chain_response


@app.post(
    "/api/chain/{chain_name}/run/step/{step_number}",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=str,
    summary="Run chain step",
    description="Executes a specific step within a chain and returns the output.",
)
async def run_chain_step(
    chain_name: str,
    step_number: str,
    user_input: RunChainStep,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    chain = Chain(user=user)
    chain_steps = chain.get_chain(chain_name=chain_name)
    try:
        step = chain_steps["step"][step_number]
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Step {step_number} not found. {e}"
        )
    agent_name = (
        user_input.agent_override if user_input.agent_override else step["agent"]
    )
    chain_step_response = await AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=user_input.conversation_name,
    ).run_chain_step(
        chain_run_id=user_input.chain_run_id,
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
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=Dict[str, List[str]],
    summary="Get chain arguments",
    description="Retrieves the list of available arguments for a specific chain.",
)
async def get_chain_args(
    chain_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
):
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    chain_args = Chain(user=user).get_chain_args(chain_name=chain_name)
    return {"chain_args": chain_args}


@app.post(
    "/api/chain",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Create new chain",
    description="Creates a new empty chain with the specified name.",
)
async def add_chain(
    chain_name: ChainName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_name.chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).add_chain(
        chain_name=chain_name.chain_name, description=chain_name.description
    )
    return ResponseMessage(message=f"Chain '{chain_name.chain_name}' created.")


@app.post(
    "/api/chain/import",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Import chain",
    description="Imports a chain configuration including all steps and settings.",
)
async def importchain(
    chain: ChainData, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if chain.chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    response = Chain(user=user).import_chain(
        chain_name=chain.chain_name, steps=chain.steps
    )
    return ResponseMessage(message=response)


@app.put(
    "/api/chain/{chain_name}",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Update chain",
    description="Updates the name and/or description of an existing chain.",
)
async def update_chain(
    chain_name: str,
    new_name: ChainNewName,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    chain = Chain(user=user)
    if new_name.new_name:
        chain.rename_chain(chain_name=chain_name, new_name=new_name.new_name)
        if not new_name.description:
            return ResponseMessage(
                message=f"Chain '{chain_name}' renamed to '{new_name.new_name}'."
            )
    if new_name.description:
        chain.update_description(
            chain_name=chain_name, description=new_name.description
        )
        if not new_name.new_name:
            return ResponseMessage(
                message=f"Description for chain '{chain_name}' updated to '{new_name.description}'."
            )
    return ResponseMessage(
        message=f"Chain '{chain_name}' updated with new name '{new_name.new_name}' and description '{new_name.description}'."
    )


@app.delete(
    "/api/chain/{chain_name}",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete chain",
    description="Deletes a chain and all its associated steps.",
)
async def delete_chain(
    chain_name: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).delete_chain(chain_name=chain_name)
    return ResponseMessage(message=f"Chain '{chain_name}' deleted.")


@app.post(
    "/api/chain/{chain_name}/step",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Add chain step",
    description="Adds a new step to an existing chain with specified configurations.",
)
async def add_step(
    chain_name: str,
    step_info: StepInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    ApiClient = get_api_client(authorization=authorization)
    Chain(user=user).add_chain_step(
        chain_name=chain_name,
        step_number=step_info.step_number,
        prompt_type=step_info.prompt_type,
        prompt=step_info.prompt,
        agent_name=step_info.agent_name,
    )
    return {"message": f"Step {step_info.step_number} added to chain '{chain_name}'."}


@app.put(
    "/api/chain/{chain_name}/step/{step_number}",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Update chain step",
    description="Updates the configuration of an existing step in the chain.",
)
async def update_step(
    chain_name: str,
    step_number: int,
    chain_step: ChainStep,
    user=Depends(verify_api_key),
) -> ResponseMessage:
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    Chain(user=user).update_step(
        chain_name=chain_name,
        step_number=step_number if step_number else chain_step.step_number,
        prompt_type=chain_step.prompt_type,
        prompt=chain_step.prompt,
        agent_name=chain_step.agent_name,
    )
    return {
        "message": f"Step {chain_step.step_number} updated for chain '{chain_name}'."
    }


@app.patch(
    "/api/chain/{chain_name}/step/move",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Move chain step",
    description="Changes the position of a step within the chain by updating its step number.",
)
async def move_step(
    chain_name: str,
    chain_step_new_info: ChainStepNewInfo,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).move_step(
        chain_name=chain_name,
        current_step_number=chain_step_new_info.old_step_number,
        new_step_number=chain_step_new_info.new_step_number,
    )
    return {
        "message": f"Step {chain_step_new_info.old_step_number} moved to {chain_step_new_info.new_step_number} in chain '{chain_name}'."
    }


@app.delete(
    "/api/chain/{chain_name}/step/{step_number}",
    tags=["Legacy-Chain"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete chain step",
    description="Removes a specific step from the chain.",
)
async def delete_step(
    chain_name: str,
    step_number: int,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if chain_name == "":
        raise HTTPException(status_code=400, detail="Chain name cannot be empty.")
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    Chain(user=user).delete_step(chain_name=chain_name, step_number=step_number)
    return {"message": f"Step {step_number} deleted from chain '{chain_name}'."}


# V1 Chain Endpoints using chain_id instead of chain_name
