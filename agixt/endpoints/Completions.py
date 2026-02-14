import time
import uuid
import re
import logging
import traceback
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from Globals import get_tokens
from MagicalAuth import get_user_id
from ApiClient import Agent, verify_api_key, get_api_client, get_agents
from Conversations import get_conversation_name_by_id
from DB import get_session, Conversation, ConversationParticipant, Agent as AgentModel
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


def parse_agent_mentions(messages, available_agents):
    """
    Parse @AgentName mentions from the last user message.
    Returns (mentioned_agent_name, cleaned_messages) or (None, messages) if no valid mention.

    Matching is case-insensitive and supports multi-word agent names.
    The longest matching agent name wins to avoid partial matches.
    """
    if not messages or not available_agents:
        return None, messages

    # Find the last user message
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if (
            isinstance(messages[i], dict)
            and messages[i].get("role", "").lower() == "user"
        ):
            last_user_idx = i
            break

    if last_user_idx is None:
        return None, messages

    msg = messages[last_user_idx]
    content = msg.get("content", "")
    if not isinstance(content, str):
        return None, messages

    # Build agent name lookup (case-insensitive), sorted longest first
    # Support both objects with .name and dicts with ["name"]
    def _get_agent_name(a):
        if isinstance(a, str):
            return a
        if isinstance(a, dict):
            return a.get("name", "")
        return getattr(a, "name", "")

    agent_names = sorted(
        [n for n in (_get_agent_name(a) for a in available_agents) if n],
        key=lambda n: len(n),
        reverse=True,
    )
    # Deduplicate
    agent_names = list(dict.fromkeys(agent_names))

    # Match @AgentName pattern - supports quoted names like @"My Agent" and unquoted
    for agent_name in agent_names:
        # Try quoted pattern first: @"Agent Name"
        quoted_pattern = re.compile(
            r'@["\u201c]' + re.escape(agent_name) + r'["\u201d]',
            re.IGNORECASE,
        )
        match = quoted_pattern.search(content)
        if match:
            cleaned_content = content[: match.start()] + content[match.end() :]
            cleaned_content = cleaned_content.strip()
            new_messages = list(messages)
            new_messages[last_user_idx] = {**msg, "content": cleaned_content}
            return agent_name, new_messages

        # Try unquoted pattern: @AgentName (word boundary after)
        unquoted_pattern = re.compile(
            r"@" + re.escape(agent_name) + r"(?:\b|(?=\s|$|[,.:;!?]))",
            re.IGNORECASE,
        )
        match = unquoted_pattern.search(content)
        if match:
            cleaned_content = content[: match.start()] + content[match.end() :]
            cleaned_content = cleaned_content.strip()
            new_messages = list(messages)
            new_messages[last_user_idx] = {**msg, "content": cleaned_content}
            return agent_name, new_messages

    return None, messages


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
        conversation_id = None
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
        # Pre-fetch agents list once for model defaulting and @mention routing
        all_agents = get_agents(user=user)
        if not prompt.model:
            try:
                prompt.model = (
                    all_agents[0]["name"] if isinstance(all_agents[0], dict) else all_agents[0].name
                )
            except Exception:
                # Log without exposing exception details
                logging.error("Error getting agent name: using default")
                prompt.model = "AGiXT"
        prompt.model = prompt.model.replace('"', "")

        # @mention agent routing: if the user's message contains @AgentName,
        # override the target agent and strip the mention from the message.
        if prompt.messages:
            try:
                mentioned_agent, cleaned_messages = parse_agent_mentions(
                    prompt.messages, all_agents
                )
                if mentioned_agent:
                    # Validate the mentioned agent belongs to this conversation's company
                    agent_allowed = True
                    if conversation_id:
                        try:
                            session = get_session()
                            conv = (
                                session.query(Conversation)
                                .filter(Conversation.id == conversation_id)
                                .first()
                            )
                            if conv and conv.company_id:
                                # Get the mentioned agent's company_id
                                mentioned_agent_data = next(
                                    (
                                        a
                                        for a in all_agents
                                        if (
                                            (
                                                a["name"]
                                                if isinstance(a, dict)
                                                else a.name
                                            )
                                            == mentioned_agent
                                        )
                                    ),
                                    None,
                                )
                                if mentioned_agent_data:
                                    agent_company = (
                                        mentioned_agent_data["company_id"]
                                        if isinstance(mentioned_agent_data, dict)
                                        else getattr(
                                            mentioned_agent_data, "company_id", None
                                        )
                                    )
                                    if agent_company and str(agent_company) != str(
                                        conv.company_id
                                    ):
                                        agent_allowed = False
                                        logging.info(
                                            f"@mention blocked: agent '{mentioned_agent}' "
                                            f"(company {agent_company}) not in conversation's "
                                            f"company ({conv.company_id})"
                                        )
                            session.close()
                        except Exception as e:
                            logging.warning(f"Error validating agent company: {e}")

                    if agent_allowed:
                        prompt.model = mentioned_agent
                        prompt.messages = cleaned_messages
                        logging.info(
                            f"@mention routing: directing to agent '{mentioned_agent}'"
                        )
                    else:
                        # Strip the mention but don't route to the agent
                        prompt.messages = cleaned_messages
            except Exception as e:
                logging.warning(f"Error parsing @mentions: {e}")

        # Defense-in-depth: refuse agent responses in user-to-user DMs
        # (no agent participants).  The front end already routes these to
        # the message-only endpoint, but this prevents accidental triggers
        # from stale clients, race conditions, or API callers.
        if conversation_id:
            try:
                _dm_session = get_session()
                _dm_conv = (
                    _dm_session.query(Conversation)
                    .filter(Conversation.id == conversation_id)
                    .first()
                )
                if _dm_conv and _dm_conv.conversation_type == "dm":
                    _has_agent = (
                        _dm_session.query(ConversationParticipant)
                        .filter(
                            ConversationParticipant.conversation_id == conversation_id,
                            ConversationParticipant.participant_type == "agent",
                        )
                        .first()
                    )
                    if not _has_agent:
                        _dm_session.close()
                        raise HTTPException(
                            status_code=400,
                            detail="Cannot trigger agent response in a user-to-user DM with no agent participants.",
                        )
                elif (
                    _dm_conv
                    and _dm_conv.conversation_type == "thread"
                    and _dm_conv.parent_id
                ):
                    _parent_conv = (
                        _dm_session.query(Conversation)
                        .filter(Conversation.id == _dm_conv.parent_id)
                        .first()
                    )
                    if _parent_conv and _parent_conv.conversation_type == "dm":
                        _has_agent = (
                            _dm_session.query(ConversationParticipant)
                            .filter(
                                ConversationParticipant.conversation_id
                                == _parent_conv.id,
                                ConversationParticipant.participant_type == "agent",
                            )
                            .first()
                        )
                        if not _has_agent:
                            _dm_session.close()
                            raise HTTPException(
                                status_code=400,
                                detail="Cannot trigger agent response in a thread within a user-to-user DM.",
                            )
                _dm_session.close()
            except HTTPException:
                raise
            except Exception as e:
                logging.warning(f"Error checking DM conversation type: {e}")

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
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream; charset=utf-8",
                    "X-Accel-Buffering": "no",
                    "Transfer-Encoding": "chunked",
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
        conversation_id = None
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
        # Pre-fetch agents list once for model defaulting and @mention routing
        all_agents = get_agents(user=user)
        if not prompt.model:
            try:
                prompt.model = (
                    all_agents[0]["name"] if isinstance(all_agents[0], dict) else all_agents[0].name
                )
            except Exception:
                # Log without exposing exception details
                logging.error("Error getting agent name: using default")
                prompt.model = "AGiXT"
        prompt.model = prompt.model.replace('"', "")

        # @mention agent routing for MCP endpoint
        if prompt.messages:
            try:
                mentioned_agent, cleaned_messages = parse_agent_mentions(
                    prompt.messages, all_agents
                )
                if mentioned_agent:
                    # Validate the mentioned agent belongs to this conversation's company
                    agent_allowed = True
                    if conversation_id:
                        try:
                            session = get_session()
                            conv = (
                                session.query(Conversation)
                                .filter(Conversation.id == conversation_id)
                                .first()
                            )
                            if conv and conv.company_id:
                                mentioned_agent_data = next(
                                    (
                                        a
                                        for a in all_agents
                                        if (
                                            (
                                                a["name"]
                                                if isinstance(a, dict)
                                                else a.name
                                            )
                                            == mentioned_agent
                                        )
                                    ),
                                    None,
                                )
                                if mentioned_agent_data:
                                    agent_company = (
                                        mentioned_agent_data["company_id"]
                                        if isinstance(mentioned_agent_data, dict)
                                        else getattr(
                                            mentioned_agent_data, "company_id", None
                                        )
                                    )
                                    if agent_company and str(agent_company) != str(
                                        conv.company_id
                                    ):
                                        agent_allowed = False
                                        logging.info(
                                            f"@mention blocked (MCP): agent '{mentioned_agent}' "
                                            f"(company {agent_company}) not in conversation's "
                                            f"company ({conv.company_id})"
                                        )
                            session.close()
                        except Exception as e:
                            logging.warning(f"Error validating agent company: {e}")

                    if agent_allowed:
                        prompt.model = mentioned_agent
                        prompt.messages = cleaned_messages
                        logging.info(
                            f"@mention routing (MCP): directing to agent '{mentioned_agent}'"
                        )
                    else:
                        prompt.messages = cleaned_messages
            except Exception as e:
                logging.warning(f"Error parsing @mentions: {e}")

        # Defense-in-depth: refuse agent responses in user-to-user DMs
        if conversation_id:
            try:
                _dm_session = get_session()
                _dm_conv = (
                    _dm_session.query(Conversation)
                    .filter(Conversation.id == conversation_id)
                    .first()
                )
                if _dm_conv and _dm_conv.conversation_type == "dm":
                    _has_agent = (
                        _dm_session.query(ConversationParticipant)
                        .filter(
                            ConversationParticipant.conversation_id == conversation_id,
                            ConversationParticipant.participant_type == "agent",
                        )
                        .first()
                    )
                    if not _has_agent:
                        _dm_session.close()
                        raise HTTPException(
                            status_code=400,
                            detail="Cannot trigger agent response in a user-to-user DM with no agent participants.",
                        )
                elif (
                    _dm_conv
                    and _dm_conv.conversation_type == "thread"
                    and _dm_conv.parent_id
                ):
                    _parent_conv = (
                        _dm_session.query(Conversation)
                        .filter(Conversation.id == _dm_conv.parent_id)
                        .first()
                    )
                    if _parent_conv and _parent_conv.conversation_type == "dm":
                        _has_agent = (
                            _dm_session.query(ConversationParticipant)
                            .filter(
                                ConversationParticipant.conversation_id
                                == _parent_conv.id,
                                ConversationParticipant.participant_type == "agent",
                            )
                            .first()
                        )
                        if not _has_agent:
                            _dm_session.close()
                            raise HTTPException(
                                status_code=400,
                                detail="Cannot trigger agent response in a thread within a user-to-user DM.",
                            )
                _dm_session.close()
            except HTTPException:
                raise
            except Exception as e:
                logging.warning(f"Error checking DM conversation type (MCP): {e}")

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
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream; charset=utf-8",
                    "X-Accel-Buffering": "no",
                    "Transfer-Encoding": "chunked",
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
