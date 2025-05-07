import time
import uuid
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from Globals import get_tokens
from MagicalAuth import get_user_id
from ApiClient import Agent, verify_api_key, get_api_client, get_agents
from Conversations import get_conversation_name_by_id, Conversations
from providers.default import DefaultProvider
from Memories import embed
from fastapi import UploadFile, File, Form
from typing import Optional, List
from Models import (
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
    ImageCreation,
    AudioTranscriptionResponse,
    AudioTranslationResponse,
    TextToSpeechResponse,
    ImageGenerationResponse,
)
from XT import AGiXT

import logging
import json


app = APIRouter()


# Chat Completions endpoint
# https://platform.openai.com/docs/api-reference/chat/createChatCompletion
@app.post(
    "/v1/chat/completions",
    tags=["Completions"],
    dependencies=[Depends(verify_api_key)],
    summary="Create Chat Completion",
    description="Creates a completion for the chat message. Compatible with OpenAI's chat completions API format. Supports streaming.",
    # response_model=ChatCompletionResponse, # Remove this for streaming
)
async def chat_completion(
    prompt: ChatCompletions,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    conversation_name = prompt.user
    if conversation_name and conversation_name != "-":
        try:
            conversation_id = str(uuid.UUID(conversation_name))
            user_id = get_user_id(user)  # Assuming get_user_id exists
            conversation_name = get_conversation_name_by_id(
                conversation_id=conversation_id, user_id=user_id
            )
            prompt.user = conversation_name  # Update prompt object if name resolved
        except ValueError:
            # It's not a UUID, treat it as a name
            pass
        except Exception as e:
            logging.error(f"Error resolving conversation ID/Name: {e}")
            # Proceed with the name as given, or handle error appropriately
            pass

    if not prompt.model or prompt.model == "EVEN_REALITIES_GLASSES":
        agents = get_agents(user=user)
        try:
            prompt.model = agents[0]["name"]  # Corrected agent access
        except Exception as e:
            logging.warning(
                f"Error getting default agent name: {e}, defaulting to AGiXT"
            )
            prompt.model = "AGiXT"

    agixt = AGiXT(
        user=user,
        agent_name=prompt.model,
        api_key=authorization,
        conversation_name=conversation_name,
    )

    streaming = prompt.stream

    if streaming:
        # Return a StreamingResponse using the async generator from AGiXT
        return StreamingResponse(
            agixt.chat_completions(prompt=prompt), media_type="text/event-stream"
        )
    else:
        # Non-streaming: Collect all chunks and return the final JSON
        # This requires AGiXT.chat_completions to be an async generator even for non-streaming
        final_response_content = ""
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        finish_reason = "stop"
        completion_id = ""
        model_name = prompt.model
        created_time = int(time.time())

        async for chunk_str in agixt.chat_completions(prompt=prompt):
            if chunk_str.startswith("event: message\ndata: "):
                data_json = chunk_str.split("data: ", 1)[1].strip()
                if data_json == "[DONE]":
                    break
                try:
                    data = json.loads(data_json)
                    completion_id = data.get(
                        "id", completion_id
                    )  # Get ID from first chunk
                    model_name = data.get(
                        "model", model_name
                    )  # Get model from first chunk
                    created_time = data.get(
                        "created", created_time
                    )  # Get time from first chunk

                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content_part = delta.get("content", "")
                    if content_part:
                        final_response_content += content_part
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
                except json.JSONDecodeError:
                    logging.error(f"Failed to decode stream chunk: {data_json}")
                except Exception as e:
                    logging.error(f"Error processing stream chunk: {e}")
            elif chunk_str.strip() == "data: [DONE]":  # Handle simple DONE marker
                break

        # Calculate usage (approximated if not provided by LLM)
        # Note: A more accurate way would be to get token counts from the LLM provider if possible
        prompt_tokens = get_tokens(json.dumps(prompt.messages))  # Approx prompt tokens
        completion_tokens = get_tokens(final_response_content)
        total_tokens = prompt_tokens + completion_tokens
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

        # Construct the final OpenAI-compatible response object
        final_json_response = {
            "id": completion_id if completion_id else f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": created_time,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": final_response_content,
                    },
                    "finish_reason": finish_reason,
                    "logprobs": None,  # Not supported currently
                }
            ],
            "usage": usage,
        }
        return final_json_response


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
        audio_data = await DefaultProvider().text_to_speech(text=tts.input)
    return {"url": audio_data}


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
