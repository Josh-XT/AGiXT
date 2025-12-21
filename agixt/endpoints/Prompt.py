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


@app.post(
    "/v1/prompt/{prompt_id}/revert",
    tags=["Prompt"],
    response_model=ResponseMessage,
    summary="Revert a prompt to default",
    description="Revert a user's customized prompt back to the parent (server/company) version.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("prompts:write"))],
)
async def revert_prompt_to_default_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    result = Prompts(user=user).revert_prompt_to_default(prompt_id=prompt_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ResponseMessage(message=result["message"])


# =========================================================================
# Server-level prompt management (super admin only)
# =========================================================================


@app.get(
    "/v1/server/prompts",
    tags=["Server Prompts"],
    summary="Get all server-level prompts",
    description="Retrieve all server-level prompts. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def get_server_prompts_v1(
    include_internal: bool = False,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    prompts = Prompts(user=user).get_server_prompts(include_internal=include_internal)
    return {"prompts": prompts}


@app.post(
    "/v1/server/prompt",
    tags=["Server Prompts"],
    summary="Create a server-level prompt",
    description="Create a new server-level prompt. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def create_server_prompt_v1(
    prompt: CustomPromptModel,
    is_internal: bool = False,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> PromptResponse:
    prompt_id = Prompts(user=user).add_server_prompt(
        name=prompt.prompt_name,
        content=prompt.prompt,
        category=prompt.prompt_category,
        description="",
        is_internal=is_internal,
    )
    return PromptResponse(
        message=f"Server prompt '{prompt.prompt_name}' created.",
        id=prompt_id,
    )


# Categories must be defined BEFORE {prompt_id} to avoid route conflicts
@app.get(
    "/v1/server/prompt/categories",
    tags=["Server Prompts"],
    summary="Get all server-level prompt categories",
    description="Retrieve all server-level prompt categories. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def get_server_prompt_categories_v1(
    include_internal: bool = False,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    categories = Prompts(user=user).get_server_prompt_categories(
        include_internal=include_internal
    )
    return {"categories": categories}


@app.post(
    "/v1/server/prompt/category",
    tags=["Server Prompts"],
    summary="Create a server-level prompt category",
    description="Create a new server-level prompt category. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def create_server_prompt_category_v1(
    name: str,
    description: str = "",
    is_internal: bool = False,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    category_id = Prompts(user=user).add_server_prompt_category(
        name=name, description=description, is_internal=is_internal
    )
    return ResponseMessage(
        message=f"Server prompt category created with ID: {category_id}"
    )


@app.delete(
    "/v1/server/prompt/category/{category_id}",
    tags=["Server Prompts"],
    response_model=ResponseMessage,
    summary="Delete a server-level prompt category",
    description="Delete a server-level prompt category by ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def delete_server_prompt_category_v1(
    category_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).delete_server_prompt_category(category_id=category_id)
        return ResponseMessage(message="Server prompt category deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get(
    "/v1/server/prompt/{prompt_id}",
    tags=["Server Prompts"],
    summary="Get a server-level prompt by ID",
    description="Retrieve a specific server-level prompt by its ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def get_server_prompt_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    prompt = Prompts(user=user).get_server_prompt_by_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Server prompt not found")
    return prompt


@app.put(
    "/v1/server/prompt/{prompt_id}",
    tags=["Server Prompts"],
    response_model=ResponseMessage,
    summary="Update a server-level prompt",
    description="Update a server-level prompt by ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def update_server_prompt_v1(
    prompt_id: str,
    prompt: UpdatePromptModel,
    is_internal: bool = None,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).update_server_prompt(
            prompt_id=prompt_id,
            name=prompt.prompt_name,
            content=prompt.prompt,
            is_internal=is_internal,
        )
        return ResponseMessage(message="Server prompt updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete(
    "/v1/server/prompt/{prompt_id}",
    tags=["Server Prompts"],
    response_model=ResponseMessage,
    summary="Delete a server-level prompt",
    description="Delete a server-level prompt by ID. Super admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("server:prompts"))],
)
async def delete_server_prompt_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).delete_server_prompt(prompt_id=prompt_id)
        return ResponseMessage(message="Server prompt deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================================================================
# Company-level prompt management (company admin only)
# =========================================================================


@app.get(
    "/v1/company/prompts",
    tags=["Company Prompts"],
    summary="Get all company-level prompts",
    description="Retrieve all company-level prompts for the user's company. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def get_company_prompts_v1(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    prompts = Prompts(user=user).get_company_prompts()
    return {"prompts": prompts}


@app.post(
    "/v1/company/prompt",
    tags=["Company Prompts"],
    summary="Create a company-level prompt",
    description="Create a new company-level prompt. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def create_company_prompt_v1(
    prompt: CustomPromptModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> PromptResponse:
    prompt_id = Prompts(user=user).add_company_prompt(
        name=prompt.prompt_name,
        content=prompt.prompt,
        category=prompt.prompt_category,
        description="",
    )
    return PromptResponse(
        message=f"Company prompt '{prompt.prompt_name}' created.",
        id=prompt_id,
    )


# Categories must be defined BEFORE {prompt_id} to avoid route conflicts
@app.get(
    "/v1/company/prompt/categories",
    tags=["Company Prompts"],
    summary="Get all company-level prompt categories",
    description="Retrieve all company-level prompt categories. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def get_company_prompt_categories_v1(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    categories = Prompts(user=user).get_company_prompt_categories()
    return {"categories": categories}


@app.post(
    "/v1/company/prompt/category",
    tags=["Company Prompts"],
    summary="Create a company-level prompt category",
    description="Create a new company-level prompt category. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def create_company_prompt_category_v1(
    name: str,
    description: str = "",
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    category_id = Prompts(user=user).add_company_prompt_category(
        name=name, description=description
    )
    return ResponseMessage(
        message=f"Company prompt category created with ID: {category_id}"
    )


@app.delete(
    "/v1/company/prompt/category/{category_id}",
    tags=["Company Prompts"],
    response_model=ResponseMessage,
    summary="Delete a company-level prompt category",
    description="Delete a company-level prompt category by ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def delete_company_prompt_category_v1(
    category_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).delete_company_prompt_category(category_id=category_id)
        return ResponseMessage(message="Company prompt category deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post(
    "/v1/company/prompt/share/{prompt_id}",
    tags=["Company Prompts"],
    summary="Share a user prompt to company",
    description="Share a user's prompt to the company level. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("prompts:share"))],
)
async def share_prompt_to_company_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> PromptResponse:
    try:
        new_prompt_id = Prompts(user=user).share_prompt_to_company(prompt_id=prompt_id)
        return PromptResponse(
            message="Prompt shared to company.",
            id=new_prompt_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/v1/company/prompt/{prompt_id}",
    tags=["Company Prompts"],
    summary="Get a company-level prompt by ID",
    description="Retrieve a specific company-level prompt by its ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def get_company_prompt_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    prompt = Prompts(user=user).get_company_prompt_by_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Company prompt not found")
    return prompt


@app.put(
    "/v1/company/prompt/{prompt_id}",
    tags=["Company Prompts"],
    response_model=ResponseMessage,
    summary="Update a company-level prompt",
    description="Update a company-level prompt by ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def update_company_prompt_v1(
    prompt_id: str,
    prompt: UpdatePromptModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).update_company_prompt(
            prompt_id=prompt_id,
            name=prompt.prompt_name,
            content=prompt.prompt,
        )
        return ResponseMessage(message="Company prompt updated.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete(
    "/v1/company/prompt/{prompt_id}",
    tags=["Company Prompts"],
    response_model=ResponseMessage,
    summary="Delete a company-level prompt",
    description="Delete a company-level prompt by ID. Company admin only.",
    dependencies=[Depends(verify_api_key), Depends(require_scope("company:prompts"))],
)
async def delete_company_prompt_v1(
    prompt_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        Prompts(user=user).delete_company_prompt(prompt_id=prompt_id)
        return ResponseMessage(message="Company prompt deleted.")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
