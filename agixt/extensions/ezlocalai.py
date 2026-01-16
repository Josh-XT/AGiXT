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
import random
import re
import uuid
import requests
import numpy as np
from Extensions import Extensions
from Globals import getenv
import asyncio


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
    ]

    def __init__(
        self,
        EZLOCALAI_API_URI: str = "",
        EZLOCALAI_API_KEY: str = "",
        EZLOCALAI_AI_MODEL: str = "unsloth/Qwen3-4B-Instruct-2507-GGUF",
        EZLOCALAI_CODING_MODEL: str = "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF",
        EZLOCALAI_MAX_TOKENS: int = 32000,
        EZLOCALAI_TEMPERATURE: float = 1.33,
        EZLOCALAI_TOP_P: float = 0.95,
        EZLOCALAI_VOICE: str = "HAL9000",
        EZLOCALAI_LANGUAGE: str = "en",
        EZLOCALAI_TRANSCRIPTION_MODEL: str = "base",
        **kwargs,
    ):
        # Extension base initialization
        self.agent_name = kwargs.get("agent_name", "AGiXT")
        self.ApiClient = kwargs.get("ApiClient", None)

        # Get URI from parameter or environment
        if not EZLOCALAI_API_URI:
            EZLOCALAI_API_URI = getenv("EZLOCALAI_API_URI", getenv("EZLOCALAI_URI", ""))

        # Get API key from parameter or environment
        if not EZLOCALAI_API_KEY:
            EZLOCALAI_API_KEY = getenv("EZLOCALAI_API_KEY", "")

        # Normalize URI
        if EZLOCALAI_API_URI and not EZLOCALAI_API_URI.endswith("/"):
            EZLOCALAI_API_URI += "/"
        if EZLOCALAI_API_URI and "v1/" not in EZLOCALAI_API_URI:
            EZLOCALAI_API_URI += "v1/"

        self.API_URI = EZLOCALAI_API_URI
        self.EZLOCALAI_API_KEY = EZLOCALAI_API_KEY

        # Check if this provider is configured (has a URI set)
        self.configured = bool(self.API_URI)

        # Model configuration
        self.AI_MODEL = EZLOCALAI_AI_MODEL if EZLOCALAI_AI_MODEL else "default"
        self.CODING_MODEL = (
            EZLOCALAI_CODING_MODEL
            if EZLOCALAI_CODING_MODEL
            else "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF"
        )
        self.MAX_TOKENS = int(EZLOCALAI_MAX_TOKENS) if EZLOCALAI_MAX_TOKENS else 32000
        self.AI_TEMPERATURE = (
            float(EZLOCALAI_TEMPERATURE) if EZLOCALAI_TEMPERATURE else 1.33
        )
        self.AI_TOP_P = float(EZLOCALAI_TOP_P) if EZLOCALAI_TOP_P else 0.95

        # TTS configuration
        self.VOICE = EZLOCALAI_VOICE if EZLOCALAI_VOICE else "HAL9000"
        self.TTS_LANGUAGE = EZLOCALAI_LANGUAGE if EZLOCALAI_LANGUAGE else "en"
        if len(self.TTS_LANGUAGE) > 2:
            self.TTS_LANGUAGE = self.TTS_LANGUAGE[:2].lower()

        # Transcription configuration
        self.TRANSCRIPTION_MODEL = (
            EZLOCALAI_TRANSCRIPTION_MODEL if EZLOCALAI_TRANSCRIPTION_MODEL else "base"
        )

        # Output URL for generated files
        self.OUTPUT_URL = (
            self.API_URI.replace("/v1/", "/outputs/") if self.API_URI else ""
        )

        # Failure tracking for rotation
        self.FAILURES = []
        self.failure_count = 0

        # Commands for AI Provider extensions - these allow the AI to explicitly choose this provider
        self.commands = {
            "Generate Text with ezLocalai": self.generate_text_command,
            "Generate Image with ezLocalai": self.generate_image_command,
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
                "max_tokens": int(self.MAX_TOKENS),
                "temperature": float(self.AI_TEMPERATURE),
                "top_p": float(self.AI_TOP_P),
                "n": 1,
                "stream": stream,
            }

            api_url = self.API_URI.rstrip("/") + "/chat/completions"

            if stream:
                # Return a generator for streaming with OpenAI SDK-like interface
                resp = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=300,
                )
                resp.raise_for_status()
                return parse_sse_stream(resp)

            resp = requests.post(
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

    async def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe audio to text using ezLocalai.

        Args:
            audio_path: Path to the audio file

        Returns:
            Transcribed text
        """
        if not self.configured:
            raise Exception("ezLocalai provider not configured")

        api_key = self.EZLOCALAI_API_KEY if self.EZLOCALAI_API_KEY else "none"
        headers = {"Authorization": f"Bearer {api_key}"}
        api_url = self.API_URI.rstrip("/") + "/audio/transcriptions"

        with open(audio_path, "rb") as audio_file:
            files = {"file": audio_file}
            data = {"model": self.TRANSCRIPTION_MODEL}
            resp = requests.post(
                api_url, headers=headers, files=files, data=data, timeout=120
            )
            resp.raise_for_status()
            return resp.json().get("text", "")

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
            resp = requests.post(
                api_url, headers=headers, files=files, data=data, timeout=120
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
        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
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
            "model": "stabilityai/sdxl-turbo",
            "n": 1,
            "size": "512x512",
            "response_format": "url",
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        logging.info(f"Image Generated for prompt: {prompt}")
        url = data["data"][0]["url"]

        # Download the image and return as base64
        image_data = requests.get(url).content
        return base64.b64encode(image_data).decode("utf-8")
        return f"{agixt_uri}/outputs/{filename}"

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
        Generate an image using ezLocalai's image generation capabilities.
        Use this when you need to create images locally without external API calls.

        Args:
            prompt: Description of the image to generate

        Returns:
            URL to the generated image
        """
        url = await self.generate_image(prompt=prompt)
        return f"Generated image: ![{prompt[:50]}]({url})"

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
