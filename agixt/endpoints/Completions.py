import string
import random
import time
import requests
import base64
import PIL
import uuid
from fastapi import APIRouter, Depends, Header
from Interactions import Interactions, get_tokens
from Embedding import Embedding
from ApiClient import Agent, verify_api_key, get_api_client
from readers.file import FileReader
from readers.website import WebsiteReader
from AudioToText import AudioToText
from Models import (
    Completions,
    ChatCompletions,
    EmbeddingModel,
)

app = APIRouter()


@app.post(
    "/v1/completions",
    tags=["OpenAI Style Endpoints"],
    dependencies=[Depends(verify_api_key)],
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
    "/v1/chat/completions",
    tags=["OpenAI Style Endpoints"],
    dependencies=[Depends(verify_api_key)],
)
async def chat_completion(
    prompt: ChatCompletions,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
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
    images = []
    pil_images = []
    new_prompt = ""
    for message in prompt.messages:
        if isinstance(message["content"], str):
            role = message["role"] if "role" in message else "User"
            if role.lower() == "user":
                new_prompt += f"{message['content']}\n\n"
            if role.lower() == "system":
                new_prompt = f"System: {message['content']}\n\nUser: {new_prompt}"
        if isinstance(message["content"], list):
            for msg in message["content"]:
                if "text" in msg:
                    role = message["role"] if "role" in message else "User"
                    if role.lower() == "user":
                        new_prompt += f"{msg['text']}\n\n"
                if "image_url" in msg:
                    url = (
                        msg["image_url"]["url"]
                        if "url" in msg["image_url"]
                        else msg["image_url"]
                    )
                    image_path = f"./WORKSPACE/{uuid.uuid4().hex}.jpg"
                    if url.startswith("http"):
                        image = requests.get(url).content
                    else:
                        file_type = url.split(",")[0].split("/")[1].split(";")[0]
                        if file_type == "jpeg":
                            file_type = "jpg"
                        image_path = f"./WORKSPACE/{uuid.uuid4().hex}.{file_type}"
                        image = base64.b64decode(url.split(",")[1])
                    with open(image_path, "wb") as f:
                        f.write(image)
                    images.append(image_path)
                    pil_img = PIL.Image.open(image_path)
                    pil_img = pil_img.convert("RGB")
                    pil_images.append(pil_img)
                if "audio_url" in message:
                    audio_url = (
                        message["audio_url"]["url"]
                        if "url" in message["audio_url"]
                        else message["audio_url"]
                    )
                    transcribed_audio = AudioToText().transcribe_audio(
                        file=audio_url, prompt=new_prompt
                    )
                    new_prompt += transcribed_audio
                if "file_url" in message:
                    file_url = (
                        message["file_url"]["url"]
                        if "url" in message["file_url"]
                        else message["file_url"]
                    )
                    if file_url.startswith("http"):
                        file_data = requests.get(file_url).content
                    else:
                        file_type = file_url.split(",")[0].split("/")[1].split(";")[0]
                        file_data = base64.b64decode(file_url.split(",")[1])
                    file_path = f"./WORKSPACE/{uuid.uuid4().hex}.{file_type}"
                    with open(file_path, "wb") as f:
                        f.write(file_data)
                    file_reader = FileReader(
                        agent_name=prompt.model,
                        agent_config=agent_config,
                        collection_number=0,
                        ApiClient=ApiClient,
                        user=user,
                    )
                    await file_reader.write_file_to_memory(file_path)
                if "url" in message:
                    url = (
                        message["url"]["url"]
                        if "url" in message["url"]
                        else message["url"]
                    )
                    if url.startswith("http"):
                        website_reader = WebsiteReader(
                            agent_name=prompt.model,
                            agent_config=agent_config,
                            collection_number=0,
                            ApiClient=ApiClient,
                            user=user,
                        )
                        await website_reader.write_website_to_memory(url)
    response = await agent.run(
        user_input=new_prompt,
        prompt="Custom Input",
        context_results=3,
        shots=prompt.n,
        images=images,
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
    "/v1/embedding",
    tags=["OpenAI Style Endpoints"],
    dependencies=[Depends(verify_api_key)],
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
