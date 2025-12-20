from fastapi import APIRouter, HTTPException, Depends, Header
from ApiClient import Prompts, verify_api_key, is_admin
from MagicalAuth import require_scope
from Models import (
    PromptName,
    PromptList,
    PromptCategoryList,
    ResponseMessage,
    PromptResponse,
    CustomPromptModel,
    UpdatePromptModel,
    PromptArgsResponse,
)
from Globals import getenv
import logging

app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


# Static routes MUST come before dynamic routes to avoid path conflicts
@app.get(
    "/v1/prompts",
    tags=["Prompt"],
    summary="Get all prompts with IDs",
    description="Retrieve all prompts for a category including their IDs.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts_v1(
    category: str = "Default",
    prompt_category: str = None,
    user=Depends(verify_api_key),
):
    # Support both 'category' and 'prompt_category' params for backwards compatibility
    cat = prompt_category if prompt_category else category
    prompts = Prompts(user=user).get_prompts(prompt_category=cat, include_ids=True)
    return {"prompts": prompts, "category": cat}


@app.get(
    "/v1/prompt/categories",
    tags=["Prompt"],
    summary="Get all prompt categories with IDs",
    description="Retrieve all prompt categories including their IDs.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompt_categories_v1(user=Depends(verify_api_key)):
    categories = Prompts(user=user).get_prompt_categories(include_ids=True)
    return {"categories": categories, "prompt_categories": categories}


@app.get(
    "/v1/prompt/all",
    tags=["Prompt"],
    summary="Get all user and global prompts with full details",
    description="Retrieve all global and user prompts with their IDs and full details.",
    dependencies=[Depends(verify_api_key)],
)
async def get_all_prompts_v1(user=Depends(verify_api_key)):
    global_prompts = Prompts(user=user).get_global_prompts()
    user_prompts = Prompts(user=user).get_user_prompts()
    return {"global_prompts": global_prompts, "user_prompts": user_prompts}


@app.get(
    "/v1/prompt/category/{category_id}",
    tags=["Prompt"],
    summary="Get prompts by category ID",
    description="Retrieve all prompts for a specific category by category ID.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts_by_category_id_v1(category_id: str, user=Depends(verify_api_key)):
    prompts = Prompts(user=user).get_prompts_by_category_id(category_id=category_id)
    return {"prompts": prompts, "category_id": category_id}


@app.post(
    "/v1/prompt",
    tags=["Prompt"],
    summary="Create a new prompt",
    description="Create a new prompt with the specified name, content, and category. Returns the prompt ID.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("prompts:write"))],
)
async def create_prompt_v1(
    prompt: CustomPromptModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> PromptResponse:
    prompt_id = Prompts(user=user).add_prompt(
        prompt_name=prompt.prompt_name,
        prompt=prompt.prompt,
        prompt_category=prompt.prompt_category,
    )
    return PromptResponse(
        message=f"Prompt '{prompt.prompt_name}' created with ID: {prompt_id}",
        id=prompt_id,
    )


# Dynamic routes with path parameters come AFTER static routes
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
    dependencies=[Depends(verify_api_key), Depends(require_scope("prompts:delete"))],
)
async def delete_prompt_by_id_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
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
    dependencies=[Depends(verify_api_key), Depends(require_scope("prompts:write"))],
)
async def update_prompt_by_id_v1(
    prompt_id: str,
    prompt: UpdatePromptModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).update_prompt_by_id(
            prompt_id=prompt_id,
            prompt_name=prompt.prompt_name,
            prompt=prompt.prompt,
        )
        return ResponseMessage(message=f"Prompt updated.")
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
