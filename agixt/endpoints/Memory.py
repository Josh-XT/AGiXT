import os
import base64
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import Agent, verify_api_key, get_api_client, WORKERS, is_admin
from MagicalAuth import require_scope
from typing import Dict, Any, List
from Websearch import Websearch
from XT import AGiXT
from Memories import Memories
from Conversations import Conversations
from datetime import datetime
from Models import (
    AgentMemoryQuery,
    TextMemoryInput,
    FileInput,
    UrlInput,
    ResponseMessage,
    Dataset,
    FinetuneAgentModel,
    ExternalSource,
    UserInput,
    FeedbackInput,
    MemoryResponse,
    MemoryCollectionResponse,
    DPOResponse,
)
import logging
from Globals import getenv
from MagicalAuth import MagicalAuth

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
app = APIRouter()


@app.post(
    "/v1/agent/{agent_id}/memory/{collection_number}/query",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryResponse,
    summary="Query agent memories from a specific collection by ID",
    description="Retrieves memories based on user input with relevance scoring and limiting options using agent ID.",
)
async def query_memories_v1(
    agent_id: str,
    memory: AgentMemoryQuery,
    collection_number="0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    # Use lightweight settings-only method for faster memory queries
    agent_settings = agent.get_agent_settings_only()
    agent_config = {"settings": agent_settings, "commands": {}}
    memories = await Memories(
        agent_name=agent.agent_name,
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


@app.get(
    "/v1/agent/{agent_id}/memory/export",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryResponse,
    summary="Export all agent memories by ID",
    description="Exports all memories from all collections for the specified agent using agent ID.",
)
async def export_agent_memories_v1(
    agent_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> Dict[str, Any]:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_config = agent.get_agent_config()
    memories = await Memories(
        agent_name=agent.agent_name,
        agent_config=agent_config,
        ApiClient=ApiClient,
        user=user,
    ).export_collections_to_json()
    return {"memories": memories}


@app.post(
    "/v1/agent/{agent_id}/memory/import",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Import memories into agent by ID",
    description="Imports a list of memories into the agent's various collections using agent ID.",
)
async def import_agent_memories_v1(
    agent_id: str,
    memories: List[dict],
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_config = agent.get_agent_config()
    await Memories(
        agent_name=agent.agent_name,
        agent_config=agent_config,
        ApiClient=ApiClient,
        user=user,
    ).import_collections_from_json(memories)
    return ResponseMessage(message="Memories imported.")


@app.post(
    "/v1/agent/{agent_id}/learn/text",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("memories:write"))],
    response_model=ResponseMessage,
    summary="Learn from text input by ID",
    description="Adds text content to the agent's memory with associated user input context using agent ID.",
)
async def learn_text_v1(
    agent_id: str,
    data: TextMemoryInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_config = agent.get_agent_config()
    if len(data.collection_number) > 4:
        conversation = Conversations(
            conversation_name=data.collection_number, user=user
        )
        collection_number = conversation.get_conversation_id()
    else:
        collection_number = str(data.collection_number)
    memory = Memories(
        agent_name=agent.agent_name,
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
    "/v1/agent/{agent_id}/learn/file",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Learn from file content by ID",
    description="Processes and adds file content to the agent's memory using agent ID. Supports various file types including PDFs, docs, and spreadsheets.",
)
async def learn_file_v1(
    agent_id: str,
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

    # Get agent name from agent_id
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

    agixt_agent = AGiXT(
        user=user,
        agent_name=agent_name,
        api_key=authorization,
        conversation_name=conversation_name,
        collection_id=collection_number,
    )
    file.file_name = os.path.basename(file.file_name)
    file_path = os.path.normpath(
        os.path.join(
            agixt_agent.agent_workspace, file.collection_number, file.file_name
        )
    )
    if not file_path.startswith(agixt_agent.agent_workspace):
        raise Exception("Path given not allowed")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        file_content = base64.b64decode(file.file_content)
    except:
        file_content = file.file_content.encode("utf-8")
    with open(file_path, "wb") as f:
        f.write(file_content)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    response = await agixt_agent.learn_from_file(
        file_url=f"{agixt_agent.outputs}/{file.collection_number}/{file.file_name}",
        file_name=file.file_name,
        user_input=f"File {file.file_name} uploaded on {timestamp}.",
        collection_id=str(file.collection_number),
        save_to_memory=True,
    )
    agixt_agent.conversation.log_interaction(
        role=agent_name,
        message=f"File [{file.file_name}]({agixt_agent.outputs}/{file.collection_number}/{file.file_name}) learned on {timestamp} to collection `{file.collection_number}`.",
    )
    return ResponseMessage(message=response)


@app.post(
    "/v1/agent/{agent_id}/learn/url",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Learn from URL content by ID",
    description="Scrapes and learns from content at the specified URL using agent ID.",
)
async def learn_url_v1(
    agent_id: str,
    url: UrlInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    url.url = url.url.replace(" ", "%20")
    websearch = Websearch(
        collection_number=url.collection_number,
        agent=agent,
        user=user,
        ApiClient=ApiClient,
    )
    conversation_name = f"{agent.agent_name} Training on {timestamp}"
    response = await websearch.scrape_websites(
        user_input=f"I am browsing {url.url} and collecting data from it to learn more.",
        conversation_name=conversation_name,
    )
    c = Conversations(conversation_name=conversation_name, user=user)
    c.log_interaction(
        role=agent.agent_name,
        message=f"URL [{url.url}]({url.url}) learned on {timestamp} to collection `{url.collection_number}`.",
    )
    return ResponseMessage(message=response)


@app.delete(
    "/v1/agent/{agent_id}/memory",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("memories:delete"))],
    response_model=ResponseMessage,
    summary="Delete all agent memories by ID",
    description="Wipes all memories for the specified agent using agent ID. Requires admin access.",
)
async def wipe_agent_memories_v1(
    agent_id: str, user=Depends(verify_api_key), authorization: str = Header(None)
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent.agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number="0",
        ApiClient=ApiClient,
        user=user,
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent.agent_name} deleted.")


@app.delete(
    "/v1/agent/{agent_id}/memory/{collection_number}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("memories:delete"))],
    response_model=ResponseMessage,
    summary="Delete memories from specific collection by ID",
    description="Wipes memories from a specific collection using agent ID. Requires admin access.",
)
async def wipe_agent_memories_collection_v1(
    agent_id: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent.agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent.agent_name} deleted.")


@app.delete(
    "/v1/agent/{agent_id}/memory/{collection_number}/{memory_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Delete specific memory by ID",
    description="Deletes a specific memory by its ID from a collection using agent ID.",
)
async def delete_agent_memory_v1(
    agent_id: str,
    collection_number: str = "0",
    memory_id="",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent.agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    ).delete_memory(key=memory_id)
    return ResponseMessage(
        message=f"Memory {memory_id} for agent {agent.agent_name} deleted."
    )


@app.post(
    "/v1/agent/{agent_id}/memory/dataset",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:train"))],
    response_model=ResponseMessage,
    summary="Create dataset from memories by ID",
    description="Creates a training dataset from the agent's memories using agent ID. Requires admin access.",
)
async def create_dataset_v1(
    agent_id: str,
    dataset: Dataset,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    batch_size = dataset.batch_size if dataset.batch_size < (int(WORKERS) - 2) else 4
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get agent name from agent_id
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

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
    "/v1/agent/{agent_id}/dpo",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=DPOResponse,
    summary="Get DPO response for question by ID",
    description="Generates a DPO (Direct Preference Optimization) response including prompt, chosen and rejected outputs using agent ID.",
)
async def get_dpo_response_v1(
    agent_id: str,
    user_input: UserInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get agent name from agent_id
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

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


@app.post(
    "/v1/agent/{agent_id}/memory/dataset/{dataset_name}/finetune",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("agents:train"))],
    summary="Fine tune a language model with the agent's memories as a synthetic dataset by ID",
)
async def fine_tune_model_v1(
    agent_id: str,
    finetune: FinetuneAgentModel,
    dataset_name: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    from Tuning import fine_tune_llm

    # Get agent name from agent_id
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

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


@app.delete(
    "/v1/agent/{agent_id}/memories/external_source",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key), Depends(require_scope("memories:delete"))],
    response_model=ResponseMessage,
    summary="Delete memories from external source by ID",
    description="Deletes all memories from a specific external source using agent ID. Requires admin access.",
)
async def delete_memories_from_external_source_v1(
    agent_id: str,
    external_source: ExternalSource,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
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
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    await Memories(
        agent_name=agent.agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=str(external_source.collection_number),
        ApiClient=ApiClient,
        user=user,
    ).delete_memories_from_external_source(
        external_source=external_source.external_source
    )
    return ResponseMessage(
        message=f"Memories from external source {external_source.external_source} for agent {agent.agent_name} deleted."
    )


@app.get(
    "/v1/agent/{agent_id}/memory/external_sources/{collection_number}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryCollectionResponse,
    summary="Get unique external sources by ID",
    description="Retrieves a list of unique external sources in the specified collection using agent ID.",
)
async def get_unique_external_sources_v1(
    agent_id: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    external_sources = await Memories(
        agent_name=agent.agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=user,
    ).get_external_data_sources()
    return {"external_sources": external_sources}


@app.post(
    "/v1/agent/{agent_id}/learn/file/{company_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    summary="Learn from file content by ID with company",
    description="Processes and adds file content to the agent's memory using agent ID with company context.",
)
async def learn_cfile_v1(
    agent_id: str,
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


@app.get(
    "/v1/agent/{agent_id}/memory/external_sources/{collection_number}/{company_id}",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=MemoryCollectionResponse,
    summary="Get unique external sources by ID with company",
    description="Retrieves a list of unique external sources in the specified collection using agent ID with company context.",
)
async def get_cunique_external_sources_v1(
    agent_id: str,
    company_id: str,
    collection_number: str = "0",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    auth = MagicalAuth(token=authorization)
    # Verify user has access to this company
    if str(company_id) not in auth.get_user_companies():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized. Insufficient permissions.",
        )
    # Use company email as user context for memory scoping
    company_user = f"{company_id}@{company_id}.xt"
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    external_sources = await Memories(
        agent_name=agent.agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
        ApiClient=ApiClient,
        user=company_user,
    ).get_external_data_sources()
    return {"external_sources": external_sources}


@app.post(
    "/v1/agent/{agent_id}/feedback",
    tags=["Agent"],
    dependencies=[Depends(verify_api_key)],
    response_model=ResponseMessage,
    summary="Submit RLHF feedback by ID",
    description="Submits reinforcement learning from human feedback for an interaction using agent ID.",
)
async def rlhf_v1(
    agent_id: str,
    data: FeedbackInput,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    # Get agent name from agent_id
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_id=agent_id, user=user, ApiClient=ApiClient)
    agent_name = agent.agent_name

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
