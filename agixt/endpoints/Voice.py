import json
import logging
import asyncio
from fastapi import (
    APIRouter,
    Depends,
    Header,
    WebSocket,
    WebSocketDisconnect,
)
from ApiClient import verify_api_key, get_api_client, Agent
from Conversations import (
    get_conversation_id_by_name,
)
from MagicalAuth import MagicalAuth
from VoiceConversation import VoiceConversationSession, VoiceState

app = APIRouter()


@app.websocket("/v1/audio/conversation/{conversation_id}")
async def voice_conversation(
    websocket: WebSocket,
    conversation_id: str,
    authorization: str = None,
):
    """
    WebSocket endpoint for real-time voice conversations.

    Dual-model architecture:
    - Speaker (0.8B): Fast acknowledgments and progress narration
    - Thinker (35B): Full AGiXT pipeline processing

    Client -> Server messages:
    - Binary frames: Raw audio data (WAV/PCM)
    - JSON text frames:
        {"type": "audio.input.end"} - Audio input complete, begin processing
        {"type": "text.input", "text": "..."} - Text input (typed)
        {"type": "image.input", "data": "<base64 jpeg>"} - Camera frame for vision context
        {"type": "interrupt"} - Barge-in / stop speaking
        {"type": "config", ...} - Session configuration
            Optional fields: voice, language, agent
        {"type": "tools.register", "tools": [...]} - Register client-side tools
            Each tool: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
        {"type": "tool.result", "request_id": "...", "result": "..."} - Tool execution result

    Server -> Client messages:
    - Binary frames: Raw audio data (PCM chunks)
    - JSON text frames:
        {"type": "status", "data": {"state": "..."}} - State changes
        {"type": "audio.header", "data": {"format": "pcm", ...}} - Audio format info
        {"type": "audio.end", "data": {}} - Audio playback complete
        {"type": "audio.interrupt", "data": {}} - Stop playing audio
        {"type": "transcript.user", "data": {"text": "..."}} - User speech transcript
        {"type": "transcript.agent", "data": {"text": "...", "role": "speaker|thinker"}}
        {"type": "tool.request", "data": {"request_id": "...", "tool_name": "...", "tool_args": {...}}}
        {"type": "session.end", "data": {"reason": "user_goodbye"}} - Session ending
        {"type": "heartbeat", "data": {"ts": ...}} - Keepalive
        {"type": "error", "data": {"message": "..."}} - Error
    """
    await websocket.accept()

    try:
        # Auth
        if not authorization:
            authorization = websocket.query_params.get("authorization")
        if not authorization:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "data": {"message": "Authorization required"}}
                )
            )
            await websocket.close()
            return

        try:
            from ApiClient import verify_api_key as _verify

            class _MockHeader:
                def __init__(self, value):
                    self.value = value

                def __str__(self):
                    return self.value

            user = _verify(authorization=_MockHeader(authorization))
            auth = MagicalAuth(token=authorization)
        except Exception as e:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": f"Authentication failed: {str(e)}"},
                    }
                )
            )
            await websocket.close()
            return

        # Resolve conversation
        if conversation_id == "-":
            conversation_id = get_conversation_id_by_name(
                conversation_name="-", user_id=auth.user_id
            )

        ApiClient = get_api_client(authorization=authorization)
        agent_name = "XT"  # Default agent

        # Create session
        agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
        session = VoiceConversationSession(
            agent_name=agent_name,
            user=user,
            authorization=authorization,
            conversation_id=conversation_id,
            agent=agent,
            ApiClient=ApiClient,
        )
        session.websocket = websocket

        # Start keepalive
        await session.start_keepalive()

        # Send ready
        await websocket.send_text(
            json.dumps(
                {
                    "type": "status",
                    "data": {
                        "state": "idle",
                        "message": "Voice conversation ready",
                        "conversation_id": conversation_id,
                    },
                }
            )
        )

        # Audio accumulation buffer for chunked input
        audio_buffer = bytearray()
        processing_task = None

        # Main message loop
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break

            if message.get("type") == "websocket.disconnect":
                break

            # Binary frame = audio data
            if "bytes" in message and message["bytes"]:
                audio_buffer.extend(message["bytes"])
                continue

            # Text frame = JSON control message
            if "text" in message and message["text"]:
                try:
                    msg = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "data": {"message": "Invalid JSON"},
                            }
                        )
                    )
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "audio.input.end":
                    # Process accumulated audio
                    if audio_buffer:
                        audio_data = bytes(audio_buffer)
                        audio_buffer.clear()

                        # If thinker is working, route to mid-conversation
                        # handler (injects steering instead of canceling)
                        if (
                            processing_task
                            and not processing_task.done()
                            and session.state
                            in (
                                VoiceState.WORKING,
                                VoiceState.NARRATING,
                            )
                        ):
                            asyncio.ensure_future(
                                session.handle_mid_conversation_audio(audio_data)
                            )
                        else:
                            # Cancel any existing processing
                            if processing_task and not processing_task.done():
                                await session.handle_interrupt()
                                processing_task.cancel()
                                try:
                                    await processing_task
                                except asyncio.CancelledError:
                                    pass

                            processing_task = asyncio.ensure_future(
                                session.handle_user_audio(audio_data)
                            )

                elif msg_type == "text.input":
                    text = msg.get("text", "").strip()
                    if text:
                        # If thinker is working, route to mid-conversation
                        # handler (injects steering instead of canceling)
                        if (
                            processing_task
                            and not processing_task.done()
                            and session.state
                            in (
                                VoiceState.WORKING,
                                VoiceState.NARRATING,
                            )
                        ):
                            asyncio.ensure_future(
                                session.handle_mid_conversation_text(text)
                            )
                        else:
                            # Cancel any existing processing
                            if processing_task and not processing_task.done():
                                await session.handle_interrupt()
                                processing_task.cancel()
                                try:
                                    await processing_task
                                except asyncio.CancelledError:
                                    pass

                            processing_task = asyncio.ensure_future(
                                session.handle_user_text(text)
                            )

                elif msg_type == "interrupt":
                    await session.handle_interrupt()

                elif msg_type == "config":
                    if "voice" in msg:
                        session.tts_voice = msg["voice"]
                    if "language" in msg:
                        session.tts_language = msg["language"]
                    if "agent" in msg:
                        session.agent_name = msg["agent"]
                        session.agent = Agent(
                            agent_name=msg["agent"],
                            user=user,
                            ApiClient=ApiClient,
                        )
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "status",
                                "data": {
                                    "state": "idle",
                                    "message": "Configuration updated",
                                },
                            }
                        )
                    )

                elif msg_type == "tools.register":
                    tools = msg.get("tools", [])
                    identity = msg.get("identity", "")
                    session.register_tools(tools, identity=identity)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "status",
                                "data": {
                                    "state": "idle",
                                    "message": f"Registered {len(tools)} client tools",
                                },
                            }
                        )
                    )

                elif msg_type == "tool.result":
                    request_id = msg.get("request_id", "")
                    result = msg.get("result", "")
                    if request_id:
                        await session.receive_tool_result(request_id, result)

                elif msg_type == "image.input":
                    image_data = msg.get("data", "")
                    if image_data:
                        asyncio.ensure_future(session.handle_image_input(image_data))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"[VoiceConversation WS] Error: {e}", exc_info=True)
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "data": {"message": f"Server error: {str(e)}"},
                    }
                )
            )
        except Exception:
            pass
    finally:
        if "session" in locals():
            await session.stop()
        try:
            await websocket.close()
        except Exception:
            pass
