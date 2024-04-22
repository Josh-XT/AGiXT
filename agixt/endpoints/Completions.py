import time
import base64
import uuid
import json
import requests
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
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
    ImageCreation,
)
from pydub import AudioSegment

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
    agent_name = prompt.model
    conversation_name = prompt.user
    agent = Interactions(agent_name=agent_name, user=user, ApiClient=ApiClient)
    agent_config = agent.agent.AGENT_CONFIG
    agent_settings = agent_config["settings"] if "settings" in agent_config else {}
    images = []
    new_prompt = ""
    browse_links = True
    if "mode" in agent_settings:
        mode = agent_settings["mode"]
    else:
        mode = "prompt"
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
    if "command_name" in agent_settings:
        command_name = agent_settings["command_name"]
    else:
        command_name = ""
    if "command_args" in agent_settings:
        command_args = (
            json.loads(agent_settings["command_args"])
            if isinstance(agent_settings["command_args"], str)
            else agent_settings["command_args"]
        )
    else:
        command_args = {}
    if "command_variable" in agent_settings:
        command_variable = agent_settings["command_variable"]
    else:
        command_variable = "text"
    if "chain_name" in agent_settings:
        chain_name = agent_settings["chain_name"]
    else:
        chain_name = ""
    if "chain_args" in agent_settings:
        chain_args = (
            json.loads(agent_settings["chain_args"])
            if isinstance(agent_settings["chain_args"], str)
            else agent_settings["chain_args"]
        )
    else:
        chain_args = {}
    for message in prompt.messages:
        if "mode" in message:
            if message["mode"] in ["prompt", "command", "chain"]:
                mode = message["mode"]
        if "context_results" in message:
            context_results = int(message["context_results"])
        else:
            context_results = 5
        if "prompt_category" in message:
            prompt_category = message["prompt_category"]
        if "prompt_name" in message:
            prompt_name = message["prompt_name"]
        if "prompt_args" in message:
            prompt_args = (
                json.loads(message["prompt_args"])
                if isinstance(message["prompt_args"], str)
                else message["prompt_args"]
            )
        if "command_name" in message:
            command_name = message["command_name"]
        if "command_args" in message:
            command_args = (
                json.loads(message["command_args"])
                if isinstance(message["command_args"], str)
                else message["command_args"]
            )
        if "command_variable" in message:
            command_variable = message["command_variable"]
        if "chain_name" in message:
            chain_name = message["chain_name"]
        if "chain_args" in message:
            chain_args = (
                json.loads(message["chain_args"])
                if isinstance(message["chain_args"], str)
                else message["chain_args"]
            )
        if "browse_links" in message:
            browse_links = str(message["browse_links"]).lower() == "true"
        if "content" not in message:
            continue
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
                    if url.startswith("http"):
                        image_path = url
                    else:
                        file_type = url.split(",")[0].split("/")[1].split(";")[0]
                        if file_type == "jpeg":
                            file_type = "jpg"
                        image_path = f"./WORKSPACE/{uuid.uuid4().hex}.{file_type}"
                        image_content = url.split(",")[1]
                        image = base64.b64decode(image_content)
                        with open(image_path, "wb") as f:
                            f.write(image)
                    images.append(image_path)
                if "audio_url" in msg:
                    audio_url = (
                        msg["audio_url"]["url"]
                        if "url" in msg["audio_url"]
                        else msg["audio_url"]
                    )
                    # If it is not a url, we need to find the file type and convert with pydub
                    if not audio_url.startswith("http"):
                        file_type = audio_url.split(",")[0].split("/")[1].split(";")[0]
                        audio_data = base64.b64decode(audio_url.split(",")[1])
                        audio_path = f"./WORKSPACE/{uuid.uuid4().hex}.{file_type}"
                        with open(audio_path, "wb") as f:
                            f.write(audio_data)
                        audio_url = audio_path
                    else:
                        # Download the audio file from the url, get the file type and convert to wav
                        audio_type = audio_url.split(".")[-1]
                        audio_url = f"./WORKSPACE/{uuid.uuid4().hex}.{audio_type}"
                        audio_data = requests.get(audio_url).content
                        with open(audio_url, "wb") as f:
                            f.write(audio_data)
                    wav_file = f"./WORKSPACE/{uuid.uuid4().hex}.wav"
                    AudioSegment.from_file(audio_url).set_frame_rate(16000).export(
                        wav_file, format="wav"
                    )
                    transcribed_audio = await agent.agent.transcribe_audio(
                        audio_path=wav_file
                    )
                    new_prompt += transcribed_audio
                if "video_url" in msg:
                    video_url = str(
                        msg["video_url"]["url"]
                        if "url" in msg["video_url"]
                        else msg["video_url"]
                    )
                    if "collection_number" in msg:
                        collection_number = int(msg["collection_number"])
                    else:
                        collection_number = 0
                    if video_url.startswith("https://www.youtube.com/watch?v="):
                        youtube_reader = YoutubeReader(
                            agent_name=agent_name,
                            agent_config=agent_config,
                            collection_number=collection_number,
                            ApiClient=ApiClient,
                            user=user,
                        )
                        await youtube_reader.write_youtube_captions_to_memory(video_url)
                if (
                    "file_url" in msg
                    or "application_url" in msg
                    or "text_url" in msg
                    or "url" in msg
                ):
                    file_url = str(
                        msg["file_url"]["url"]
                        if "url" in msg["file_url"]
                        else msg["file_url"]
                    )
                    if "collection_number" in message or "collection_number" in msg:
                        collection_number = int(
                            message["collection_number"]
                            if "collection_number" in message
                            else msg["collection_number"]
                        )
                    else:
                        collection_number = 0
                    if file_url.startswith("http"):
                        if file_url.startswith("https://www.youtube.com/watch?v="):
                            youtube_reader = YoutubeReader(
                                agent_name=agent_name,
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
                                agent_name=agent_name,
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
                                agent_name=agent_name,
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
                            agent_name=agent_name,
                            agent_config=agent_config,
                            collection_number=collection_number,
                            ApiClient=ApiClient,
                            user=user,
                        )
                        await file_reader.write_file_to_memory(file_path)
        if mode == "command" and command_name and command_variable:
            command_args = (
                json.loads(agent_settings["command_args"])
                if isinstance(agent_settings["command_args"], str)
                else agent_settings["command_args"]
            )
            command_args[agent_settings["command_variable"]] = new_prompt
            log_interaction(
                agent_name=agent_name,
                conversation_name=conversation_name,
                role="USER",
                message=new_prompt,
                user=user,
            )
            response = await Extensions(
                agent_name=agent_name,
                agent_config=agent_config,
                conversation_name=conversation_name,
                ApiClient=ApiClient,
                api_key=authorization,
                user=user,
            ).execute_command(
                command_name=agent_settings["command_name"],
                command_args=command_args,
            )
            log_interaction(
                agent_name=agent_name,
                conversation_name=conversation_name,
                role=agent_name,
                message=response,
                user=user,
            )
        elif mode == "chain" and chain_name:
            chain_name = agent_settings["chain_name"]
            chain_args = (
                json.loads(agent_settings["chain_args"])
                if isinstance(agent_settings["chain_args"], str)
                else agent_settings["chain_args"]
            )
            log_interaction(
                agent_name=agent_name,
                conversation_name=conversation_name,
                role="USER",
                message=new_prompt,
                user=user,
            )
            response = await Chains(user=user, ApiClient=ApiClient).run_chain(
                chain_name=chain_name,
                user_input=new_prompt,
                agent_override=agent_name,
                all_responses=False,
                chain_args=chain_args,
                from_step=1,
            )
            log_interaction(
                agent_name=agent_name,
                conversation_name=conversation_name,
                role=agent_name,
                message=response,
                user=user,
            )
        elif mode == "prompt":
            response = await agent.run(
                user_input=new_prompt,
                context_results=context_results,
                shots=prompt.n,
                conversation_name=conversation_name,
                browse_links=browse_links,
                images=images,
                **prompt_args,
            )
    prompt_tokens = get_tokens(new_prompt)
    completion_tokens = get_tokens(response)
    total_tokens = int(prompt_tokens) + int(completion_tokens)
    res_model = {
        "id": conversation_name,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": agent_name,
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


import logging


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
    audio_format = file.content_type.split("/")[1]
    if audio_format == "x-wav":
        audio_format = "wav"
    audio_path = f"./WORKSPACE/{uuid.uuid4().hex}.{audio_format}"
    with open(audio_path, "wb") as f:
        f.write(file.file.read())
    response = await agent.transcribe_audio(audio_path=audio_path)
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
    # Save as audio file based on its type
    audio_format = file.content_type.split("/")[1]
    audio_path = f"./WORKSPACE/{uuid.uuid4().hex}.{audio_format}"
    with open(audio_path, "wb") as f:
        f.write(file.file.read())
    response = await agent.translate_audio(audio_path=audio_path)
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
    audio_data = await agent.text_to_speech(text=tts.input)
    return base64.b64encode(audio_data).decode("utf-8")


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
