"""
ezLocalai AI Provider Extension for AGiXT

This extension provides AI inference capabilities using ezLocalai, a local AI server
that supports text generation, text-to-speech, image generation, transcription, and translation.

To set up ezLocalai, visit: https://github.com/DevXT-LLC/ezlocalai

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API URI.
"""

import base64
import json
import logging
import os
import random
import re
import uuid
import requests
import numpy as np
from Extensions import Extensions
from Globals import getenv
import asyncio
from functools import partial


def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in the default thread pool executor.

    This prevents blocking the asyncio event loop when making synchronous
    HTTP requests (e.g. requests.post), which would starve other coroutines
    like Discord heartbeats.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, partial(func, *args, **kwargs))


class StreamChunk:
    """Wrapper class to provide OpenAI SDK-like interface for streaming chunks."""

    def __init__(self, data: dict):
        self._data = data
        self.choices = [StreamChoice(c) for c in data.get("choices", [])]


class StreamChoice:
    """Wrapper for streaming choice data."""

    def __init__(self, choice_data: dict):
        self.delta = StreamDelta(choice_data.get("delta", {}))
        self.finish_reason = choice_data.get("finish_reason")


class StreamDelta:
    """Wrapper for streaming delta data."""

    def __init__(self, delta_data: dict):
        self.content = delta_data.get("content")
        self.role = delta_data.get("role")


def parse_sse_stream(response):
    """Parse Server-Sent Events stream and yield StreamChunk objects."""
    for line in response.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
        if line_str.startswith("data: "):
            data_str = line_str[6:]  # Remove "data: " prefix
            if data_str.strip() == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                yield StreamChunk(data)
            except json.JSONDecodeError:
                continue


class ezlocalai(Extensions):
    """
    ezLocalai AI Provider - Local AI inference server supporting LLM, TTS, image generation, and transcription.

    Set up ezLocalai at https://github.com/DevXT-LLC/ezlocalai
    """

    CATEGORY = "AI Provider"
    friendly_name = "ezLocalai"

    # Services this AI provider supports
    SERVICES = [
        "llm",
        "tts",
        "image",
        "transcription",
        "translation",
        "vision",
        "embeddings",
        "video",
    ]

    def __init__(
        self,
        EZLOCALAI_API_URI: str = "",
        EZLOCALAI_API_KEY: str = "",
        EZLOCALAI_AI_MODEL: str = "unsloth/Qwen3.6-35B-A3B-GGUF",
        EZLOCALAI_CODING_MODEL: str = "unsloth/Qwen3.6-35B-A3B-GGUF",
        EZLOCALAI_MAX_TOKENS: int = 250000,
        EZLOCALAI_TEMPERATURE: float = 1.33,
        EZLOCALAI_TOP_P: float = 0.95,
        EZLOCALAI_VOICE: str = "HAL9000",
        EZLOCALAI_LANGUAGE: str = "en",
        EZLOCALAI_TRANSCRIPTION_MODEL: str = "base",
        **kwargs,
    ):
        import os as _os
        import logging as _logging

        # Extension base initialization (matches essential_abilities pattern)
        self.agent_name = kwargs.get("agent_name", "AGiXT")
        self.agent_id = kwargs.get("agent_id")
        self.ApiClient = kwargs.get("ApiClient", None)
        self.user = kwargs.get("user", None)
        self.user_id = kwargs.get("user_id", None)
        self.conversation_name = kwargs.get("conversation_name", "")
        self.conversation_id = kwargs.get("conversation_id", "")
        self.activity_id = kwargs.get("activity_id", None)

        # Get URI from parameter or environment
        if not EZLOCALAI_API_URI:
            EZLOCALAI_API_URI = getenv("EZLOCALAI_API_URI", getenv("EZLOCALAI_URI", ""))
            # Only log when there's an issue (empty after fallback)
            if not EZLOCALAI_API_URI:
                _logging.warning(
                    f"[ezlocalai] No EZLOCALAI_API_URI configured. "
                    f"os.getenv('EZLOCALAI_API_URI')='{_os.getenv('EZLOCALAI_API_URI', 'NOT_SET')}', "
                    f"os.getenv('EZLOCALAI_URI')='{_os.getenv('EZLOCALAI_URI', 'NOT_SET')}'"
                )

        # Get API key from parameter or environment
        if not EZLOCALAI_API_KEY:
            EZLOCALAI_API_KEY = getenv("EZLOCALAI_API_KEY", "")

        # Get MAX_TOKENS from parameter or environment
        if not EZLOCALAI_MAX_TOKENS or EZLOCALAI_MAX_TOKENS == 1000000:
            env_max_tokens = getenv("EZLOCALAI_MAX_TOKENS", "")
            if env_max_tokens:
                try:
                    EZLOCALAI_MAX_TOKENS = int(env_max_tokens)
                except (ValueError, TypeError):
                    EZLOCALAI_MAX_TOKENS = 1000000

        # Normalize URI
        if EZLOCALAI_API_URI and not EZLOCALAI_API_URI.endswith("/"):
            EZLOCALAI_API_URI += "/"
        if EZLOCALAI_API_URI and "v1/" not in EZLOCALAI_API_URI:
            EZLOCALAI_API_URI += "v1/"

        self.API_URI = EZLOCALAI_API_URI
        # Validate API key is safe for HTTP headers (latin-1 encodable).
        # Masked/corrupted values (e.g. bullet chars from UI) must be discarded.
        try:
            if EZLOCALAI_API_KEY:
                EZLOCALAI_API_KEY.encode("latin-1")
        except UnicodeEncodeError:
            logging.warning(
                "[ezlocalai] API key contains non-ASCII characters (possibly masked value), ignoring"
            )
            EZLOCALAI_API_KEY = ""
        self.EZLOCALAI_API_KEY = EZLOCALAI_API_KEY

        # Check if this provider is configured (has a valid URI set)
        self.configured = bool(
            self.API_URI
            and self.API_URI.strip() != ""
            and self.API_URI.lower() not in ["none", "null", "false", "0"]
        )

        # Model configuration
        self.AI_MODEL = EZLOCALAI_AI_MODEL if EZLOCALAI_AI_MODEL else "default"
        self.CODING_MODEL = (
            EZLOCALAI_CODING_MODEL
            if EZLOCALAI_CODING_MODEL
            else "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF"
        )
        # Handle MAX_TOKENS safely - might receive encrypted/invalid values from database
        try:
            self.MAX_TOKENS = (
                int(EZLOCALAI_MAX_TOKENS) if EZLOCALAI_MAX_TOKENS else 1000000
            )
        except (ValueError, TypeError):
            self.MAX_TOKENS = 1000000
        # Handle TEMPERATURE safely
        try:
            self.AI_TEMPERATURE = (
                float(EZLOCALAI_TEMPERATURE) if EZLOCALAI_TEMPERATURE else 1.33
            )
        except (ValueError, TypeError):
            self.AI_TEMPERATURE = 1.33
        # Handle TOP_P safely
        try:
            self.AI_TOP_P = float(EZLOCALAI_TOP_P) if EZLOCALAI_TOP_P else 0.95
        except (ValueError, TypeError):
            self.AI_TOP_P = 0.95

        # TTS configuration
        self.VOICE = EZLOCALAI_VOICE if EZLOCALAI_VOICE else "HAL9000"
        self.TTS_LANGUAGE = EZLOCALAI_LANGUAGE if EZLOCALAI_LANGUAGE else "en"
        if len(self.TTS_LANGUAGE) > 2:
            self.TTS_LANGUAGE = self.TTS_LANGUAGE[:2].lower()

        # Transcription configuration
        self.TRANSCRIPTION_MODEL = (
            EZLOCALAI_TRANSCRIPTION_MODEL if EZLOCALAI_TRANSCRIPTION_MODEL else "base"
        )

        # Output URL for generated files on the ezlocalai server
        self.OUTPUT_URL = (
            self.API_URI.replace("/v1/", "/outputs/") if self.API_URI else ""
        )

        # Workspace directory for saving generated files (injected by Extensions)
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
        self.output_url = kwargs.get("output_url", "")

        # Failure tracking for rotation
        self.FAILURES = []
        self.failure_count = 0

        # Commands for AI Provider extensions - these allow the AI to explicitly choose this provider
        self.commands = {
            "Generate Text with ezLocalai": self.generate_text_command,
            "Generate Image with ezLocalai": self.generate_image_command,
            "Edit Image with ezLocalai": self.edit_image_command,
            "Generate Video with ezLocalai": self.generate_video_command,
            "Image to Video with ezLocalai": self.image_to_video_command,
            "Video to Video with ezLocalai": self.video_to_video_command,
            "Text to Speech with ezLocalai": self.text_to_speech_command,
            "Transcribe Audio with ezLocalai": self.transcribe_audio_command,
        }

    @staticmethod
    def services():
        """Return list of services this provider supports"""
        return [
            "llm",
            "tts",
            "image",
            "transcription",
            "translation",
            "vision",
            "embeddings",
            "video",
        ]

    def get_max_tokens(self):
        """Return the maximum token limit for this provider"""
        return self.MAX_TOKENS

    def is_configured(self):
        """Check if this provider is properly configured"""
        return self.configured

    def rotate_uri(self):
        """Rotate to a different URI if multiple are configured"""
        self.FAILURES.append(self.API_URI)
        uri_list = self.API_URI.split(",")
        random.shuffle(uri_list)
        for uri in uri_list:
            if uri not in self.FAILURES:
                self.API_URI = uri
                break

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        """
        Generate text using ezLocalai LLM.

        Args:
            prompt: The input prompt
            tokens: Input token count (for budgeting, not output limit)
            images: List of image URLs or paths for vision tasks
            stream: Whether to stream the response
            use_smartest: Use the coding/smartest model

        Returns:
            Generated text response or stream object
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured - missing API URI")

        model = self.CODING_MODEL if use_smartest else self.AI_MODEL
        if not model:
            model = "default"
        # Use a dummy API key if none is set
        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Build messages with optional vision content
        messages = []
        if images:
            content = [{"type": "text", "text": prompt}]
            for image in images:
                if image.startswith("http") or image.startswith("data:"):
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": image},
                        }
                    )
                else:
                    # Local file path - read and encode
                    file_type = image.split(".")[-1]
                    with open(image, "rb") as f:
                        image_base64 = base64.b64encode(f.read()).decode("utf-8")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{file_type};base64,{image_base64}"
                            },
                        }
                    )
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": float(self.AI_TEMPERATURE),
                "top_p": float(self.AI_TOP_P),
                "n": 1,
                "stream": stream,
                "stop": ["</execute>"],
            }

            api_url = self.API_URI.rstrip("/") + "/chat/completions"

            if stream:
                # Return a generator for streaming with OpenAI SDK-like interface
                # Use a longer connection timeout (600s) since the inference slot
                # may be busy with another request and we need to wait in queue.
                # The read timeout for individual chunks is set to 120s.
                # Run in executor to avoid blocking the event loop (Discord heartbeat etc.)
                resp = await _run_sync(
                    requests.post,
                    api_url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=(600, 120),
                )
                resp.raise_for_status()
                return parse_sse_stream(resp)

            resp = await _run_sync(
                requests.post,
                api_url,
                headers=headers,
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            response = data["choices"][0]["message"]["content"]

            # Clean up response
            if "User:" in response:
                response = response.split("User:")[0]
            response = response.lstrip()
            response = response.replace("<s>", "").replace("</s>", "")

            # Fix output URLs
            if "http://localhost:8091/outputs/" in response:
                response = response.replace(
                    "http://localhost:8091/outputs/", self.OUTPUT_URL
                )

            if self.OUTPUT_URL and self.OUTPUT_URL in response:
                urls = re.findall(f"{re.escape(self.OUTPUT_URL)}[^\"' ]+", response)
                if urls:
                    urls = urls[0].split("\n\n")
                    for url in urls:
                        file_type = url.split(".")[-1]
                        if file_type == "wav":
                            response = response.replace(
                                url,
                                f'<audio controls><source src="{url}" type="audio/wav"></audio>',
                            )
                        else:
                            response = response.replace(url, f"![{file_type}]({url})")

            return response

        except Exception as e:
            self.failure_count += 1
            logging.error(f"ezLocalai API Error on server {self.API_URI} {e}")

            if "," in self.API_URI:
                self.rotate_uri()

            if self.failure_count >= 3:
                raise Exception(f"ezLocalai API Error: Too many failures. {e}")

            return await self.inference(
                prompt=prompt,
                tokens=tokens,
                images=images,
                stream=stream,
                use_smartest=use_smartest,
            )

    async def transcribe_audio(
        self,
        audio_path: str,
        enable_diarization: bool = False,
        num_speakers: int = None,
        session_id: str = None,
    ) -> str:
        """
        Transcribe audio to text using ezLocalai.

        Args:
            audio_path: Path to the audio file
            enable_diarization: If True, perform speaker diarization
            num_speakers: Optional number of speakers (auto-detect if None)
            session_id: Optional session ID for persistent speaker voice prints

        Returns:
            Transcribed text, or dict with text/segments/language if diarization enabled
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {"Authorization": f"Bearer {api_key}"}
        api_url = self.API_URI.rstrip("/") + "/audio/transcriptions"

        with open(audio_path, "rb") as audio_file:
            files = {"file": audio_file}
            data = {"model": self.TRANSCRIPTION_MODEL}
            if enable_diarization:
                data["enable_diarization"] = "true"
                data["response_format"] = "verbose_json"
                if num_speakers is not None:
                    data["num_speakers"] = str(num_speakers)
            if session_id:
                data["session_id"] = session_id
            resp = await _run_sync(
                requests.post,
                api_url,
                headers=headers,
                files=files,
                data=data,
                timeout=120,
            )
            resp.raise_for_status()
            result = resp.json()
            if enable_diarization and "segments" in result:
                return result
            return result.get("text", "")

    async def translate_audio(self, audio_path: str) -> str:
        """
        Translate audio to English text using ezLocalai.

        Args:
            audio_path: Path to the audio file

        Returns:
            Translated text
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {"Authorization": f"Bearer {api_key}"}
        api_url = self.API_URI.rstrip("/") + "/audio/translations"

        with open(audio_path, "rb") as audio_file:
            files = {"file": audio_file}
            data = {"model": self.TRANSCRIPTION_MODEL}
            resp = await _run_sync(
                requests.post,
                api_url,
                headers=headers,
                files=files,
                data=data,
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")

    async def text_to_speech(self, text: str) -> str:
        """
        Convert text to speech using ezLocalai.

        Args:
            text: Text to convert to speech

        Returns:
            Base64 encoded audio content
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/audio/speech"

        payload = {
            "model": "tts-1",
            "voice": self.VOICE,
            "input": text,
            "language": self.TTS_LANGUAGE,
        }
        resp = await _run_sync(
            requests.post, api_url, headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")

    async def text_to_speech_stream(self, text: str):
        """
        Stream TTS audio as it's generated from ezLocalai.

        This enables real-time playback without waiting for the entire audio
        to be generated. Dramatically reduces time-to-first-word for long text.

        Yields binary chunks in format:
        - Header (8 bytes): sample_rate (uint32), bits (uint16), channels (uint16)
        - Data chunks: chunk_size (uint32) + raw PCM data
        - End marker: chunk_size = 0

        Args:
            text: Text to convert to speech

        Yields:
            bytes: Binary audio data chunks (PCM format)
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        import httpx

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/audio/speech/stream"

        payload = {
            "model": "tts-1",
            "voice": self.VOICE,
            "input": text,
            "language": self.TTS_LANGUAGE,
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST", api_url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk

    async def tts_websocket_session(self):
        """
        Create a persistent WebSocket session for real-time TTS streaming.

        Returns a TTSWebSocketSession that can be used to:
        1. Send text incrementally
        2. Flush to generate TTS
        3. Receive audio chunks as they're generated

        Usage:
            async with provider.tts_websocket_session() as session:
                await session.send_text("Hello")
                await session.send_text(" world!")
                async for chunk in session.flush():
                    # Process audio chunk
                    pass
        """
        import websockets

        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        # Convert http(s) to ws(s)
        ws_url = (
            self.API_URI.rstrip("/")
            .replace("http://", "ws://")
            .replace("https://", "wss://")
        )
        ws_url += "/v1/audio/speech/ws"

        return TTSWebSocketSession(
            url=ws_url,
            voice=self.VOICE,
            language=self.TTS_LANGUAGE,
        )

    async def generate_image(self, prompt: str) -> str:
        """
        Generate an image using ezLocalai.

        Args:
            prompt: Image generation prompt

        Returns:
            Base64 encoded image data
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/images/generations"

        payload = {
            "prompt": prompt,
            "model": "unsloth/FLUX.2-klein-4B-GGUF",
            "n": 1,
            "size": "1024x1024",
            "response_format": "url",
        }
        resp = await _run_sync(
            requests.post, api_url, headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        data = resp.json()

        logging.info(f"Image Generated for prompt: {prompt}")
        url = data["data"][0]["url"]

        # Download the image and return as base64
        dl_resp = await _run_sync(requests.get, url, timeout=60)
        image_data = dl_resp.content
        return base64.b64encode(image_data).decode("utf-8")

    async def edit_image(self, prompt: str, image: str) -> str:
        """
        Edit an image using a text prompt via ezLocalai.

        Args:
            prompt: Text description of the edit to apply
            image: Base64-encoded image, data URL, or HTTP URL of image to edit

        Returns:
            Base64 encoded edited image data
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/images/edits"

        payload = {
            "image": image,
            "prompt": prompt,
            "model": "unsloth/FLUX.2-klein-4B-GGUF",
            "n": 1,
            "size": "1024x1024",
            "response_format": "url",
        }
        resp = await _run_sync(
            requests.post, api_url, headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        data = resp.json()

        logging.info(f"Image Edited for prompt: {prompt}")
        url = data["data"][0]["url"]

        dl_resp = await _run_sync(requests.get, url, timeout=60)
        image_data = dl_resp.content
        return base64.b64encode(image_data).decode("utf-8")

    def _save_to_workspace(self, content: bytes, filename: str) -> str:
        """Save file content to the agent workspace and return the workspace URL."""
        file_path = os.path.join(self.WORKING_DIRECTORY, os.path.basename(filename))
        with open(file_path, "wb") as f:
            f.write(content)
        if self.output_url:
            return f"{self.output_url}{os.path.basename(filename)}"
        return file_path

    async def _resolve_image_to_base64(self, image_input: str) -> str:
        """Convert an image input (HTTP URL, data URL, or raw base64) to base64 string."""
        if not image_input:
            return image_input
        if image_input.startswith(("http://", "https://")):
            resp = await _run_sync(requests.get, image_input, timeout=30)
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode("utf-8")
        # data URLs and raw base64 are passed through as-is
        return image_input

    async def generate_video(
        self,
        prompt: str,
        size: str = "768x512",
        num_frames: int = 121,
        num_inference_steps: int = 40,
        guidance_scale: float = 4.0,
        frame_rate: int = 24,
        image: str = None,
        conditions: list = None,
    ) -> str:
        """
        Generate a video with audio using ezLocalai.

        Supports three modes:
        - Text-to-video: provide only prompt
        - Image-to-video: provide prompt + image
        - Video-to-video: provide prompt + conditions (list of frame dicts)

        Args:
            prompt: Text description of the video to generate
            size: Video resolution as "WIDTHxHEIGHT" (default: "768x512")
            num_frames: Number of frames to generate (default: 121)
            num_inference_steps: Denoising steps (default: 40)
            guidance_scale: CFG scale (default: 4.0)
            frame_rate: Output frame rate (default: 24)
            image: Base64-encoded image for image-to-video mode
            conditions: List of condition frame dicts for video-to-video mode

        Returns:
            URL to the generated video file
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/videos/generations"

        payload = {
            "prompt": prompt,
            "model": "unsloth/LTX-2.3-GGUF",
            "n": 1,
            "size": size,
            "num_frames": num_frames,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "frame_rate": frame_rate,
            "response_format": "url",
        }
        if image:
            payload["image"] = image
        if conditions:
            payload["conditions"] = conditions

        resp = await _run_sync(
            requests.post, api_url, headers=headers, json=payload, timeout=1800
        )
        resp.raise_for_status()
        data = resp.json()

        logging.info(f"Video Generated for prompt: {prompt}")
        first_item = data["data"][0]
        error = first_item.get("error")
        if error:
            raise Exception(f"Video generation failed: {error}")
        url = first_item.get("url")
        if not url:
            raise Exception("Video generation failed: no URL returned")
        # Download the video to agent workspace
        dl_resp = await _run_sync(requests.get, url, timeout=120)
        video_data = dl_resp.content
        filename = url.split("/")[-1] if "/" in url else f"{uuid.uuid4()}.mp4"
        return self._save_to_workspace(video_data, filename)

    def embeddings(self, input) -> np.ndarray:
        """
        Generate embeddings using ezLocalai.

        Args:
            input: Text to embed

        Returns:
            Embedding vector
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/embeddings"

        payload = {
            "input": input,
            "model": "bge-m3",
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    # Command methods that can be called by the AI
    async def generate_text_command(
        self,
        prompt: str,
        use_coding_model: str = "false",
    ) -> str:
        """
        Generate text using ezLocalai's local LLM. Use this when you need to generate text
        using the local AI model, especially for privacy-sensitive tasks or when low latency is needed.

        Args:
            prompt: The text prompt to send to the LLM
            use_coding_model: Set to "true" to use the more capable coding model

        Returns:
            Generated text response from ezLocalai
        """
        use_smartest = use_coding_model.lower() == "true"
        return await self.inference(prompt=prompt, use_smartest=use_smartest)

    async def generate_image_command(self, prompt: str) -> str:
        """
        Generate an image using ezLocalai's FLUX.2-klein-4B image generation.
        Use this when you need to create images locally without external API calls.

        Args:
            prompt: Description of the image to generate

        Returns:
            Base64 image data with markdown display
        """
        from Conversations import Conversations

        c = Conversations(
            conversation_name=self.conversation_name,
            user=self.user,
            conversation_id=self.conversation_id,
        )

        c.log_interaction(
            role=self.agent_name,
            message="[SUBACTIVITY] Generating image...",
        )
        image_b64 = await self.generate_image(prompt=prompt)

        # Vision verification loop: use the LLM's vision to check if the
        # generated image matches the prompt, and edit if it doesn't.
        max_edits = 3
        for attempt in range(max_edits):
            data_url = f"data:image/png;base64,{image_b64}"
            c.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY] Reviewing generated image (attempt {attempt + 1}/{max_edits})...",
            )
            verification_prompt = (
                f"You are an image QA reviewer. The user requested this image:\n\n"
                f'"{prompt}"\n\n'
                f"Look at the generated image carefully. Does it match the request? "
                f"Pay close attention to text content, capitalization, colors, layout, "
                f"and any specific details mentioned in the request.\n"
                f"If it matches well enough, respond with exactly: PASS\n"
                f"If it does NOT match, respond with a brief description of what "
                f"specifically needs to change (do NOT say PASS). Focus only on the "
                f"most important differences from the request."
            )
            try:
                verdict = await self.inference(
                    prompt=verification_prompt,
                    images=[data_url],
                )
            except Exception as e:
                logging.warning(
                    f"[generate_image_command] Vision verification failed: {e}"
                )
                c.log_interaction(
                    role=self.agent_name,
                    message="[SUBACTIVITY] Vision review unavailable, using image as-is.",
                )
                break

            verdict_stripped = verdict.strip()
            # Check for PASS anywhere in a short response to handle
            # variations like "PASS." or "PASS - looks good"
            verdict_upper = verdict_stripped.upper()
            if verdict_upper.startswith("PASS") or (
                len(verdict_stripped) < 50 and "PASS" in verdict_upper
            ):
                logging.info(
                    f"[generate_image_command] Image passed vision verification "
                    f"on attempt {attempt + 1}."
                )
                c.log_interaction(
                    role=self.agent_name,
                    message="[SUBACTIVITY] Image passed quality review.",
                )
                break

            logging.info(
                f"[generate_image_command] Vision verification attempt "
                f"{attempt + 1}/{max_edits}: needs edits — "
                f"{verdict_stripped[:200]}"
            )
            c.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY] Image needs edits: {verdict_stripped[:300]}",
            )

            # Edit the image with the feedback
            edit_prompt = (
                f"Original request: {prompt}\n" f"Required changes: {verdict_stripped}"
            )
            c.log_interaction(
                role=self.agent_name,
                message="[SUBACTIVITY] Editing image to address feedback...",
            )
            try:
                image_b64 = await self.edit_image(
                    prompt=edit_prompt,
                    image=image_b64,
                )
            except Exception as e:
                logging.warning(
                    f"[generate_image_command] Image edit failed on attempt "
                    f"{attempt + 1}: {e}"
                )
                c.log_interaction(
                    role=self.agent_name,
                    message="[SUBACTIVITY] Image edit failed, using current image.",
                )
                break

        image_data = base64.b64decode(image_b64)
        filename = f"{uuid.uuid4()}.png"
        workspace_url = self._save_to_workspace(image_data, filename)
        return f"Generated image: ![{prompt[:50]}]({workspace_url})"

    async def edit_image_command(self, prompt: str, image_url: str) -> str:
        """
        Edit an image using a text prompt with ezLocalai's FLUX.2-klein-4B model.
        Use this when you need to modify or transform an existing image based on
        a text description. The model takes the input image and applies the
        described transformation.

        Args:
            prompt: Description of the edit to apply to the image
            image_url: URL or base64-encoded data of the image to edit

        Returns:
            Base64 edited image data with markdown display
        """
        image_b64 = await self.edit_image(prompt=prompt, image=image_url)
        image_data = base64.b64decode(image_b64)
        filename = f"{uuid.uuid4()}.png"
        workspace_url = self._save_to_workspace(image_data, filename)
        return f"Edited image: ![{prompt[:50]}]({workspace_url})"

    async def generate_video_command(
        self,
        prompt: str,
        size: str = "768x512",
        num_frames: str = "121",
        num_inference_steps: str = "40",
    ) -> str:
        """
        Generate a video with synchronized audio from a text prompt using ezLocalai's
        LTX-2.3 model. Use this when you need to create videos locally from text
        descriptions. Produces MP4 files with both video and audio tracks.

        Args:
            prompt: Description of the video to generate
            size: Video resolution as WIDTHxHEIGHT (default: 768x512)
            num_frames: Number of frames to generate (default: 121)
            num_inference_steps: Number of denoising steps, higher is better quality but slower (default: 40)

        Returns:
            URL to the generated video
        """
        url = await self.generate_video(
            prompt=prompt,
            size=size,
            num_frames=int(num_frames),
            num_inference_steps=int(num_inference_steps),
        )
        return f"Generated video: [{prompt[:50]}]({url})"

    async def image_to_video_command(
        self,
        prompt: str,
        image_url: str,
        size: str = "768x512",
        num_frames: str = "121",
        num_inference_steps: str = "40",
    ) -> str:
        """
        Generate a video from an image and text prompt using ezLocalai's LTX-2.3 model.
        The provided image is used as the first frame and the video is generated to
        match the text description. Produces MP4 files with video and audio tracks.

        Args:
            prompt: Description of what should happen in the video
            image_url: URL or base64-encoded data of the starting image
            size: Video resolution as WIDTHxHEIGHT (default: 768x512)
            num_frames: Number of frames to generate (default: 121)
            num_inference_steps: Number of denoising steps (default: 40)

        Returns:
            URL to the generated video
        """
        image_b64 = await self._resolve_image_to_base64(image_url)
        url = await self.generate_video(
            prompt=prompt,
            size=size,
            num_frames=int(num_frames),
            num_inference_steps=int(num_inference_steps),
            image=image_b64,
        )
        return f"Generated video from image: [{prompt[:50]}]({url})"

    async def video_to_video_command(
        self,
        prompt: str,
        start_frame_url: str,
        end_frame_url: str,
        size: str = "768x512",
        num_frames: str = "121",
        num_inference_steps: str = "40",
    ) -> str:
        """
        Generate a video conditioned on start and end frames using ezLocalai's LTX-2.3
        model. Provide a start frame and end frame, and the model generates a smooth
        video transition between them guided by the text prompt. Useful for style
        transfer, interpolation, and video-to-video transformation.

        Args:
            prompt: Description of the video transition or transformation
            start_frame_url: URL or base64-encoded data of the starting frame
            end_frame_url: URL or base64-encoded data of the ending frame
            size: Video resolution as WIDTHxHEIGHT (default: 768x512)
            num_frames: Number of frames to generate (default: 121)
            num_inference_steps: Number of denoising steps (default: 40)

        Returns:
            URL to the generated video
        """
        start_b64 = await self._resolve_image_to_base64(start_frame_url)
        end_b64 = await self._resolve_image_to_base64(end_frame_url)
        conditions = [
            {"image": start_b64, "index": 0, "strength": 1.0},
            {"image": end_b64, "index": -1, "strength": 1.0},
        ]
        url = await self.generate_video(
            prompt=prompt,
            size=size,
            num_frames=int(num_frames),
            num_inference_steps=int(num_inference_steps),
            conditions=conditions,
        )
        return f"Generated video from frames: [{prompt[:50]}]({url})"

    async def text_to_speech_command(self, text: str) -> str:
        """
        Convert text to speech using ezLocalai's TTS capabilities.
        Use this when you need to generate audio from text locally.

        Args:
            text: The text to convert to speech

        Returns:
            Audio player HTML or URL to the generated audio
        """
        audio_base64 = await self.text_to_speech(text=text)
        return f'<audio controls><source src="data:audio/wav;base64,{audio_base64}" type="audio/wav"></audio>'

    async def transcribe_audio_command(self, audio_url: str) -> str:
        """
        Transcribe audio to text using ezLocalai's speech recognition.
        Use this when you need to convert audio to text locally.

        Args:
            audio_url: URL or path to the audio file to transcribe

        Returns:
            Transcribed text from the audio
        """
        return await self.transcribe_audio(audio_path=audio_url)


class TTSWebSocketSession:
    """
    A persistent WebSocket session for real-time TTS streaming.

    This keeps the connection open between text chunks, reducing latency
    by eliminating HTTP connection overhead for each TTS request.
    """

    def __init__(self, url: str, voice: str = "default", language: str = "en"):
        self.url = url
        self.voice = voice
        self.language = language
        self.ws = None
        self.header_received = False

    async def __aenter__(self):
        import websockets

        self.ws = await websockets.connect(self.url)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.ws:
            try:
                # Signal done
                await self.ws.send('{"done": true}')
                # Drain any remaining audio
                try:
                    while True:
                        data = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                        if not data or data == b"":
                            break
                except asyncio.TimeoutError:
                    pass
            except:
                pass
            await self.ws.close()

    async def send_text(self, text: str, flush: bool = False):
        """
        Send text to the TTS session.

        Args:
            text: Text to add to the buffer
            flush: If True, trigger TTS generation for accumulated text
        """
        if self.ws:
            import json

            await self.ws.send(
                json.dumps(
                    {
                        "text": text,
                        "voice": self.voice,
                        "language": self.language,
                        "flush": flush,
                    }
                )
            )

    async def flush(self):
        """
        Flush the text buffer and yield audio chunks.

        Yields:
            bytes: Audio data chunks
        """
        if not self.ws:
            return

        import json

        await self.ws.send(
            json.dumps({"flush": True, "voice": self.voice, "language": self.language})
        )

        # Receive audio chunks until we get empty bytes
        while True:
            try:
                data = await self.ws.recv()
                if isinstance(data, bytes):
                    if len(data) == 0:
                        break
                    yield data
            except:
                break
