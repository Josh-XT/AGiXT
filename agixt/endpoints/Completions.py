import time
import uuid
import logging
import traceback
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from Globals import get_tokens
from MagicalAuth import get_user_id
from ApiClient import Agent, verify_api_key, get_api_client, get_agents
from Conversations import get_conversation_name_by_id
from Memories import embed
from fastapi import UploadFile, File, Form
from typing import Optional, List
from Models import (
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
    ImageCreation,
    ChatCompletionResponse,
    ChatCompletionChunk,
    EmbeddingResponse,
    AudioTranscriptionResponse,
    AudioTranslationResponse,
    TextToSpeechResponse,
    ImageGenerationResponse,
)
from XT import AGiXT
import json
import asyncio

app = APIRouter()


async def safe_stream_wrapper(stream_generator):
    """Wrap a streaming generator to prevent exception information exposure."""
    try:
        async for chunk in stream_generator:
            yield chunk
    except asyncio.CancelledError:
        # Re-raise cancellation to allow proper cleanup
        raise
    except Exception as e:
        # Log the error internally but don't expose details to client
        logging.error(f"Error during streaming response: {e}")
        logging.error(traceback.format_exc())
        # Send error to Discord if configured
        try:
            from middleware import send_discord_error

            await send_discord_error(e)
        except Exception:
            pass
        # Yield an error chunk in OpenAI-compatible format so clients can parse it
        import time

        error_chunk = {
            "id": "error",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "error",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "[Error: An error occurred during streaming]"},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


# Chat Completions endpoint
# https://platform.openai.com/docs/api-reference/chat/createChatCompletion
@app.post(
    "/v1/chat/completions",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
    summary="Create Chat Completion",
    description="Creates a completion for the chat message. Compatible with OpenAI's chat completions API format. Supports streaming responses when stream=true.",
)
async def chat_completion(
    prompt: ChatCompletions,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        # prompt.model is the agent name
        # prompt.user is the conversation name
        # Check if conversation name is a uuid, if so, it is the conversation_id and nedds convertd
        conversation_name = prompt.user
        if conversation_name != "-":
            try:
                conversation_id = str(uuid.UUID(conversation_name))
            except Exception:
                conversation_id = None
            if conversation_id:
                user_id = get_user_id(user)
                conversation_name = get_conversation_name_by_id(
                    conversation_id=conversation_id, user_id=user_id
                )
        if not prompt.model:
            agents = get_agents(user=user)
            try:
                prompt.model = agents[0].name
            except Exception:
                # Log without exposing exception details
                logging.error("Error getting agent name: using default")
                prompt.model = "AGiXT"
        prompt.model = prompt.model.replace('"', "")
        agixt = AGiXT(
            user=user,
            agent_name=prompt.model,
            api_key=authorization,
            conversation_name=conversation_name,
        )

        # Check if streaming is requested
        if prompt.stream:
            return StreamingResponse(
                safe_stream_wrapper(agixt.chat_completions_stream(prompt=prompt)),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
        else:
            return await agixt.chat_completions(prompt=prompt)
    except HTTPException:
        # Re-raise HTTP exceptions (like 402 Payment Required) without modification
        raise
    except ValueError as e:
        # Return 400 for validation errors (bad request)
        logging.warning(f"Validation error in chat_completion endpoint: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log error internally but don't expose details to client
        logging.error(f"Error in chat_completion endpoint: {e}")
        logging.error(traceback.format_exc())
        # Send error to Discord if configured (fire and forget)
        try:
            from middleware import send_discord_error

            await send_discord_error(e)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal server error")


# Chat Completions endpoint
# https://platform.openai.com/docs/api-reference/chat/createChatCompletion
@app.post(
    "/v1/mcp/chat/completions",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
    summary="Create Chat Completion",
    description="Creates a completion for the chat message. Compatible with OpenAI's chat completions API format. Supports streaming responses when stream=true.",
)
async def mcp_chat_completion(
    prompt: ChatCompletions,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    try:
        # Validate that messages is provided
        if not prompt.messages:
            raise ValueError(
                "The 'messages' field is required and must contain at least one message."
            )
        # prompt.model is the agent name
        # prompt.user is the conversation name
        # Check if conversation name is a uuid, if so, it is the conversation_id and nedds convertd
        prompt.messages[0]["running_command"] = "Browser Automation"
        conversation_name = prompt.user
        if conversation_name != "-":
            try:
                conversation_id = str(uuid.UUID(conversation_name))
            except Exception:
                conversation_id = None
            if conversation_id:
                user_id = get_user_id(user)
                conversation_name = get_conversation_name_by_id(
                    conversation_id=conversation_id, user_id=user_id
                )
        if not prompt.model:
            agents = get_agents(user=user)
            try:
                prompt.model = agents[0].name
            except Exception:
                # Log without exposing exception details
                logging.error("Error getting agent name: using default")
                prompt.model = "AGiXT"
        prompt.model = prompt.model.replace('"', "")
        agixt = AGiXT(
            user=user,
            agent_name=prompt.model,
            api_key=authorization,
            conversation_name=conversation_name,
        )

        # Check if streaming is requested
        if prompt.stream:
            return StreamingResponse(
                safe_stream_wrapper(agixt.chat_completions_stream(prompt=prompt)),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
        else:
            return await agixt.chat_completions(prompt=prompt)
    except ValueError as e:
        # Return 400 for validation errors (bad request)
        logging.warning(f"Validation error in mcp_chat_completion endpoint: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log error internally but don't expose details to client
        logging.error(f"Error in mcp_chat_completion endpoint: {e}")
        logging.error(traceback.format_exc())
        # Send error to Discord if configured
        try:
            from middleware import send_discord_error

            await send_discord_error(e)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Internal server error")


# Embedding endpoint
# https://platform.openai.com/docs/api-reference/embeddings/createEmbedding
@app.post(
    "/v1/embeddings",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
    summary="Create Text Embeddings",
    description="Creates embeddings for the input text. Compatible with OpenAI's embeddings API format.",
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
    embedding = embed(input=embedding.input)
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
    summary="Create Audio Transcription",
    description="Transcribes audio into text. Compatible with OpenAI's audio transcription API format.",
    response_model=AudioTranscriptionResponse,
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
    summary="Create Audio Translation",
    description="Translates audio into English text. Compatible with OpenAI's audio translation API format.",
    response_model=AudioTranslationResponse,
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
    summary="Create Text-to-Speech Audio",
    description="Converts text into speech audio. Compatible with OpenAI's text-to-speech API format.",
    response_model=TextToSpeechResponse,
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
        raise HTTPException(status_code=400, detail="No TTS provider available")
    return {"url": audio_data}


# Streaming Text to Speech endpoint
@app.post(
    "/v1/audio/speech/stream",
    tags=["Audio"],
    dependencies=[Depends(verify_api_key)],
    summary="Stream Text-to-Speech Audio",
    description="Stream TTS audio as it's generated. Returns raw PCM audio stream with header information.",
)
async def text_to_speech_stream(
    tts: TextToSpeech,
    authorization: str = Header(None),
    user: str = Depends(verify_api_key),
):
    """
    Stream TTS audio as it's generated, chunk by chunk.

    Response format (binary stream):
    - Header (8 bytes): sample_rate (uint32), bits (uint16), channels (uint16)
    - Data chunks: chunk_size (uint32) + raw PCM data
    - End marker: chunk_size = 0

    Audio format: 24kHz, 16-bit, mono PCM
    """
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=tts.model, user=user, ApiClient=ApiClient)

    if agent.TTS_PROVIDER is None:
        raise HTTPException(status_code=400, detail="No TTS provider available")

    async def audio_stream_generator():
        async for chunk in agent.text_to_speech_stream(text=tts.input):
            yield chunk

    return StreamingResponse(
        audio_stream_generator(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Format": "pcm",
            "X-Sample-Rate": "24000",
            "X-Bits-Per-Sample": "16",
            "X-Channels": "1",
        },
    )


# Image Generation endpoint
# https://platform.openai.com/docs/api-reference/images
@app.post(
    "/v1/images/generations",
    tags=["Images"],
    dependencies=[Depends(verify_api_key)],
    summary="Create Image",
    description="Creates an image given a prompt. Compatible with OpenAI's image generation API format.",
    response_model=ImageGenerationResponse,
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
