from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import Prompts, verify_api_key, is_admin
from Models import (
    PromptName,
    PromptList,
    PromptCategoryList,
    ResponseMessage,
    CustomPromptModel,
    PromptArgsResponse,
)
from Globals import getenv
import logging

app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@app.get(
    "/v1/prompt/{prompt_id}",
    tags=["Prompt"],
    response_model=CustomPromptModel,
    summary="Get a specific prompt by ID",
    description="Retrieve a prompt by its ID.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_by_id_v1(prompt_id: str, user=Depends(verify_api_key)):
    try:
        prompt_details = Prompts(user=user).get_prompt_details_by_id(
            prompt_id=prompt_id
        )
        if not prompt_details:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {
            "prompt_name": prompt_details["prompt_name"],
            "prompt_category": prompt_details["prompt_category"],
            "prompt": prompt_details["prompt"],
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail="Prompt not found")


@app.delete(
    "/v1/prompt/{prompt_id}",
    tags=["Prompt"],
    response_model=ResponseMessage,
    summary="Delete a prompt by ID",
    description="Delete a specific prompt by its ID. Requires admin privileges.",
    dependencies=[Depends(verify_api_key)],
)
async def delete_prompt_by_id_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        prompt_details = Prompts(user=user).get_prompt_details_by_id(
            prompt_id=prompt_id
        )
        if not prompt_details:
            raise HTTPException(status_code=404, detail="Prompt not found")
        Prompts(user=user).delete_prompt_by_id(prompt_id=prompt_id)
        return ResponseMessage(
            message=f"Prompt '{prompt_details['prompt_name']}' deleted."
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put(
    "/v1/prompt/{prompt_id}",
    tags=["Prompt"],
    response_model=ResponseMessage,
    summary="Update a prompt by ID",
    description="Update the content of an existing prompt by its ID. Requires admin privileges.",
    dependencies=[Depends(verify_api_key)],
)
async def update_prompt_by_id_v1(
    prompt_id: str,
    prompt: CustomPromptModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    if is_admin(email=user, api_key=authorization) != True:
        raise HTTPException(status_code=403, detail="Access Denied")
    try:
        Prompts(user=user).update_prompt_by_id(
            prompt_id=prompt_id,
            prompt_name=prompt.prompt_name,
            prompt=prompt.prompt,
        )
        return ResponseMessage(message=f"Prompt '{prompt.prompt_name}' updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get(
    "/v1/prompt/{prompt_id}/args",
    tags=["Prompt"],
    response_model=PromptArgsResponse,
    summary="Get prompt arguments by ID",
    description="Retrieve the arguments required by a specific prompt by its ID.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_args_by_id_v1(prompt_id: str, user=Depends(verify_api_key)):
    try:
        prompt_content = Prompts(user=user).get_prompt_by_id(prompt_id=prompt_id)
        if not prompt_content:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"prompt_args": Prompts(user=user).get_prompt_args(prompt_content)}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Prompt not found.")
