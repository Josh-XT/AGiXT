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
    ResponseMessage,
    UrlInput,
    TTSInput,
    TaskPlanInput,
    ChatCompletions,
)
import logging
import base64
import uuid
import os
from datetime import datetime

app = APIRouter()


@app.post("/api/agent", tags=["Agent"], dependencies=[Depends(verify_api_key)])
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


@app.post("/api/agent/import", tags=["Agent"], dependencies=[Depends(verify_api_key)])
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
    new_settings = {}
    for key in settings.settings:
        if settings.settings[key] != "HIDDEN":
            new_settings[key] = settings.settings[key]
    update_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).update_agent_config(new_config=settings.settings, config_key="settings")
    return ResponseMessage(message=update_config)


@app.put(
    "/api/agent/{agent_name}/commands",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
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


@app.get("/api/agent", tags=["Agent"], dependencies=[Depends(verify_api_key)])
async def getagents(user=Depends(verify_api_key), authorization: str = Header(None)):
    agents = get_agents(user=user)
    create_agent = str(getenv("CREATE_AGENT_ON_REGISTER")).lower() == "true"
    if create_agent:
        agent_list = [agent["name"] for agent in agents]
        agent_name = getenv("AGIXT_AGENT")
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
        upper_key = str(key).upper()
        if (
            upper_key.endswith("_KEY")
            or upper_key.endswith("_PASSWORD")
            or upper_key.endswith("_SECRET")
            or upper_key.endswith("_TOKEN")
        ):
            agent_config["settings"][key] = "HIDDEN"
    return {"agent": agent_config}


@app.post(
    "/api/agent/{agent_name}/prompt",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
)
async def prompt_agent(
    agent_name: str,
    agent_prompt: AgentPrompt,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    if "conversation_name" not in agent_prompt.prompt_args:
        conversation_name = datetime.now().strftime("%Y%m%d%H%M%S")
        agent_prompt.prompt_args["log_user_input"] = False
        agent_prompt.prompt_args["log_output"] = False
    else:
        conversation_name = agent_prompt.prompt_args["conversation_name"]
        del agent_prompt.prompt_args["conversation_name"]
    if "user_input" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["user_input"] = ""
    agent = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=conversation_name,
    )
    agent_prompt.prompt_args["prompt_name"] = agent_prompt.prompt_name
    if "prompt_category" not in agent_prompt.prompt_args:
        agent_prompt.prompt_args["prompt_category"] = "Default"
    logging.info(f"Initialized with conversation ID: {agent.conversation_id}")
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
    logging.info(f"Prompting agent '{agent_name}' with messages: {messages}")
    response = await agent.chat_completions(
        prompt=ChatCompletions(
            model=agent_name,
            user=conversation_name,
            messages=messages,
        )
    )
    response = response["choices"][0]["message"]["content"]
    return {"response": str(response)}


@app.get(
    "/api/agent/{agent_name}/command",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
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
    try:
        if payload.command_name == "*":
            for each_command_name in agent.AGENT_CONFIG["commands"]:
                agent.AGENT_CONFIG["commands"][each_command_name] = payload.enable

            agent.update_agent_config(
                new_config=agent.AGENT_CONFIG["commands"], config_key="commands"
            )
            return ResponseMessage(
                message=f"All commands enabled for agent '{agent_name}'."
            )
        else:
            agent.AGENT_CONFIG["commands"][payload.command_name] = payload.enable
            agent.update_agent_config(
                new_config=agent.AGENT_CONFIG["commands"], config_key="commands"
            )
            return ResponseMessage(
                message=f"Command '{payload.command_name}' toggled for agent '{agent_name}'."
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error enabling all commands for agent '{agent_name}': {str(e)}",
        )


# Get agent browsed links
@app.get(
    "/api/agent/{agent_name}/browsed_links/{collection_number}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
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
    websearch.agent_memory.delete_memories_from_external_source(url=url.url)
    agent.delete_browsed_link(url=url.url, conversation_id=url.collection_number)
    return {"message": "Browsed links deleted."}


@app.post(
    "/api/agent/{agent_name}/text_to_speech",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
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
    tts_response = await agent.text_to_speech(text=text.text)
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
