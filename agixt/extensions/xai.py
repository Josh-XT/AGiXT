"""
xAI AI Provider Extension for AGiXT

This extension provides AI inference capabilities using xAI's Grok API,
supporting text generation and vision tasks.

Get your xAI API key at: https://docs.x.ai/docs#getting-started

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


class xai(Extensions):
    """
    xAI AI Provider - Grok models for LLM inference and vision tasks.

    Get your API key at https://docs.x.ai/docs#getting-started
    """

    CATEGORY = "AI Provider"
    friendly_name = "xAI Grok"

    # Services this AI provider supports
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        XAI_API_KEY: str = "",
        XAI_API_URI: str = "https://api.x.ai/v1/",
        XAI_AI_MODEL: str = "grok-beta",
        XAI_MAX_TOKENS: int = 128000,
        XAI_TEMPERATURE: float = 0.7,
        XAI_TOP_P: float = 0.7,
        XAI_WAIT_BETWEEN_REQUESTS: int = 1,
        XAI_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        # Get from parameter or environment
        if not XAI_API_KEY:
            XAI_API_KEY = getenv("XAI_API_KEY", "")
        if not XAI_AI_MODEL or XAI_AI_MODEL == "grok-beta":
            XAI_AI_MODEL = getenv("XAI_MODEL", "grok-beta")

        self.XAI_API_KEY = XAI_API_KEY
        self.API_URI = XAI_API_URI if XAI_API_URI else "https://api.x.ai/v1/"
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        self.AI_MODEL = XAI_AI_MODEL if XAI_AI_MODEL else "grok-beta"
        self.MAX_TOKENS = int(XAI_MAX_TOKENS) if XAI_MAX_TOKENS else 128000
        self.AI_TEMPERATURE = float(XAI_TEMPERATURE) if XAI_TEMPERATURE else 0.7
        self.AI_TOP_P = float(XAI_TOP_P) if XAI_TOP_P else 0.7
        self.WAIT_BETWEEN_REQUESTS = (
            int(XAI_WAIT_BETWEEN_REQUESTS) if XAI_WAIT_BETWEEN_REQUESTS else 1
        )
        self.WAIT_AFTER_FAILURE = (
            int(XAI_WAIT_AFTER_FAILURE) if XAI_WAIT_AFTER_FAILURE else 3
        )

        self.FAILURES = []
        self.failure_count = 0

        # Check if configured
        self.configured = bool(
            self.XAI_API_KEY
            and self.XAI_API_KEY != ""
            and self.XAI_API_KEY != "YOUR_XAI_API_KEY"
        )

        # Commands that allow the AI to use this provider directly
        self.commands = {
            "Generate Response with xAI": self.generate_response_command,
        }

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient", None)

    @staticmethod
    def services():
        """Return list of services this provider supports"""
        return ["llm", "vision"]

    def get_max_tokens(self):
        """Return the maximum token limit for this provider"""
        return self.MAX_TOKENS

    def is_configured(self):
        """Check if this provider is properly configured"""
        return self.configured

    def _get_headers(self):
        """Get request headers for xAI API calls"""
        return {
            "Authorization": f"Bearer {self.XAI_API_KEY}",
            "Content-Type": "application/json",
        }

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        """
        Generate text using xAI Grok.

        Args:
            prompt: The input prompt
            tokens: Input token count (for budgeting)
            images: List of image URLs or paths for vision tasks
            stream: Whether to stream the response
            use_smartest: Use the smartest model

        Returns:
            Generated text response or stream object
        """
        if not self.configured:
            raise Exception("xAI provider not configured - missing API key")

        headers = self._get_headers()
        api_url = self.API_URI.rstrip("/") + "/chat/completions"

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
            self.failure_count += 1
            logging.error(f"xAI API Error: {e}")

            if self.failure_count >= 3:
                raise Exception(f"xAI API Error: Too many failures. {e}")

            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)

            return await self.inference(
                prompt=prompt,
                tokens=tokens,
                images=images,
                stream=stream,
                use_smartest=use_smartest,
            )

    # Command methods for AI to use this provider directly
    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using xAI Grok.

        Args:
            prompt: The prompt to send to Grok

        Returns:
            The generated text response from Grok
        """
        return await self.inference(prompt=prompt)
