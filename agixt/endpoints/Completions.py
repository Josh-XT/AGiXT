import string
import random
import time
from fastapi import APIRouter, Depends, Header
from Interactions import Interactions, get_tokens
from Embedding import Embedding
from ApiClient import Agent, verify_api_key, get_api_client
from Models import (
    Completions,
    EmbeddingModel,
)

app = APIRouter()


@app.post(
    "/api/v1/completions", tags=["Completions"], dependencies=[Depends(verify_api_key)]
)
async def completion(
    prompt: Completions, user=Depends(verify_api_key), authorization: str = Header(None)
):
    # prompt.model is the agent name
    ApiClient = get_api_client(authorization=authorization)
    agent = Interactions(agent_name=prompt.model, user=user, ApiClient=ApiClient)
    agent_config = agent.agent.AGENT_CONFIG
    if "settings" in agent_config:
        if "AI_MODEL" in agent_config["settings"]:
            model = agent_config["settings"]["AI_MODEL"]
        else:
            model = "undefined"
    else:
        model = "undefined"
    response = await agent.run(
        user_input=prompt.prompt,
        prompt="Custom Input",
        context_results=3,
        shots=prompt.n,
    )
    characters = string.ascii_letters + string.digits
    prompt_tokens = get_tokens(prompt.prompt)
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    random_chars = "".join(random.choice(characters) for _ in range(15))
    res_model = {
        "id": f"cmpl-{random_chars}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "text": response,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    return res_model


@app.post(
    "/api/v1/chat/completions",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
)
async def chat_completion(
    prompt: Completions, user=Depends(verify_api_key), authorization: str = Header(None)
):
    # prompt.model is the agent name
    ApiClient = get_api_client(authorization=authorization)
    agent = Interactions(agent_name=prompt.model, user=user, ApiClient=ApiClient)
    agent_config = agent.agent.AGENT_CONFIG
    if "settings" in agent_config:
        if "AI_MODEL" in agent_config["settings"]:
            model = agent_config["settings"]["AI_MODEL"]
        else:
            model = "undefined"
    else:
        model = "undefined"
    response = await agent.run(
        user_input=prompt.prompt,
        prompt="Custom Input",
        context_results=3,
        shots=prompt.n,
    )
    characters = string.ascii_letters + string.digits
    prompt_tokens = get_tokens(prompt.prompt)
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    random_chars = "".join(random.choice(characters) for _ in range(15))
    res_model = {
        "id": f"chatcmpl-{random_chars}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": [
                    {
                        "role": "assistant",
                        "content": response,
                    },
                ],
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    return res_model


# Use agent name in the model field to use embedding.
@app.post(
    "/api/v1/embedding", tags=["Completions"], dependencies=[Depends(verify_api_key)]
)
async def embedding(
    embedding: EmbeddingModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent_name = embedding.model
    agent_config = Agent(
        agent_name=agent_name, user=user, ApiClient=ApiClient
    ).get_agent_config()
    agent_settings = agent_config["settings"] if "settings" in agent_config else None
    tokens = get_tokens(embedding.input)
    embedding = Embedding(agent_settings=agent_settings).embed_text(
        text=embedding.input
    )
    return {
        "data": [{"embedding": embedding, "index": 0, "object": "embedding"}],
        "model": agent_name,
        "object": "list",
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }
