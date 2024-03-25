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
from readers.youtube import YoutubeReader
from readers.github import GithubReader
from AudioToText import AudioToText
from fastapi import UploadFile, File, Form
from typing import Optional, List
from Models import (
    Completions,
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
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
    conversation_name = "Chat"
    websearch = False
    websearch_depth = 0
    browse_links = True
    for message in prompt.messages:
        if "conversation_name" in message:
            conversation_name = message["conversation_name"]
        if "context_results" in message:
            context_results = int(message["context_results"])
        else:
            context_results = 5
        if "prompt_category" in message:
            prompt_category = message["prompt_category"]
        else:
            prompt_category = "Default"
        if "prompt_name" in message:
            prompt_name = message["prompt_name"]
        else:
            prompt_name = "Chat"
        if "websearch" in message:
            websearch = str(message["websearch"]).lower() == "true"
        if "websearch_depth" in message:
            websearch_depth = int(message["websearch_depth"])
        if "browse_links" in message:
            browse_links = str(message["browse_links"]).lower() == "true"
        if isinstance(message["content"], str):
            role = message["role"] if "role" in message else "User"
            if role.lower() == "system":
                if "/" in message["content"]:
                    new_prompt += f"{message['content']}\n\n"
            if role.lower() == "user":
                new_prompt += f"{message['content']}\n\n"
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
                if "video_url" in message:
                    video_url = str(
                        message["video_url"]["url"]
                        if "url" in message["video_url"]
                        else message["video_url"]
                    )
                    if "collection_number" in message:
                        collection_number = int(message["collection_number"])
                    else:
                        collection_number = 0
                    if video_url.startswith("https://www.youtube.com/watch?v="):
                        youtube_reader = YoutubeReader(
                            agent_name=prompt.model,
                            agent_config=agent_config,
                            collection_number=collection_number,
                            ApiClient=ApiClient,
                            user=user,
                        )
                        await youtube_reader.write_youtube_captions_to_memory(video_url)
                if (
                    "file_url" in message
                    or "application_url" in message
                    or "text_url" in message
                    or "url" in message
                ):
                    file_url = str(
                        message["file_url"]["url"]
                        if "url" in message["file_url"]
                        else message["file_url"]
                    )
                    if "collection_number" in message:
                        collection_number = int(message["collection_number"])
                    else:
                        collection_number = 0
                    if file_url.startswith("http"):
                        if file_url.startswith("https://www.youtube.com/watch?v="):
                            youtube_reader = YoutubeReader(
                                agent_name=prompt.model,
                                agent_config=agent_config,
                                collection_number=collection_number,
                                ApiClient=ApiClient,
                                user=user,
                            )
                            await youtube_reader.write_youtube_captions_to_memory(
                                file_url
                            )
                        elif file_url.startswith("https://github.com"):
                            github_reader = GithubReader(
                                agent_name=prompt.model,
                                agent_config=agent_config,
                                collection_number=collection_number,
                                ApiClient=ApiClient,
                                user=user,
                            )
                            await github_reader.write_github_repository_to_memory(
                                github_repo=file_url,
                                github_user=(
                                    agent_config["GITHUB_USER"]
                                    if "GITHUB_USER" in agent_config
                                    else None
                                ),
                                github_token=(
                                    agent_config["GITHUB_TOKEN"]
                                    if "GITHUB_TOKEN" in agent_config
                                    else None
                                ),
                                github_branch=(
                                    "main"
                                    if "branch" not in message
                                    else message["branch"]
                                ),
                            )
                        else:
                            website_reader = WebsiteReader(
                                agent_name=prompt.model,
                                agent_config=agent_config,
                                collection_number=collection_number,
                                ApiClient=ApiClient,
                                user=user,
                            )
                            await website_reader.write_website_to_memory(url)
                    else:
                        file_type = file_url.split(",")[0].split("/")[1].split(";")[0]
                        file_data = base64.b64decode(file_url.split(",")[1])
                        file_path = f"./WORKSPACE/{uuid.uuid4().hex}.{file_type}"
                        with open(file_path, "wb") as f:
                            f.write(file_data)
                        file_reader = FileReader(
                            agent_name=prompt.model,
                            agent_config=agent_config,
                            collection_number=collection_number,
                            ApiClient=ApiClient,
                            user=user,
                        )
                        await file_reader.write_file_to_memory(file_path)
    response = await agent.run(
        user_input=new_prompt,
        prompt=prompt_name,
        prompt_category=prompt_category,
        context_results=context_results,
        shots=prompt.n,
        websearch=websearch,
        websearch_depth=websearch_depth,
        conversation_name=conversation_name,
        browse_links=browse_links,
        images=images,
    )
    prompt_tokens = get_tokens(prompt.prompt)
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    res_model = {
        "id": conversation_name,
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


# Audio Transcription endpoint
# https://platform.openai.com/docs/api-reference/audio/createTranscription
@app.post(
    "/v1/audio/transcriptions",
    tags=["Audio"],
    dependencies=[Depends(verify_api_key)],
)
async def speech_to_text(
    file: UploadFile = File(...),
    model: str = Form("base"),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: Optional[str] = Form("json"),
    temperature: Optional[float] = Form(0.0),
    timestamp_granularities: Optional[List[str]] = Form(["segment"]),
    user: str = Depends(verify_api_key),
):
    response = await AudioToText(model=model).transcribe_audio(
        file=file.file,
        language=language,
        prompt=prompt,
        temperature=temperature,
    )
    return {"text": response}


@app.post(
    "/v1/audio/speech",
    tags=["Audio"],
    dependencies=[Depends(verify_api_key)],
)
async def text_to_speech(
    tts: TextToSpeech,
    authorization: str = Header(None),
    user: str = Depends(verify_api_key),
):
    ApiClient = get_api_client(authorization=authorization)
    audio_response = ApiClient.execute_command(
        agent_name=tts.model,
        command_name="Text to Speech",
        command_args={"text": tts.input, "voice": tts.voice, "language": tts.language},
    )
    return f"{audio_response}"
