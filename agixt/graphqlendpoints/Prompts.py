from typing import List, Optional
import strawberry
from fastapi import HTTPException
from ApiClient import verify_api_key
from endpoints.Prompt import (
    add_prompt as rest_add_prompt,
    get_prompt_with_category as rest_get_prompt,
    get_prompts as rest_get_prompts,
    get_prompt_categories as rest_get_prompt_categories,
    get_prompt_arg as rest_get_prompt_args,
    delete_prompt as rest_delete_prompt,
    update_prompt as rest_update_prompt,
    rename_prompt as rest_rename_prompt,
)


# Convert Pydantic models to Strawberry types
@strawberry.type
class Prompt:
    prompt_name: str
    prompt: str


@strawberry.type
class CustomPromptModel:
    prompt_name: str
    prompt: str


@strawberry.type
class PromptName:
    name: str


@strawberry.type
class ResponseMessage:
    message: str


@strawberry.type
class PromptListType:
    prompts: List[str]


@strawberry.type
class PromptCategoryListType:
    prompt_categories: List[str]


@strawberry.type
class PromptArgsResponseType:
    prompt_args: List[str]


# Input types
@strawberry.input
class PromptInput:
    prompt_name: str
    prompt: str


@strawberry.type
class Query:
    @strawberry.field
    async def prompt(
        self, info, prompt_name: str, prompt_category: str = "Default"
    ) -> Optional[Prompt]:
        try:
            # Reuse the REST endpoint function
            result = await rest_get_prompt(
                prompt_name=prompt_name,
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
            )
            return Prompt.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def prompts(self, info, prompt_category: str = "Default") -> PromptListType:
        try:
            # Reuse the REST endpoint function
            result = await rest_get_prompts(
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
            )
            return PromptListType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def prompt_categories(self, info) -> PromptCategoryListType:
        try:
            # Reuse the REST endpoint function
            result = await rest_get_prompt_categories(
                user=await verify_api_key(info.context["request"])
            )
            return PromptCategoryListType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.field
    async def prompt_arguments(
        self, info, prompt_name: str, prompt_category: str = "Default"
    ) -> PromptArgsResponseType:
        try:
            # Reuse the REST endpoint function
            result = await rest_get_prompt_args(
                prompt_name=prompt_name,
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
            )
            return PromptArgsResponseType.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def add_prompt(
        self, info, prompt: PromptInput, prompt_category: str = "Default"
    ) -> ResponseMessage:
        try:
            # Convert input to Pydantic model and reuse REST endpoint
            prompt_model = CustomPromptModel(
                prompt_name=prompt.prompt_name, prompt=prompt.prompt
            )
            result = await rest_add_prompt(
                prompt=prompt_model,
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
                authorization=info.context["request"].headers.get("authorization"),
            )
            return ResponseMessage.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def update_prompt(
        self, info, prompt: PromptInput, prompt_category: str = "Default"
    ) -> ResponseMessage:
        try:
            prompt_model = CustomPromptModel(
                prompt_name=prompt.prompt_name, prompt=prompt.prompt
            )
            result = await rest_update_prompt(
                prompt=prompt_model,
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
                authorization=info.context["request"].headers.get("authorization"),
            )
            return ResponseMessage.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def delete_prompt(
        self, info, prompt_name: str, prompt_category: str = "Default"
    ) -> ResponseMessage:
        try:
            result = await rest_delete_prompt(
                prompt_name=prompt_name,
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
                authorization=info.context["request"].headers.get("authorization"),
            )
            return ResponseMessage.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def rename_prompt(
        self,
        info,
        prompt_name: str,
        new_name: PromptName,
        prompt_category: str = "Default",
    ) -> ResponseMessage:
        try:
            result = await rest_rename_prompt(
                prompt_name=prompt_name,
                new_name=new_name,
                prompt_category=prompt_category,
                user=await verify_api_key(info.context["request"]),
                authorization=info.context["request"].headers.get("authorization"),
            )
            return ResponseMessage.from_pydantic(result)
        except HTTPException as e:
            raise Exception(str(e.detail))


# Create the schema
schema = strawberry.Schema(query=Query, mutation=Mutation)
