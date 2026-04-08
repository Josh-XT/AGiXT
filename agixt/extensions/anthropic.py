"""
Anthropic AI Provider Extension for AGiXT

This extension provides AI inference capabilities using Anthropic's Claude API,
supporting text generation and vision tasks.

Get your Anthropic API key at: https://console.anthropic.com/settings/keys

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

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_FAST_MODE_BETA = "fast-mode-2026-02-01"


def parse_anthropic_sse_stream(response):
    """Parse Anthropic SSE stream and yield text strings."""
    for line in response.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
        if not line_str.startswith("data: "):
            continue
        data_str = line_str[6:]
        if data_str.strip() == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if data.get("type") == "content_block_delta":
            delta = data.get("delta", {})
            text = delta.get("text", "")
            if text:
                yield text


class anthropic(Extensions):
    """
    Anthropic AI Provider - Claude models for LLM inference and vision tasks.

    Get your API key at https://console.anthropic.com/settings/keys
    """

    CATEGORY = "AI Provider"
    friendly_name = "Anthropic Claude"

    # Services this AI provider supports
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        ANTHROPIC_API_KEY: str = "",
        ANTHROPIC_AI_MODEL: str = "claude-opus-4-6",
        ANTHROPIC_MAX_TOKENS: int = 200000,
        ANTHROPIC_TEMPERATURE: float = 0.7,
        ANTHROPIC_FAST_MODE: bool = False,
        ANTHROPIC_WAIT_BETWEEN_REQUESTS: int = 1,
        **kwargs,
    ):
        # Get from parameter or environment
        if not ANTHROPIC_API_KEY:
            ANTHROPIC_API_KEY = getenv("ANTHROPIC_API_KEY", "")
        if not ANTHROPIC_AI_MODEL or ANTHROPIC_AI_MODEL == "claude-opus-4-6":
            ANTHROPIC_AI_MODEL = getenv("ANTHROPIC_MODEL", "claude-opus-4-6")

        self.ANTHROPIC_API_KEY = ANTHROPIC_API_KEY
        self.AI_MODEL = ANTHROPIC_AI_MODEL if ANTHROPIC_AI_MODEL else "claude-opus-4-6"
        self.MAX_TOKENS = int(ANTHROPIC_MAX_TOKENS) if ANTHROPIC_MAX_TOKENS else 200000
        self.AI_TEMPERATURE = (
            float(ANTHROPIC_TEMPERATURE) if ANTHROPIC_TEMPERATURE else 0.7
        )
        self.FAST_MODE = ANTHROPIC_FAST_MODE
        self.WAIT_BETWEEN_REQUESTS = (
            int(ANTHROPIC_WAIT_BETWEEN_REQUESTS)
            if ANTHROPIC_WAIT_BETWEEN_REQUESTS
            else 1
        )

        self.failure_count = 0

        # Check if configured
        self.configured = bool(
            self.ANTHROPIC_API_KEY
            and self.ANTHROPIC_API_KEY != ""
            and self.ANTHROPIC_API_KEY != "YOUR_ANTHROPIC_API_KEY"
        )

        # Commands that allow the AI to use this provider directly
        self.commands = {
            "Generate Response with Anthropic Claude": self.generate_response_command,
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
        """Build request headers for the Anthropic API."""
        headers = {
            "x-api-key": self.ANTHROPIC_API_KEY,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        if self.FAST_MODE:
            headers["anthropic-beta"] = ANTHROPIC_FAST_MODE_BETA
        return headers

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        """
        Generate text using Anthropic Claude.

        Args:
            prompt: The input prompt
            tokens: Input token count (for budgeting)
            images: List of image URLs or paths for vision tasks
            stream: Whether to stream the response
            use_smartest: Use the smartest model (Claude uses same model)

        Returns:
            Generated text response or stream object
        """
        if not self.configured:
            raise Exception("Anthropic provider not configured - missing API key")

        messages = []
        if images:
            from XT import is_safe_url

            content_parts = []
            for image in images:
                if image.startswith("http"):
                    # SSRF protection: validate URL before making request
                    if not is_safe_url(image):
                        logging.warning(
                            f"SSRF protection: blocked image download from {image}"
                        )
                        continue
                    image_base64 = base64.b64encode(
                        requests.get(image, timeout=30).content
                    ).decode("utf-8")
                else:
                    with open(image, "rb") as f:
                        image_base64 = base64.b64encode(f.read()).decode("utf-8")

                file_type = image.split(".")[-1] if "." in image else "jpeg"
                if file_type == "jpg":
                    file_type = "jpeg"

                content_parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": f"image/{file_type}",
                            "data": image_base64,
                        },
                    }
                )
            content_parts.append({"type": "text", "text": prompt})
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.AI_MODEL,
            "max_tokens": 4096,
            "messages": messages,
        }
        if self.FAST_MODE:
            payload["speed"] = "fast"
        if stream:
            payload["stream"] = True

        headers = self._get_headers()

        if self.WAIT_BETWEEN_REQUESTS > 0:
            time.sleep(self.WAIT_BETWEEN_REQUESTS)

        try:
            if stream:
                resp = requests.post(
                    ANTHROPIC_API_URL,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=300,
                )
                resp.raise_for_status()
                return parse_anthropic_sse_stream(resp)
            else:
                resp = requests.post(
                    ANTHROPIC_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=300,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["content"][0]["text"]

        except Exception as e:
            logging.error(f"Anthropic API Error: {e}")
            self.failure_count += 1

            if self.failure_count > 3:
                raise Exception(f"Anthropic Error: Too many failures. {e}")

            # Rate limits - sleep and retry
            # https://console.anthropic.com/settings/limits
            time.sleep(61)
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
        Generate a response using Anthropic Claude.

        Args:
            prompt: The prompt to send to Claude

        Returns:
            The generated text response from Claude
        """
        return await self.inference(prompt=prompt)
