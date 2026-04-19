import os
import re
import json
import time
import uuid
import base64
import asyncio
import logging
import tempfile
import httpx
from enum import Enum
from typing import Optional, Dict, List
from Globals import getenv
from Interactions import _ability_selection_inference
from Conversations import (
    Conversations,
    get_conversation_id_by_name,
)


class VoiceState(str, Enum):
    LISTENING = "listening"
    ACKNOWLEDGING = "acknowledging"
    WORKING = "working"
    NARRATING = "narrating"
    ANSWERING = "answering"
    WAITING_TOOL = "waiting_tool"
    IDLE = "idle"


class VoiceConversationSession:
    """
    Real-time voice conversation session with dual-model architecture.

    Speaker (0.8B): Fast triage, acknowledgments, progress narration, steering
    Thinker (35B): Full AGiXT pipeline for actual processing

    Key design principles:
    - Speaker triages: instant answers for trivial questions, thinker for everything else
    - Speaker injects [ACTIVITY] context so the thinker's continuation loop sees it
    - Thinker activity events (thinking, searching, executing) drive informed narration
    - Mid-conversation user speech is injected as steering context for thinker
    - Answer tokens stream to TTS as they arrive (no wait-then-monologue)
    - All I/O is async (httpx), no blocking thread pool calls
    """

    def __init__(
        self,
        agent_name: str,
        user: str,
        authorization: str,
        conversation_id: str,
        agent=None,
        ApiClient=None,
    ):
        self.agent_name = agent_name
        self.user = user
        self.authorization = authorization
        self.conversation_id = conversation_id
        self.agent = agent
        self.ApiClient = ApiClient

        # State machine
        self.state = VoiceState.IDLE
        self._state_lock = asyncio.Lock()

        # Server configuration
        self.voice_server = getenv("VOICE_SERVER")
        self.ability_server = getenv("ABILITY_SELECTION_SERVER")
        self.ability_model = getenv("ABILITY_SELECTION_MODEL")

        # Cancellation
        self._speaker_task: Optional[asyncio.Task] = None
        self._thinker_task: Optional[asyncio.Task] = None
        self._cancelled = False

        # WebSocket reference (set by endpoint)
        self.websocket = None

        # Audio config
        self.tts_voice = "default"
        self.tts_language = "en"

        # Keepalive
        self._keepalive_task: Optional[asyncio.Task] = None
        self._last_activity = time.time()
        self._keepalive_interval = 8.0

        # Client-side tools (registered by device like ESP32, robot SDK, etc.)
        self.client_tools: list = []

        # Tool result bridge: thinker waits here for client tool results
        self._pending_tool_results: Dict[str, asyncio.Future] = {}
        self._tool_result_lock = asyncio.Lock()

        # Thinker activity stream: real-time events from the AGiXT pipeline
        # used to drive informed narration instead of blind "still working" fillers
        self._thinker_activity: asyncio.Queue = asyncio.Queue()

        # Mid-conversation steering: user messages injected during thinker work
        self._steering_messages: List[str] = []
        self._steering_lock = asyncio.Lock()

        # Vision: latest camera frame from client (base64 JPEG)
        self._latest_image_b64: Optional[str] = None
        self._image_lock = asyncio.Lock()

        # Conversation helper (lazy-initialized)
        self._conversations: Optional[Conversations] = None

    def _get_conversations(self) -> Conversations:
        """Get or create Conversations instance for logging."""
        if self._conversations is None:
            self._conversations = Conversations(
                conversation_name=self.conversation_id,
                user=self.user,
            )
        return self._conversations

    # ─── State & Transport ──────────────────────────────────────────────

    async def set_state(self, new_state: VoiceState):
        async with self._state_lock:
            old_state = self.state
            self.state = new_state
            if old_state != new_state:
                logging.info(
                    f"[VoiceConversation] State: {old_state.value} -> {new_state.value}"
                )
                await self._send_event(
                    "status",
                    {"state": new_state.value, "previous": old_state.value},
                )

    async def _send_event(self, event_type: str, data: dict):
        if self.websocket and not self._cancelled:
            try:
                await self.websocket.send_text(
                    json.dumps({"type": event_type, "data": data})
                )
                self._last_activity = time.time()
            except Exception as e:
                logging.debug(f"[VoiceConversation] Send failed: {e}")

    async def _send_audio_chunk(self, chunk: bytes):
        if self.websocket and not self._cancelled:
            try:
                await self.websocket.send_bytes(chunk)
                self._last_activity = time.time()
            except Exception as e:
                logging.debug(f"[VoiceConversation] Audio send failed: {e}")

    # ─── Vision / Image Input ───────────────────────────────────────────

    async def handle_image_input(self, image_b64: str):
        """Store the latest camera frame from the client."""
        async with self._image_lock:
            self._latest_image_b64 = image_b64
        logging.debug(
            f"[VoiceConversation] Image frame received ({len(image_b64)} chars b64)"
        )

    async def _get_latest_image(self) -> Optional[str]:
        """Get and optionally clear the latest image frame."""
        async with self._image_lock:
            return self._latest_image_b64

    def _build_multimodal_content(self, text: str, image_b64: Optional[str]) -> object:
        """Build message content with text + optional image for the thinker."""
        if not image_b64:
            return text
        return [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]

    # ─── Client Tool Registration & Bridging ────────────────────────────

    def register_tools(self, tools: list):
        """Register client-side tools (from ESP32, robot SDK, etc.)."""
        self.client_tools = tools
        tool_names = [t.get("function", {}).get("name", "?") for t in tools]
        logging.info(
            f"[VoiceConversation] Registered {len(tools)} client tools: {tool_names}"
        )

    async def request_tool_execution(
        self, tool_name: str, tool_args: dict, request_id: str
    ) -> str:
        """Send tool request to client and wait for result."""
        future = asyncio.get_event_loop().create_future()
        async with self._tool_result_lock:
            self._pending_tool_results[request_id] = future

        await self.set_state(VoiceState.WAITING_TOOL)
        await self._send_event(
            "tool.request",
            {
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_args": tool_args,
            },
        )

        # Narrate while waiting for tool
        narration = await self._generate_tool_narration(tool_name)
        if narration:
            await self._send_event(
                "transcript.agent", {"text": narration, "role": "speaker"}
            )
            await self.speak(narration)

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            logging.warning(f"[VoiceConversation] Tool {tool_name} timed out after 30s")
            async with self._tool_result_lock:
                self._pending_tool_results.pop(request_id, None)
            return f"Error: Tool {tool_name} timed out"

    async def receive_tool_result(self, request_id: str, result: str):
        """Called when client sends tool result back."""
        async with self._tool_result_lock:
            future = self._pending_tool_results.pop(request_id, None)
        if future and not future.done():
            future.set_result(result)
            logging.info(
                f"[VoiceConversation] Tool result received for {request_id}: "
                f"{result[:100]}"
            )
        else:
            logging.warning(
                f"[VoiceConversation] No pending future for tool result {request_id}"
            )

    async def _generate_tool_narration(self, tool_name: str) -> str:
        """Generate brief narration about what tool we're using."""
        if not self.ability_server:
            return ""

        tool_descriptions = {
            "capture_image": "taking a photo with the camera",
            "send_ir": "sending an infrared signal",
            "get_ir_capabilities": "checking IR remote capabilities",
        }
        desc = tool_descriptions.get(tool_name, f"running {tool_name}")

        prompt = (
            f"You are a voice assistant narrating your current action. "
            f"You are: {desc}\n\n"
            f"Generate a very brief spoken phrase (under 10 words) about what "
            f"you're doing. Keep it casual and conversational. "
            f"Just one short phrase.\n\nYour narration:"
        )

        response = await _ability_selection_inference(
            self.ability_server, self.ability_model, prompt
        )
        if response:
            return response.strip("\"'")
        return ""

    # ─── Speaker Triage (0.8B) ──────────────────────────────────────────

    async def triage_message(self, user_text: str) -> str:
        """
        Classify user input:
        - GOODBYE: user is ending the conversation
        - INSTANT: trivial question 0.8B can answer directly
        - THINKER: needs full AGiXT pipeline (default for anything non-trivial)
        """
        if not self.ability_server:
            return "THINKER"

        prompt = f"""Classify the user's message into exactly one category.

User said: "{user_text}"

Categories:
- GOODBYE: User is ending the conversation (bye, thanks that's all, see you later, I'm done)
- INSTANT: Trivial factual/math that needs no tools or research (2+2, what is 5*3, say hello, repeat after me, simple greetings like "how are you")
- THINKER: Everything else - questions needing research, actions, commands, anything you're unsure about

Reply with exactly one word: GOODBYE, INSTANT, or THINKER

When in doubt, reply THINKER.

Your classification:"""

        response = await _ability_selection_inference(
            self.ability_server, self.ability_model, prompt
        )
        response = response.strip().upper()
        for category in ("GOODBYE", "INSTANT", "THINKER"):
            if category in response:
                return category
        return "THINKER"

    async def generate_instant_answer(self, user_text: str) -> str:
        """Use 0.8B to answer a trivial question directly."""
        if not self.ability_server:
            return ""

        prompt = (
            f"Answer the user's simple question directly and briefly "
            f"(1-2 sentences max). Be conversational.\n\n"
            f'User: "{user_text}"\n\nYour answer:'
        )

        response = await _ability_selection_inference(
            self.ability_server, self.ability_model, prompt
        )
        if response:
            return response.strip("\"'")
        return ""

    async def generate_speaker_triage(self, user_text: str) -> dict:
        """
        Produce triage context + acknowledgment. The context gets injected into
        the conversation as an [ACTIVITY] so the thinker's continuation loop sees it.
        """
        if not self.ability_server:
            return {
                "intent": "unknown",
                "context_note": "",
                "acknowledgment": "Got it, let me work on that.",
            }

        prompt = f"""You are triaging a voice conversation message for a thinking AI. Analyze this:

User said: "{user_text}"

Produce exactly 3 lines:
INTENT: (1-5 words describing what the user wants, e.g. "check the weather", "control TV via IR", "analyze an image")
CONTEXT: (1 sentence of useful context for the thinking AI, e.g. "User likely wants current conditions for their location", "This is a follow-up to the previous topic", "May need web search")
ACK: (brief spoken acknowledgment, 1 sentence, e.g. "Sure, let me look into that!")

INTENT:"""

        response = await _ability_selection_inference(
            self.ability_server, self.ability_model, prompt
        )

        intent = "unknown"
        context_note = ""
        acknowledgment = "Got it, let me work on that."

        if response:
            for line in response.strip().split("\n"):
                line = line.strip()
                upper = line.upper()
                if upper.startswith("INTENT:"):
                    intent = line[7:].strip().strip("\"'")
                elif upper.startswith("CONTEXT:"):
                    context_note = line[8:].strip().strip("\"'")
                elif upper.startswith("ACK:"):
                    acknowledgment = line[4:].strip().strip("\"'")
            if intent == "unknown" and not context_note:
                acknowledgment = response.strip().strip("\"'")[:200]

        return {
            "intent": intent,
            "context_note": context_note,
            "acknowledgment": acknowledgment,
        }

    async def _generate_goodbye(self, user_text: str) -> str:
        """Use 0.8B to generate a brief goodbye message."""
        if not self.ability_server:
            return "Goodbye! Talk to you later."

        prompt = (
            f"The user is ending the conversation. Generate a brief, warm "
            f"goodbye response (1 sentence max).\n\n"
            f'User said: "{user_text}"\n\nYour goodbye response:'
        )

        response = await _ability_selection_inference(
            self.ability_server, self.ability_model, prompt
        )
        response = response.strip().strip('"')
        if not response or len(response) > 200:
            return "Goodbye! Talk to you later."
        return response

    # ─── Conversation Context Injection ─────────────────────────────────

    def _log_activity(self, message: str):
        """Log an [ACTIVITY] message that the thinker sees but users don't."""
        try:
            c = self._get_conversations()
            c.log_interaction(role=self.agent_name, message=f"[ACTIVITY] {message}")
        except Exception as e:
            logging.debug(f"[VoiceConversation] Activity log failed: {e}")

    def _log_speaker_ack(self, ack_text: str):
        """Log the speaker acknowledgment as an activity so the thinker knows."""
        self._log_activity(f'[SPEAKER] Acknowledged user with: "{ack_text}"')

    def _log_speaker_triage(self, intent: str, context_note: str):
        """Log the speaker's triage analysis for the thinker."""
        parts = [f"[SPEAKER] Triage — Intent: {intent}"]
        if context_note:
            parts.append(f"Context: {context_note}")
        self._log_activity(" | ".join(parts))

    async def inject_steering_message(self, user_text: str):
        """
        Called when user speaks during thinker processing.
        Injects as a conversation message the thinker's continuation loop
        will pick up on the next iteration.
        """
        try:
            c = self._get_conversations()
            c.log_interaction(role="USER", message=user_text)
            async with self._steering_lock:
                self._steering_messages.append(user_text)
            logging.info(f"[VoiceConversation] Steering injected: '{user_text[:80]}'")
        except Exception as e:
            logging.debug(f"[VoiceConversation] Steering injection failed: {e}")

    # ─── STT via Voice Server (async httpx) ─────────────────────────────

    async def transcribe(self, audio_data: bytes) -> str:
        """Send audio to voice server for STT transcription."""
        if not self.voice_server:
            logging.error("[VoiceConversation] No VOICE_SERVER configured")
            return ""

        api_url = self.voice_server.rstrip("/") + "/v1/audio/transcriptions"
        api_key = getenv("EZLOCALAI_API_KEY", "none") or "none"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(temp_path, "rb") as audio_file:
                    resp = await client.post(
                        api_url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": ("audio.wav", audio_file, "audio/wav")},
                        data={"model": "base"},
                    )
                resp.raise_for_status()
                result = resp.json()
                return result.get("text", "").strip()
        except Exception as e:
            logging.error(f"[VoiceConversation] STT error: {e}")
            return ""
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    # ─── TTS via Voice Server ───────────────────────────────────────────

    async def speak(self, text: str):
        """Stream TTS audio to client via voice server."""
        if not text or not self.voice_server or self._cancelled:
            return

        text = self._clean_for_tts(text)
        if not text:
            return

        api_url = self.voice_server.rstrip("/") + "/v1/audio/speech/stream"
        api_key = getenv("EZLOCALAI_API_KEY", "none") or "none"

        payload = {
            "model": "tts-1",
            "voice": self.tts_voice,
            "input": text,
            "language": self.tts_language,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST", api_url, headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    first_chunk = True
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if self._cancelled:
                            break
                        if first_chunk:
                            await self._send_event(
                                "audio.header",
                                {
                                    "format": "pcm",
                                    "sample_rate": 24000,
                                    "bits_per_sample": 16,
                                    "channels": 1,
                                },
                            )
                            first_chunk = False
                        await self._send_audio_chunk(chunk)

            if not self._cancelled:
                await self._send_event("audio.end", {})
        except httpx.HTTPStatusError as e:
            logging.error(f"[VoiceConversation] TTS stream HTTP error: {e}")
        except Exception as e:
            logging.error(f"[VoiceConversation] TTS stream error: {e}")

    def _clean_for_tts(self, text: str) -> str:
        """Clean text for TTS - remove code blocks, URLs, XML tags."""
        if "```" in text:
            text = re.sub(
                r"```[^`]*```",
                "See the chat for the code.",
                text,
                flags=re.DOTALL,
            )
        text = re.sub(r"https?://[^\s<>]+", "", text)
        text = re.sub(
            r"</?(?:thinking|reflection|answer|execute|output|step|reward|count|speak)[^>]*>",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\*+", "", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ─── Thinker (35B via AGiXT pipeline) with activity streaming ──────

    async def run_thinker(self, user_text: str) -> str:
        """
        Run the full AGiXT pipeline and collect the response.

        Parses activity events (activity.stream) and pushes them to
        self._thinker_activity queue for the narrator to consume.
        Streams answer tokens for progressive TTS.
        Handles tool calls by bridging through WebSocket to client device.
        """
        from XT import AGiXT
        from Models import ChatCompletions

        try:
            agixt = AGiXT(
                user=self.user,
                agent_name=self.agent_name,
                api_key=self.authorization,
                conversation_name=self.conversation_id,
            )

            # Attach latest camera frame if available
            image_b64 = await self._get_latest_image()
            message_content = self._build_multimodal_content(user_text, image_b64)

            prompt = ChatCompletions(
                model=self.agent_name,
                messages=[{"role": "user", "content": message_content}],
                user=self.conversation_id,
                tts_mode="off",
                tools=self.client_tools if self.client_tools else None,
            )

            full_response = ""
            pending_tool_calls = []

            async for chunk_str in agixt._execute_chat_completions_stream(prompt):
                if self._cancelled:
                    break
                for line in chunk_str.split("\n"):
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        obj_type = chunk_data.get("object", "")

                        # Remote command requests (tool calls to client)
                        if obj_type == "remote_command.request":
                            tool_name = chunk_data.get("tool_name", "")
                            tool_args = chunk_data.get("tool_args", {})
                            request_id = chunk_data.get(
                                "request_id",
                                f"call_{uuid.uuid4().hex[:8]}",
                            )
                            if tool_name:
                                pending_tool_calls.append(
                                    {
                                        "tool_name": tool_name,
                                        "tool_args": tool_args,
                                        "request_id": request_id,
                                    }
                                )
                            continue

                        # Activity events → push to narrator queue
                        if obj_type == "activity.stream":
                            activity_content = chunk_data.get("content", "")
                            if activity_content:
                                try:
                                    self._thinker_activity.put_nowait(
                                        {
                                            "type": "activity",
                                            "content": activity_content,
                                        }
                                    )
                                except asyncio.QueueFull:
                                    pass
                            continue

                        # Regular content chunk (answer tokens)
                        choices = chunk_data.get("choices", [{}])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                try:
                                    self._thinker_activity.put_nowait(
                                        {
                                            "type": "answer_token",
                                            "content": content,
                                        }
                                    )
                                except asyncio.QueueFull:
                                    pass
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass

            # Signal stream done
            try:
                self._thinker_activity.put_nowait({"type": "done"})
            except asyncio.QueueFull:
                pass

            # Execute any pending tool calls through the client
            if pending_tool_calls and not self._cancelled:
                for tool_call in pending_tool_calls:
                    if self._cancelled:
                        break
                    tool_result = await self.request_tool_execution(
                        tool_name=tool_call["tool_name"],
                        tool_args=tool_call["tool_args"],
                        request_id=tool_call["request_id"],
                    )
                    await self.set_state(VoiceState.WORKING)
                    continuation = await self._continue_after_tool(
                        agixt, tool_call, tool_result
                    )
                    if continuation:
                        full_response = continuation

            logging.info(
                f"[VoiceConversation] Thinker response: {len(full_response)} chars"
            )
            return full_response
        except Exception as e:
            logging.error(f"[VoiceConversation] Thinker error: {e}", exc_info=True)
            return ""

    async def _continue_after_tool(
        self, agixt, tool_call: dict, tool_result: str
    ) -> str:
        """After a tool executes, submit result and get the LLM's follow-up."""
        from Models import ChatCompletions

        try:
            messages = [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_call["request_id"],
                            "type": "function",
                            "function": {
                                "name": tool_call["tool_name"],
                                "arguments": json.dumps(tool_call["tool_args"]),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": tool_call["request_id"],
                    "content": tool_result,
                },
            ]

            prompt = ChatCompletions(
                model=self.agent_name,
                messages=messages,
                user=self.conversation_id,
                tts_mode="off",
            )

            full_response = ""
            async for chunk_str in agixt._execute_chat_completions_stream(prompt):
                if self._cancelled:
                    break
                for line_str in chunk_str.split("\n"):
                    line_str = line_str.strip()
                    if not line_str.startswith("data: "):
                        continue
                    data_str = line_str[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        content = (
                            chunk_data.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if content:
                            full_response += content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass

            return full_response
        except Exception as e:
            logging.error(
                f"[VoiceConversation] Tool continuation error: {e}",
                exc_info=True,
            )
            return ""

    # ─── Main Conversation Loop ────────────────────────────────────────

    async def _process_user_input(self, user_text: str):
        """
        Unified pipeline for both audio and text input.

        Flow:
        1. Speaker triage (0.8B): GOODBYE / INSTANT / THINKER
        2. If GOODBYE: farewell + session.end
        3. If INSTANT: 0.8B answers directly, log as activity, skip thinker
        4. If THINKER:
           a. Speaker generates triage context + acknowledgment (parallel with
              thinker start)
           b. Triage context injected as [ACTIVITY] for thinker continuation loop
           c. Ack spoken via TTS (non-blocking, thinker monitors in parallel)
           d. Activity-aware narrator speaks progress from real thinker events
           e. Answer tokens stream to TTS as sentences complete
           f. On thinker failure, retry once; then fall back to speaker error
        """
        # 1. Triage
        category = await self.triage_message(user_text)
        logging.info(f"[VoiceConversation] Triage: '{user_text[:60]}' -> {category}")

        # 2. GOODBYE
        if category == "GOODBYE":
            goodbye = await self._generate_goodbye(user_text)
            await self._send_event(
                "transcript.agent", {"text": goodbye, "role": "speaker"}
            )
            await self.speak(goodbye)
            await self._send_event("session.end", {"reason": "user_goodbye"})
            await self.set_state(VoiceState.IDLE)
            return

        # 3. INSTANT — 0.8B answers directly
        if category == "INSTANT":
            await self.set_state(VoiceState.ANSWERING)
            answer = await self.generate_instant_answer(user_text)
            if answer:
                self._log_activity(f'[SPEAKER] Answered instantly: "{answer}"')
                await self._send_event(
                    "transcript.agent", {"text": answer, "role": "speaker"}
                )
                await self.speak(answer)
            await self.set_state(VoiceState.IDLE)
            return

        # 4. THINKER — full pipeline
        await self.set_state(VoiceState.ACKNOWLEDGING)

        # Clear activity queue and steering for fresh run
        while not self._thinker_activity.empty():
            try:
                self._thinker_activity.get_nowait()
            except asyncio.QueueEmpty:
                break
        async with self._steering_lock:
            self._steering_messages.clear()

        # Run triage + thinker start in parallel
        triage_task = asyncio.ensure_future(self.generate_speaker_triage(user_text))
        thinker_task = asyncio.ensure_future(self.run_thinker(user_text))
        self._thinker_task = thinker_task

        # Wait for triage (fast, ~200ms)
        triage = await triage_task

        # Inject triage context as [ACTIVITY] for the thinker's continuation loop
        self._log_speaker_triage(triage["intent"], triage["context_note"])

        # Speak acknowledgment (non-blocking — fires TTS and continues)
        ack_text = triage["acknowledgment"]
        self._log_speaker_ack(ack_text)
        await self._send_event(
            "transcript.agent", {"text": ack_text, "role": "speaker"}
        )
        ack_speak_task = asyncio.ensure_future(self.speak(ack_text))

        # 4d/e. Activity-aware narrator + progressive answer TTS
        await self.set_state(VoiceState.WORKING)
        thinker_response = await self._monitor_thinker(thinker_task, ack_speak_task)

        if self._cancelled:
            return

        # 4f. Handle empty response: retry once, then fallback
        if not thinker_response:
            logging.warning("[VoiceConversation] Empty thinker response, retrying")
            self._log_activity("[SPEAKER] First attempt returned empty, retrying")
            while not self._thinker_activity.empty():
                try:
                    self._thinker_activity.get_nowait()
                except asyncio.QueueEmpty:
                    break

            retry_task = asyncio.ensure_future(self.run_thinker(user_text))
            self._thinker_task = retry_task
            thinker_response = await self._monitor_thinker(retry_task, None)

            if not thinker_response:
                fallback = (
                    "I'm sorry, I had trouble processing that. "
                    "Could you try asking again?"
                )
                await self._send_event(
                    "transcript.agent",
                    {"text": fallback, "role": "speaker"},
                )
                await self.speak(fallback)
                await self.set_state(VoiceState.IDLE)
                return

        await self.set_state(VoiceState.IDLE)

    async def _monitor_thinker(
        self,
        thinker_task: asyncio.Task,
        ack_speak_task: Optional[asyncio.Task],
    ) -> str:
        """
        Monitor the thinker while it runs:
        - Consume activity events for informed narration
        - Accumulate answer tokens and stream TTS as sentences complete
        - Ensure ack TTS finishes before starting answer TTS
        """
        answer_buffer = ""
        answer_spoken_up_to = 0
        last_narration_time = time.time()
        narration_interval = 10.0
        last_activity_desc = ""
        thinker_done = False

        while not thinker_done and not self._cancelled:
            # Drain activity queue
            try:
                event = await asyncio.wait_for(
                    self._thinker_activity.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                event = None

            if event is None:
                if thinker_task.done():
                    thinker_done = True
                    continue
                # Maybe narrate if it's been a while
                elapsed = time.time() - last_narration_time
                if elapsed >= narration_interval and self.state == VoiceState.WORKING:
                    narration = await self._generate_informed_narration(
                        last_activity_desc
                    )
                    if narration:
                        if ack_speak_task and not ack_speak_task.done():
                            try:
                                await asyncio.wait_for(ack_speak_task, timeout=5.0)
                            except (
                                asyncio.TimeoutError,
                                asyncio.CancelledError,
                            ):
                                pass
                            ack_speak_task = None
                        await self.set_state(VoiceState.NARRATING)
                        await self._send_event(
                            "transcript.agent",
                            {"text": narration, "role": "speaker"},
                        )
                        await self.speak(narration)
                        await self.set_state(VoiceState.WORKING)
                        last_narration_time = time.time()
                continue

            etype = event.get("type", "")

            if etype == "done":
                thinker_done = True
                continue

            if etype == "activity":
                last_activity_desc = event.get("content", "")
                # Reset narration timer on new activity — narrate sooner
                last_narration_time = time.time() - (narration_interval - 3.0)
                continue

            if etype == "answer_token":
                answer_buffer += event.get("content", "")

                # Progressive TTS: check if we have a complete sentence
                speakable = self._extract_complete_sentences(
                    answer_buffer[answer_spoken_up_to:]
                )
                if speakable:
                    # Ensure ack TTS is done before speaking answer
                    if ack_speak_task and not ack_speak_task.done():
                        try:
                            await asyncio.wait_for(ack_speak_task, timeout=10.0)
                        except (
                            asyncio.TimeoutError,
                            asyncio.CancelledError,
                        ):
                            pass
                        ack_speak_task = None

                    if self.state != VoiceState.ANSWERING:
                        await self.set_state(VoiceState.ANSWERING)
                        await self._send_event(
                            "transcript.agent",
                            {"text": "(streaming)", "role": "thinker"},
                        )

                    await self.speak(speakable)
                    answer_spoken_up_to += len(speakable)
                continue

        # Ensure ack TTS is done
        if ack_speak_task and not ack_speak_task.done():
            try:
                await asyncio.wait_for(ack_speak_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        # Get the full response from the task
        try:
            full_response = await thinker_task
        except asyncio.CancelledError:
            return ""
        except Exception as e:
            logging.error(f"[VoiceConversation] Thinker task error: {e}")
            return ""

        # Speak any remaining un-spoken portion of the answer
        if full_response and answer_spoken_up_to < len(full_response):
            remaining = full_response[answer_spoken_up_to:].strip()
            if remaining:
                if self.state != VoiceState.ANSWERING:
                    await self.set_state(VoiceState.ANSWERING)
                await self._send_event(
                    "transcript.agent",
                    {"text": full_response, "role": "thinker"},
                )
                await self._speak_in_sentences(remaining)
        elif full_response and answer_spoken_up_to > 0:
            # Already streamed partial transcript, send final full text
            await self._send_event(
                "transcript.agent",
                {"text": full_response, "role": "thinker"},
            )

        return full_response

    async def _generate_informed_narration(self, activity_desc: str) -> str:
        """Generate narration based on actual thinker activity."""
        if not self.ability_server:
            return ""

        if activity_desc:
            prompt = (
                f"You are a voice assistant narrating what you're doing. "
                f"Current activity: {activity_desc}\n\n"
                f"Generate ONE brief spoken phrase (under 12 words) about your "
                f"current progress. Sound natural and conversational.\n\n"
                f"Your narration:"
            )
        else:
            prompt = (
                "You are a voice assistant and you've been thinking for a while. "
                "Generate ONE very brief filler phrase to let the user know "
                "you're still working. Just one short phrase.\n\n"
                'Examples: "Still working on it...", '
                '"Bear with me a moment..."\n\nYour filler:'
            )

        response = await _ability_selection_inference(
            self.ability_server, self.ability_model, prompt
        )
        if response:
            return response.strip("\"'")
        return ""

    def _extract_complete_sentences(self, text: str) -> str:
        """
        Extract complete sentences from the beginning of text for progressive
        TTS. Returns the speakable portion, or empty string if none ready.
        """
        text = self._clean_for_tts(text)
        if not text:
            return ""

        last_boundary = -1
        for m in re.finditer(r"[.!?]\s+", text):
            last_boundary = m.end()

        if last_boundary > 20:
            return text[:last_boundary].strip()
        return ""

    # ─── Entry Points ──────────────────────────────────────────────────

    async def handle_user_audio(self, audio_data: bytes):
        """Main entry point when user sends audio."""
        await self.cancel_speaker()

        await self.set_state(VoiceState.LISTENING)
        user_text = await self.transcribe(audio_data)

        if not user_text:
            await self._send_event(
                "transcript.user",
                {"text": "", "error": "Could not transcribe audio"},
            )
            await self.set_state(VoiceState.IDLE)
            return

        await self._send_event("transcript.user", {"text": user_text})
        logging.info(f"[VoiceConversation] User said: {user_text}")
        await self._process_user_input(user_text)

    async def handle_user_text(self, text: str):
        """Handle text input (typed) — same pipeline but skip STT."""
        await self.cancel_speaker()
        await self._send_event("transcript.user", {"text": text})
        logging.info(f"[VoiceConversation] User typed: {text}")
        await self._process_user_input(text)

    async def handle_mid_conversation_audio(self, audio_data: bytes):
        """
        Handle audio arriving while the thinker is still working.
        Transcribe and inject as steering context instead of interrupting.
        """
        if self.state not in (VoiceState.WORKING, VoiceState.NARRATING):
            return await self.handle_user_audio(audio_data)

        user_text = await self.transcribe(audio_data)
        if not user_text:
            return

        await self._send_event("transcript.user", {"text": user_text})
        logging.info(f"[VoiceConversation] Mid-conversation steering: {user_text}")

        category = await self.triage_message(user_text)
        if category == "GOODBYE":
            await self.handle_interrupt()
            goodbye = await self._generate_goodbye(user_text)
            await self._send_event(
                "transcript.agent", {"text": goodbye, "role": "speaker"}
            )
            await self.speak(goodbye)
            await self._send_event("session.end", {"reason": "user_goodbye"})
            await self.set_state(VoiceState.IDLE)
            return

        await self.inject_steering_message(user_text)
        steering_ack = "Noted, I'll take that into account."
        await self._send_event(
            "transcript.agent",
            {"text": steering_ack, "role": "speaker"},
        )
        await self.speak(steering_ack)

    async def handle_mid_conversation_text(self, text: str):
        """Handle text arriving while the thinker is still working."""
        if self.state not in (VoiceState.WORKING, VoiceState.NARRATING):
            return await self.handle_user_text(text)

        await self._send_event("transcript.user", {"text": text})
        logging.info(f"[VoiceConversation] Mid-conversation steering: {text}")

        category = await self.triage_message(text)
        if category == "GOODBYE":
            await self.handle_interrupt()
            goodbye = await self._generate_goodbye(text)
            await self._send_event(
                "transcript.agent", {"text": goodbye, "role": "speaker"}
            )
            await self.speak(goodbye)
            await self._send_event("session.end", {"reason": "user_goodbye"})
            await self.set_state(VoiceState.IDLE)
            return

        await self.inject_steering_message(text)
        steering_ack = "Noted, I'll take that into account."
        await self._send_event(
            "transcript.agent",
            {"text": steering_ack, "role": "speaker"},
        )
        await self.speak(steering_ack)

    # ─── Helpers ────────────────────────────────────────────────────────

    async def _speak_in_sentences(self, text: str):
        """Stream TTS sentence-by-sentence for natural delivery."""
        sentences = self._split_sentences(text)
        for sentence in sentences:
            if self._cancelled:
                break
            sentence = sentence.strip()
            if sentence and len(sentence) > 1:
                await self.speak(sentence)

    def _split_sentences(self, text: str) -> list:
        """Split text into sentences for progressive TTS."""
        parts = re.split(r"(?<=[.!?])\s+", text)
        merged = []
        buffer = ""
        for part in parts:
            buffer += (" " if buffer else "") + part
            if len(buffer) > 20:
                merged.append(buffer)
                buffer = ""
        if buffer:
            merged.append(buffer)
        return merged

    # ─── Interruption Handling ──────────────────────────────────────────

    async def cancel_speaker(self):
        """Cancel ongoing speaker audio (barge-in). Thinker keeps running."""
        if self._speaker_task and not self._speaker_task.done():
            self._speaker_task.cancel()
            try:
                await self._speaker_task
            except asyncio.CancelledError:
                pass
            self._speaker_task = None
        await self._send_event("audio.interrupt", {})

    async def handle_interrupt(self):
        """Handle user barge-in / interrupt."""
        logging.info("[VoiceConversation] User interrupted")
        await self.cancel_speaker()

    # ─── Keepalive ──────────────────────────────────────────────────────

    async def start_keepalive(self):
        """Start sending keepalive pings to prevent timeout."""

        async def _keepalive_loop():
            while not self._cancelled:
                await asyncio.sleep(self._keepalive_interval)
                if self._cancelled:
                    break
                elapsed = time.time() - self._last_activity
                if elapsed >= self._keepalive_interval:
                    await self._send_event("heartbeat", {"ts": time.time()})

        self._keepalive_task = asyncio.ensure_future(_keepalive_loop())

    async def stop(self):
        """Clean shutdown of the session."""
        self._cancelled = True
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        if self._thinker_task and not self._thinker_task.done():
            self._thinker_task.cancel()
            try:
                await self._thinker_task
            except asyncio.CancelledError:
                pass
        if self._speaker_task and not self._speaker_task.done():
            self._speaker_task.cancel()
            try:
                await self._speaker_task
            except asyncio.CancelledError:
                pass
        logging.info("[VoiceConversation] Session stopped")
