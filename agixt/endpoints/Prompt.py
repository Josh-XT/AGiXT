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


@app.post(
    "/api/prompt/{prompt_category}",
    tags=["Prompt"],
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
    tags=["Prompt"],
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
    tags=["Prompt"],
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
    tags=["Prompt"],
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
    tags=["Prompt"],
    summary="Get prompts by category",
    description="Retrieve all prompts in a specific category.",
    dependencies=[Depends(verify_api_key)],
)
async def get_prompts(prompt_category: str = "Default", user=Depends(verify_api_key)):
    prompts = Prompts(user=user).get_prompts(prompt_category=prompt_category)
    return {"prompts": prompts}


@app.delete(
    "/api/prompt/{prompt_category}/{prompt_name}",
    tags=["Prompt"],
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
    tags=["Prompt"],
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
    tags=["Prompt"],
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
    tags=["Prompt"],
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
