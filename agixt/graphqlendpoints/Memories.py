from typing import List, Dict, Any, Optional
import strawberry
from fastapi import Depends, HTTPException, Header
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
from endpoints.Memory import (
    query_memories as rest_query_memories,
    export_agent_memories as rest_export_memories,
    import_agent_memories as rest_import_memories,
    learn_text as rest_learn_text,
    learn_file as rest_learn_file,
    learn_url as rest_learn_url,
    wipe_agent_memories as rest_wipe_memories,
    delete_agent_memory as rest_delete_memory,
    create_dataset as rest_create_dataset,
    get_dpo_response as rest_get_dpo,
    fine_tune_model as rest_fine_tune,
    delete_memories_from_external_source as rest_delete_external_source,
    get_unique_external_sources as rest_get_external_sources,
    rlhf as rest_rlhf,
)
from ApiClient import verify_api_key


# Convert Pydantic models to Strawberry types
@strawberry.experimental.pydantic.type(model=MemoryResponse)
class MemoryResponseType:
    memories: List[Dict[str, Any]]


@strawberry.experimental.pydantic.type(model=MemoryCollectionResponse)
class MemoryCollectionResponseType:
    external_sources: List[str]


@strawberry.experimental.pydantic.type(model=ResponseMessage)
class ResponseMessageType:
    message: str


@strawberry.experimental.pydantic.type(model=DPOResponse)
class DPOResponseType:
    prompt: str
    chosen: str
    rejected: str


# Input types
@strawberry.input
class MemoryQueryInput:
    user_input: str
    limit: int = 5
    min_relevance_score: float = 0.0


@strawberry.input
class TextInput:
    user_input: str
    text: str
    collection_number: str = "0"


@strawberry.input
class FileInputType:
    file_name: str
    file_content: str
    collection_number: str = "0"


@strawberry.input
class URLInput:
    url: str
    collection_number: str = "0"


@strawberry.input
class DatasetInput:
    batch_size: int = 5


@strawberry.input
class FinetuneInput:
    model: str = "unsloth/mistral-7b-v0.2"
    max_seq_length: int = 16384
    huggingface_output_path: str = "JoshXT/finetuned-mistral-7b-v0.2"
    private_repo: bool = True


@strawberry.input
class ExternalSourceInput:
    external_source: str
    collection_number: str = "0"
    company_id: Optional[str] = None


@strawberry.input
class FeedbackInputType:
    user_input: str
    message: str
    feedback: str
    positive: bool = True
    conversation_name: str = ""


# Helper for auth
async def get_auth_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        return user, request.headers.get("authorization")
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class Query:
    @strawberry.field
    async def query_memories(
        self,
        info,
        agent_name: str,
        query: MemoryQueryInput,
        collection_number: str = "0",
    ) -> MemoryResponseType:
        """Query agent memories from a specific collection"""
        user, auth = await get_auth_context(info)
        result = await rest_query_memories(
            agent_name=agent_name,
            memory=AgentMemoryQuery(**query.__dict__),
            collection_number=collection_number,
            user=user,
            authorization=auth,
        )
        return MemoryResponseType.from_pydantic(result)

    @strawberry.field
    async def export_memories(self, info, agent_name: str) -> MemoryResponseType:
        """Export all agent memories"""
        user, auth = await get_auth_context(info)
        result = await rest_export_memories(
            agent_name=agent_name, user=user, authorization=auth
        )
        return MemoryResponseType.from_pydantic(result)

    @strawberry.field
    async def get_dpo_response(
        self, info, agent_name: str, input: str, injected_memories: int = 10
    ) -> DPOResponseType:
        """Get DPO response for question"""
        user, auth = await get_auth_context(info)
        result = await rest_get_dpo(
            agent_name=agent_name,
            user_input=UserInput(user_input=input, injected_memories=injected_memories),
            user=user,
            authorization=auth,
        )
        return DPOResponseType.from_pydantic(result)

    @strawberry.field
    async def get_external_sources(
        self, info, agent_name: str, collection_number: str = "0"
    ) -> MemoryCollectionResponseType:
        """Get unique external sources"""
        user, auth = await get_auth_context(info)
        result = await rest_get_external_sources(
            agent_name=agent_name,
            collection_number=collection_number,
            user=user,
            authorization=auth,
        )
        return MemoryCollectionResponseType.from_pydantic(result)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def import_memories(
        self, info, agent_name: str, memories: List[Dict[str, Any]]
    ) -> ResponseMessageType:
        """Import memories into agent"""
        user, auth = await get_auth_context(info)
        result = await rest_import_memories(
            agent_name=agent_name, memories=memories, user=user, authorization=auth
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def learn_text(
        self, info, agent_name: str, input: TextInput
    ) -> ResponseMessageType:
        """Learn from text input"""
        user, auth = await get_auth_context(info)
        result = await rest_learn_text(
            agent_name=agent_name,
            data=TextMemoryInput(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def learn_file(
        self, info, agent_name: str, input: FileInputType
    ) -> ResponseMessageType:
        """Learn from file content"""
        user, auth = await get_auth_context(info)
        result = await rest_learn_file(
            agent_name=agent_name,
            file=FileInput(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def learn_url(
        self, info, agent_name: str, input: URLInput
    ) -> ResponseMessageType:
        """Learn from URL content"""
        user, auth = await get_auth_context(info)
        result = await rest_learn_url(
            agent_name=agent_name,
            url=UrlInput(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def wipe_memories(
        self, info, agent_name: str, collection_number: Optional[str] = None
    ) -> ResponseMessageType:
        """Delete all agent memories or memories from specific collection"""
        user, auth = await get_auth_context(info)
        if collection_number:
            result = await rest_wipe_memories(
                agent_name=agent_name,
                collection_number=collection_number,
                user=user,
                authorization=auth,
            )
        else:
            result = await rest_wipe_memories(
                agent_name=agent_name, user=user, authorization=auth
            )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def delete_memory(
        self, info, agent_name: str, memory_id: str, collection_number: str = "0"
    ) -> ResponseMessageType:
        """Delete specific memory"""
        user, auth = await get_auth_context(info)
        result = await rest_delete_memory(
            agent_name=agent_name,
            collection_number=collection_number,
            memory_id=memory_id,
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def create_dataset(
        self, info, agent_name: str, input: DatasetInput
    ) -> ResponseMessageType:
        """Create dataset from memories"""
        user, auth = await get_auth_context(info)
        result = await rest_create_dataset(
            agent_name=agent_name,
            dataset=Dataset(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def fine_tune(
        self, info, agent_name: str, dataset_name: str, input: FinetuneInput
    ) -> ResponseMessageType:
        """Fine tune a language model"""
        user, auth = await get_auth_context(info)
        result = await rest_fine_tune(
            agent_name=agent_name,
            dataset_name=dataset_name,
            finetune=FinetuneAgentModel(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def delete_external_source_memories(
        self, info, agent_name: str, input: ExternalSourceInput
    ) -> ResponseMessageType:
        """Delete memories from external source"""
        user, auth = await get_auth_context(info)
        result = await rest_delete_external_source(
            agent_name=agent_name,
            external_source=ExternalSource(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)

    @strawberry.mutation
    async def submit_feedback(
        self, info, agent_name: str, input: FeedbackInputType
    ) -> ResponseMessageType:
        """Submit RLHF feedback"""
        user, auth = await get_auth_context(info)
        result = await rest_rlhf(
            agent_name=agent_name,
            data=FeedbackInput(**input.__dict__),
            user=user,
            authorization=auth,
        )
        return ResponseMessageType.from_pydantic(result)


# Create the schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
