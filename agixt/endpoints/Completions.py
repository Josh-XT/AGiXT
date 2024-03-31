import string
import random
import time
import requests
import base64
import PIL
import uuid
import json
from fastapi import APIRouter, Depends, Header
from Interactions import Interactions, get_tokens, log_interaction
from ApiClient import Agent, verify_api_key, get_api_client
from Extensions import Extensions
from Chains import Chains
from readers.file import FileReader
from readers.website import WebsiteReader
from readers.youtube import YoutubeReader
from readers.github import GithubReader
from fastapi import UploadFile, File, Form
from typing import Optional, List
from Models import (
    Completions,
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
    ImageCreation,
)

app = APIRouter()


# Chat Completions endpoint
# https://platform.openai.com/docs/api-reference/chat/createChatCompletion
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
    # prompt.user is the conversation name
    ApiClient = get_api_client(authorization=authorization)
    agent = Interactions(agent_name=prompt.model, user=user, ApiClient=ApiClient)
    agent_config = agent.agent.AGENT_CONFIG
    conversation_name = prompt.user
    agent_settings = agent_config["settings"] if "settings" in agent_config else {}
    if "mode" in agent_config:
        mode = agent_config["mode"]
    else:
        mode = "prompt"
    if (
        mode == "command"
        and "command_name" in agent_settings
        and "command_args" in agent_settings
        and "command_variable" in agent_settings
    ):
        command_args = (
            json.loads(agent_settings["command_args"])
            if isinstance(agent_settings["command_args"], str)
            else agent_settings["command_args"]
        )
        command_args[agent_settings["command_variable"]] = prompt.messages[0]["content"]
        response = await Extensions(
            agent_name=prompt.model,
            agent_config=agent_config,
            conversation_name=conversation_name,
            ApiClient=ApiClient,
            api_key=authorization,
            user=user,
        ).execute_command(
            command_name=agent_settings["command_name"],
            command_args=agent_settings["command_args"],
        )
        log_interaction(
            agent_name=prompt.model,
            conversation_name=conversation_name,
            role=prompt.model,
            message=response,
            user=user,
        )
    elif (
        mode == "chain"
        and "chain_name" in agent_settings
        and "chain_args" in agent_settings
    ):
        chain_name = agent_settings["chain_name"]
        chain_args = (
            json.loads(agent_settings["chain_args"])
            if isinstance(agent_settings["chain_args"], str)
            else agent_settings["chain_args"]
        )
        response = Chains(user=user, ApiClient=ApiClient).run_chain(
            chain_name=chain_name,
            user_input=prompt.messages[0]["content"],
            agent_override=prompt.model,
            all_responses=False,
            chain_args=chain_args,
            from_step=1,
        )
    else:
        images = []
        pil_images = []
        new_prompt = ""
        websearch = False
        websearch_depth = 0
        browse_links = True
        if "prompt_name" in agent_settings:
            prompt_name = agent_settings["prompt_name"]
        else:
            prompt_name = "Chat"
        if "prompt_category" in agent_settings:
            prompt_category = agent_settings["prompt_category"]
        else:
            prompt_category = "Default"
        if "prompt_args" in agent_settings:
            prompt_args = (
                json.loads(agent_settings["prompt_args"])
                if isinstance(agent_settings["prompt_args"], str)
                else agent_settings["prompt_args"]
            )
        else:
            prompt_args = {}
        for message in prompt.messages:
            if "conversation_name" in message:
                conversation_name = message["conversation_name"]
            if "context_results" in message:
                context_results = int(message["context_results"])
            else:
                context_results = 5
            if "prompt_category" in message:
                prompt_category = message["prompt_category"]
            if "prompt_name" in message:
                prompt_name = message["prompt_name"]
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
                        transcribed_audio = agent.agent.transcribe_audio(
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
                            await youtube_reader.write_youtube_captions_to_memory(
                                video_url
                            )
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
                                        agent_settings["GITHUB_USER"]
                                        if "GITHUB_USER" in agent_settings
                                        else None
                                    ),
                                    github_token=(
                                        agent_settings["GITHUB_TOKEN"]
                                        if "GITHUB_TOKEN" in agent_settings
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
                            file_type = (
                                file_url.split(",")[0].split("/")[1].split(";")[0]
                            )
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
            **prompt_args,
        )
    prompt_tokens = get_tokens(str(prompt.messages))
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    res_model = {
        "id": conversation_name,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": prompt.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": str(response),
                },
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    return res_model


# Completions endpoint
# https://platform.openai.com/docs/api-reference/completions/createCompletion
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


# Embedding endpoint
# https://platform.openai.com/docs/api-reference/embeddings/createEmbedding
@app.post(
    "/v1/embeddings",
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
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    tokens = get_tokens(embedding.input)
    embedding = agent.embeddings(input=embedding.input)
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
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=model, user=user, ApiClient=ApiClient)
    response = await agent.transcribe_audio(
        audio_path=f"data:audio/{file.content_type};base64,{file.file.read()}",
    )
    if response.startswith("data:"):
        response = response.split(",")[1]
    return {"text": response}


# Audio Translations endpoint
# https://platform.openai.com/docs/api-reference/audio/createTranslation
@app.post(
    "/v1/audio/translations",
    tags=["Audio"],
    dependencies=[Depends(verify_api_key)],
)
async def translate_audio(
    file: UploadFile = File(...),
    model: str = Form("base"),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: Optional[str] = Form("json"),
    temperature: Optional[float] = Form(0.0),
    timestamp_granularities: Optional[List[str]] = Form(["segment"]),
    user: str = Depends(verify_api_key),
    authorization: str = Header(None),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=model, user=user, ApiClient=ApiClient)
    response = await agent.translate_audio(
        audio_path=f"data:audio/{file.content_type};base64,{file.file.read()}",
    )
    if response.startswith("data:"):
        response = response.split(",")[1]
    return {"text": response}


# Text to Speech endpoint
# https://platform.openai.com/docs/api-reference/audio/createSpeech
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
    agent = Agent(agent_name=tts.model, user=user, ApiClient=ApiClient)
    return await agent.text_to_speech(text=tts.input)


# Image Generation endpoint
# https://platform.openai.com/docs/api-reference/images
@app.post(
    "/v1/images/generations",
    tags=["Images"],
    dependencies=[Depends(verify_api_key)],
)
async def generate_image(
    image: ImageCreation,
    authorization: str = Header(None),
    user: str = Depends(verify_api_key),
):
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=image.model, user=user, ApiClient=ApiClient)
    images = []
    if int(image.n) > 1:
        for i in range(image.n):
            image = await agent.generate_image(prompt=image.prompt)
            images.append({"url": image})
        return {
            "created": int(time.time()),
            "data": images,
        }
    image = await agent.generate_image(prompt=image.prompt)
    return {
        "created": int(time.time()),
        "data": [{"url": image}],
    }
