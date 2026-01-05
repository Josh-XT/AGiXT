"""
Deepseek AI Provider Extension for AGiXT

This extension provides AI inference capabilities using the Deepseek API.
Get your API key at https://platform.deepseek.com/

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import base64
import json
import logging
import time
import requests

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


class deepseek(Extensions):
    """
    Deepseek AI Provider - Deepseek models for LLM inference and vision.

    Get your API key at https://platform.deepseek.com/
    """

    CATEGORY = "AI Provider"
    friendly_name = "DeepSeek"
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        DEEPSEEK_API_KEY: str = "",
        DEEPSEEK_MODEL: str = "deepseek-chat",
        DEEPSEEK_API_URI: str = "https://api.deepseek.com/",
        DEEPSEEK_MAX_TOKENS: int = 64000,
        DEEPSEEK_TEMPERATURE: float = 0.1,
        DEEPSEEK_TOP_P: float = 0.95,
        DEEPSEEK_WAIT_BETWEEN_REQUESTS: int = 0,
        DEEPSEEK_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        if not DEEPSEEK_API_KEY:
            DEEPSEEK_API_KEY = getenv("DEEPSEEK_API_KEY", "")

        self.DEEPSEEK_API_KEY = DEEPSEEK_API_KEY
        self.AI_MODEL = DEEPSEEK_MODEL if DEEPSEEK_MODEL else "deepseek-chat"
        self.API_URI = (
            DEEPSEEK_API_URI if DEEPSEEK_API_URI else "https://api.deepseek.com/"
        )
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        self.MAX_TOKENS = int(DEEPSEEK_MAX_TOKENS) if DEEPSEEK_MAX_TOKENS else 64000
        self.AI_TEMPERATURE = (
            float(DEEPSEEK_TEMPERATURE) if DEEPSEEK_TEMPERATURE else 0.1
        )
        self.AI_TOP_P = float(DEEPSEEK_TOP_P) if DEEPSEEK_TOP_P else 0.95
        self.WAIT_BETWEEN_REQUESTS = (
            int(DEEPSEEK_WAIT_BETWEEN_REQUESTS) if DEEPSEEK_WAIT_BETWEEN_REQUESTS else 0
        )
        self.WAIT_AFTER_FAILURE = (
            int(DEEPSEEK_WAIT_AFTER_FAILURE) if DEEPSEEK_WAIT_AFTER_FAILURE else 3
        )
        self.failures = 0

        self.configured = bool(self.DEEPSEEK_API_KEY and self.DEEPSEEK_API_KEY != "")

        self.commands = {
            "Generate Response with Deepseek": self.generate_response_command,
        }

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient", None)

    @staticmethod
    def services():
        return ["llm", "vision"]

    def get_max_tokens(self):
        return self.MAX_TOKENS

    def is_configured(self):
        return self.configured

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        if not self.configured:
            raise Exception("Deepseek provider not configured")

        headers = {
            "Authorization": f"Bearer {self.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        api_url = self.API_URI.rstrip("/") + "/chat/completions"

        messages = []
        if images:
            content = [{"type": "text", "text": prompt}]
            for image in images:
                if image.startswith("http"):
                    content.append({"type": "image_url", "image_url": {"url": image}})
                else:
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
                "model": self.AI_MODEL,
                "messages": messages,
                "temperature": float(self.AI_TEMPERATURE),
                "max_tokens": 4096,
                "top_p": float(self.AI_TOP_P),
                "n": 1,
                "stream": stream,
            }

            if stream:
                resp = requests.post(
                    api_url, headers=headers, json=payload, stream=True, timeout=300
                )
                resp.raise_for_status()
                return parse_sse_stream(resp)

            resp = requests.post(api_url, headers=headers, json=payload, timeout=300)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logging.info(f"Deepseek API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"Deepseek API Error: Too many failures. {e}")
            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, stream=stream
            )

    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using Deepseek.

        Args:
            prompt: The prompt to send to Deepseek

        Returns:
            The generated text response
        """
        return await self.inference(prompt=prompt)
