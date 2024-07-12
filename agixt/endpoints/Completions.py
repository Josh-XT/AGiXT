import time
import base64
import uuid
from fastapi import APIRouter, Depends, Header
from Globals import get_tokens
from ApiClient import Agent, verify_api_key, get_api_client
from providers.default import DefaultProvider
from fastapi import UploadFile, File, Form
from typing import Optional, List
from Models import (
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
    ImageCreation,
)
from XT import AGiXT

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
    agixt = AGiXT(
        user=user,
        agent_name=prompt.model,
        api_key=authorization,
        conversation_name=prompt.user,
    )
    return await agixt.chat_completions(prompt=prompt)


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
    if agent.TTS_PROVIDER != None:
        audio_data = await agent.text_to_speech(text=tts.input)
    else:
        audio_data = await DefaultProvider().text_to_speech(text=tts.input)
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
