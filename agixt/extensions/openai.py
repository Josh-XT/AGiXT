"""
OpenAI AI Provider Extension for AGiXT

This extension provides AI inference capabilities using OpenAI's API,
supporting text generation, text-to-speech, image generation, transcription, and translation.

Get your OpenAI API key at: https://platform.openai.com/account/api-keys

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import base64
import json
import logging
import random
import time
import uuid

import requests
import numpy as np
from Extensions import Extensions
from Globals import getenv


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


class openai(Extensions):
    """
    OpenAI AI Provider - Cloud AI inference supporting LLM, TTS, image generation, and transcription.

    Get your API key at https://platform.openai.com/account/api-keys
    """

    CATEGORY = "AI Provider"
    friendly_name = "OpenAI"

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
        OPENAI_API_KEY: str = "",
        OPENAI_API_URI: str = "https://api.openai.com/v1",
        OPENAI_AI_MODEL: str = "gpt-4o",
        OPENAI_VISION_MODEL: str = "gpt-4o",
        OPENAI_CODING_MODEL: str = "gpt-4o",
        OPENAI_MAX_TOKENS: int = 128000,
        OPENAI_TEMPERATURE: float = 0.7,
        OPENAI_TOP_P: float = 0.9,
        OPENAI_VOICE: str = "alloy",
        OPENAI_TRANSCRIPTION_MODEL: str = "whisper-1",
        OPENAI_WAIT_BETWEEN_REQUESTS: int = 1,
        OPENAI_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        # Get from parameter or environment
        if not OPENAI_API_KEY:
            OPENAI_API_KEY = getenv("OPENAI_API_KEY", "")
        if not OPENAI_API_URI or OPENAI_API_URI == "https://api.openai.com/v1":
            OPENAI_API_URI = getenv(
                "OPENAI_API_URI", getenv("OPENAI_BASE_URI", "https://api.openai.com/v1")
            )
        if not OPENAI_AI_MODEL or OPENAI_AI_MODEL == "gpt-4o":
            OPENAI_AI_MODEL = getenv("OPENAI_MODEL", "gpt-4o")

        self.OPENAI_API_KEY = OPENAI_API_KEY
        self.API_URI = OPENAI_API_URI if OPENAI_API_URI else "https://api.openai.com/v1"
        self.AI_MODEL = OPENAI_AI_MODEL if OPENAI_AI_MODEL else "gpt-4o"
        self.VISION_MODEL = OPENAI_VISION_MODEL if OPENAI_VISION_MODEL else "gpt-4o"
        self.CODING_MODEL = OPENAI_CODING_MODEL if OPENAI_CODING_MODEL else "gpt-4o"
        self.MAX_TOKENS = int(OPENAI_MAX_TOKENS) if OPENAI_MAX_TOKENS else 128000
        self.AI_TEMPERATURE = float(OPENAI_TEMPERATURE) if OPENAI_TEMPERATURE else 0.7
        self.AI_TOP_P = float(OPENAI_TOP_P) if OPENAI_TOP_P else 0.9
        self.VOICE = OPENAI_VOICE if OPENAI_VOICE else "alloy"
        self.TRANSCRIPTION_MODEL = (
            OPENAI_TRANSCRIPTION_MODEL if OPENAI_TRANSCRIPTION_MODEL else "whisper-1"
        )
        self.WAIT_BETWEEN_REQUESTS = (
            int(OPENAI_WAIT_BETWEEN_REQUESTS) if OPENAI_WAIT_BETWEEN_REQUESTS else 1
        )
        self.WAIT_AFTER_FAILURE = (
            int(OPENAI_WAIT_AFTER_FAILURE) if OPENAI_WAIT_AFTER_FAILURE else 3
        )

        self.FAILURES = []
        self.failure_count = 0

        # Commands that allow the AI to use this provider directly
        self.commands = {
            "Generate Response with OpenAI": self.generate_response_command,
            "Text to Speech with OpenAI": self.text_to_speech_command,
            "Generate Image with OpenAI": self.generate_image_command,
            "Transcribe Audio with OpenAI": self.transcribe_audio_command,
            "Translate Audio with OpenAI": self.translate_audio_command,
            "Generate Embeddings with OpenAI": self.generate_embeddings_command,
        }

        # Check if configured
        self.configured = bool(
            self.OPENAI_API_KEY
            and self.OPENAI_API_KEY != ""
            and self.OPENAI_API_KEY != "YOUR_OPENAI_API_KEY"
        )

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient", None)

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

    def _get_headers(self):
        """Get request headers for OpenAI API calls"""
        return {
            "Authorization": f"Bearer {self.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

    def _get_base_url(self):
        """Get the base URL for API calls"""
        uri = self.API_URI if self.API_URI else "https://api.openai.com/v1"
        return uri.rstrip("/")

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        """
        Generate text using OpenAI LLM.

        Args:
            prompt: The input prompt
            tokens: Input token count (for budgeting)
            images: List of image URLs or paths for vision tasks
            stream: Whether to stream the response
            use_smartest: Use the coding/smartest model

        Returns:
            Generated text response or stream object
        """
        if not self.configured:
            raise Exception("OpenAI provider not configured - missing API key")

        model = self.CODING_MODEL if use_smartest else self.AI_MODEL
        if images:
            model = self.VISION_MODEL

        headers = self._get_headers()
        api_url = self._get_base_url() + "/chat/completions"

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

        if self.WAIT_BETWEEN_REQUESTS > 0:
            time.sleep(self.WAIT_BETWEEN_REQUESTS)

        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": float(self.AI_TEMPERATURE),
                "top_p": float(self.AI_TOP_P),
                "n": 1,
                "stream": stream,
            }

            if stream:
                resp = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=300,
                )
                resp.raise_for_status()
                return parse_sse_stream(resp)

            resp = requests.post(api_url, headers=headers, json=payload, timeout=300)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except Exception as e:
            self.failure_count += 1
            logging.error(f"OpenAI API Error: {e}")

            if "," in self.API_URI:
                self.rotate_uri()

            if self.failure_count >= 3:
                raise Exception(f"OpenAI API Error: Too many failures. {e}")

            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)

            return await self.inference(
                prompt=prompt,
                tokens=tokens,
                images=images,
                stream=stream,
                use_smartest=use_smartest,
            )

    async def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribe audio to text using OpenAI Whisper.

        Args:
            audio_path: Path to the audio file

        Returns:
            Transcribed text
        """
        if not self.configured:
            raise Exception("OpenAI provider not configured")

        headers = {"Authorization": f"Bearer {self.OPENAI_API_KEY}"}
        api_url = self._get_base_url() + "/audio/transcriptions"

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
        Translate audio to English text using OpenAI Whisper.

        Args:
            audio_path: Path to the audio file

        Returns:
            Translated text in English
        """
        if not self.configured:
            raise Exception("OpenAI provider not configured")

        headers = {"Authorization": f"Bearer {self.OPENAI_API_KEY}"}
        api_url = self._get_base_url() + "/audio/translations"

        with open(audio_path, "rb") as audio_file:
            files = {"file": audio_file}
            data = {"model": self.TRANSCRIPTION_MODEL}
            resp = requests.post(
                api_url, headers=headers, files=files, data=data, timeout=120
            )
            resp.raise_for_status()
            return resp.json().get("text", "")

    async def text_to_speech(self, text: str) -> bytes:
        """
        Convert text to speech using OpenAI TTS.

        Args:
            text: Text to convert to speech

        Returns:
            Audio content as bytes
        """
        if not self.configured:
            raise Exception("OpenAI provider not configured")

        headers = self._get_headers()
        api_url = self._get_base_url() + "/audio/speech"

        payload = {
            "model": "tts-1",
            "voice": self.VOICE,
            "input": text,
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.content

    async def generate_image(self, prompt: str) -> str:
        """
        Generate an image from a text prompt using DALL-E.

        Args:
            prompt: Text description of the image to generate

        Returns:
            Base64 encoded image data
        """
        if not self.configured:
            raise Exception("OpenAI provider not configured")

        headers = self._get_headers()
        api_url = self._get_base_url() + "/images/generations"

        payload = {
            "prompt": prompt,
            "model": "dall-e-3",
            "n": 1,
            "size": "1024x1024",
            "response_format": "url",
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        logging.info(f"[OpenAI] Image generated for prompt: {prompt}")
        url = data["data"][0]["url"]

        # Download the image and return as base64
        image_data = requests.get(url).content
        return base64.b64encode(image_data).decode("utf-8")

    def embeddings(self, input_text) -> np.ndarray:
        """
        Generate embeddings for text using OpenAI.

        Args:
            input_text: Text to generate embeddings for

        Returns:
            Embedding vector as numpy array
        """
        if not self.configured:
            raise Exception("OpenAI provider not configured")

        headers = self._get_headers()
        api_url = self._get_base_url() + "/embeddings"

        payload = {
            "input": input_text,
            "model": "text-embedding-3-small",
        }
        resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    # Command methods for AI to use this provider directly
    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using OpenAI's language model.

        Args:
            prompt: The prompt to send to OpenAI

        Returns:
            The generated text response from OpenAI
        """
        return await self.inference(prompt=prompt)

    async def text_to_speech_command(self, text: str) -> str:
        """
        Convert text to speech using OpenAI TTS.

        Args:
            text: The text to convert to speech

        Returns:
            URL to the generated audio file
        """
        audio_bytes = await self.text_to_speech(text=text)
        filename = f"{uuid.uuid4()}.mp3"
        audio_path = f"./WORKSPACE/{filename}"
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        agixt_uri = getenv("AGIXT_URI")
        return f"{agixt_uri}/outputs/{filename}"

    async def generate_image_command(self, prompt: str) -> str:
        """
        Generate an image using OpenAI DALL-E.

        Args:
            prompt: Text description of the image to generate

        Returns:
            URL to the generated image
        """
        return await self.generate_image(prompt=prompt)

    async def transcribe_audio_command(self, audio_url: str) -> str:
        """
        Transcribe audio to text using OpenAI Whisper.

        Args:
            audio_url: URL to the audio file to transcribe

        Returns:
            The transcribed text
        """
        import tempfile

        audio_data = requests.get(audio_url).content
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        result = await self.transcribe_audio(audio_path=temp_path)
        import os

        os.unlink(temp_path)
        return result

    async def translate_audio_command(self, audio_url: str) -> str:
        """
        Translate audio to English text using OpenAI Whisper.

        Args:
            audio_url: URL to the audio file to translate

        Returns:
            The translated text in English
        """
        import tempfile

        audio_data = requests.get(audio_url).content
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        result = await self.translate_audio(audio_path=temp_path)
        import os

        os.unlink(temp_path)
        return result

    async def generate_embeddings_command(self, text: str) -> str:
        """
        Generate text embeddings using OpenAI.

        Args:
            text: The text to generate embeddings for

        Returns:
            The embedding vector as a JSON string
        """
        import json

        embeddings = self.embeddings(input_text=text)
        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()
        return json.dumps(embeddings)
