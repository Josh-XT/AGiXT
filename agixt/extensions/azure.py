"""
Azure OpenAI AI Provider Extension for AGiXT

This extension provides AI inference capabilities using Azure OpenAI API.
Learn more at https://learn.microsoft.com/en-us/azure/ai-services/openai/

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


class azure(Extensions):
    """
    Azure OpenAI AI Provider - Azure-hosted OpenAI models for LLM inference and vision.

    Learn more at https://learn.microsoft.com/en-us/azure/ai-services/openai/
    """

    CATEGORY = "AI Provider"
    friendly_name = "Azure OpenAI"
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        AZURE_API_KEY: str = "",
        AZURE_OPENAI_ENDPOINT: str = "https://your-endpoint.openai.azure.com",
        AZURE_DEPLOYMENT_NAME: str = "gpt-4o",
        AZURE_TEMPERATURE: float = 0.7,
        AZURE_TOP_P: float = 0.7,
        AZURE_MAX_TOKENS: int = 120000,
        AZURE_WAIT_BETWEEN_REQUESTS: int = 1,
        AZURE_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        if not AZURE_API_KEY:
            AZURE_API_KEY = getenv("AZURE_API_KEY", "")
        if (
            not AZURE_OPENAI_ENDPOINT
            or AZURE_OPENAI_ENDPOINT == "https://your-endpoint.openai.azure.com"
        ):
            AZURE_OPENAI_ENDPOINT = getenv(
                "AZURE_OPENAI_ENDPOINT", "https://your-endpoint.openai.azure.com"
            )

        self.AZURE_API_KEY = AZURE_API_KEY
        self.AZURE_OPENAI_ENDPOINT = AZURE_OPENAI_ENDPOINT
        self.AI_MODEL = AZURE_DEPLOYMENT_NAME if AZURE_DEPLOYMENT_NAME else "gpt-4o"
        self.AI_TEMPERATURE = float(AZURE_TEMPERATURE) if AZURE_TEMPERATURE else 0.7
        self.AI_TOP_P = float(AZURE_TOP_P) if AZURE_TOP_P else 0.7
        self.MAX_TOKENS = int(AZURE_MAX_TOKENS) if AZURE_MAX_TOKENS else 120000
        self.WAIT_AFTER_FAILURE = (
            int(AZURE_WAIT_AFTER_FAILURE) if AZURE_WAIT_AFTER_FAILURE else 3
        )
        self.WAIT_BETWEEN_REQUESTS = (
            int(AZURE_WAIT_BETWEEN_REQUESTS) if AZURE_WAIT_BETWEEN_REQUESTS else 1
        )
        self.failures = 0

        self.configured = bool(
            self.AZURE_API_KEY
            and self.AZURE_API_KEY != ""
            and self.AZURE_OPENAI_ENDPOINT != "https://your-endpoint.openai.azure.com"
        )

        self.commands = {
            "Generate Response with Azure OpenAI": self.generate_response_command,
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
            raise Exception("Azure OpenAI provider not configured")

        base_url = self.AZURE_OPENAI_ENDPOINT.rstrip("/")
        api_url = f"{base_url}/openai/deployments/{self.AI_MODEL}/chat/completions?api-version=2024-02-01"

        headers = {
            "api-key": self.AZURE_API_KEY,
            "Content-Type": "application/json",
        }

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
            logging.warning(f"Azure OpenAI API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"Azure OpenAI API Error: Too many failures. {e}")
            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, stream=stream
            )

    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using Azure OpenAI.

        Args:
            prompt: The prompt to send to Azure OpenAI

        Returns:
            The generated text response
        """
        return await self.inference(prompt=prompt)
