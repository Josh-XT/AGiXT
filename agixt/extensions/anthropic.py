"""
Anthropic AI Provider Extension for AGiXT

This extension provides AI inference capabilities using Anthropic's Claude API,
supporting text generation and vision tasks.

Get your Anthropic API key at: https://console.anthropic.com/settings/keys

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import base64
import logging
import time

import httpx
from Extensions import Extensions
from Globals import getenv, install_package_if_missing

install_package_if_missing("anthropic")
import anthropic


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
        ANTHROPIC_AI_MODEL: str = "claude-sonnet-4-20250514",
        ANTHROPIC_MAX_TOKENS: int = 200000,
        ANTHROPIC_TEMPERATURE: float = 0.7,
        ANTHROPIC_GOOGLE_VERTEX_REGION: str = "europe-west1",
        ANTHROPIC_GOOGLE_VERTEX_PROJECT_ID: str = "",
        ANTHROPIC_WAIT_BETWEEN_REQUESTS: int = 1,
        **kwargs,
    ):
        # Get from parameter or environment
        if not ANTHROPIC_API_KEY:
            ANTHROPIC_API_KEY = getenv("ANTHROPIC_API_KEY", "")
        if not ANTHROPIC_AI_MODEL or ANTHROPIC_AI_MODEL == "claude-sonnet-4-20250514":
            ANTHROPIC_AI_MODEL = getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        self.ANTHROPIC_API_KEY = ANTHROPIC_API_KEY
        self.AI_MODEL = (
            ANTHROPIC_AI_MODEL if ANTHROPIC_AI_MODEL else "claude-sonnet-4-20250514"
        )
        self.MAX_TOKENS = int(ANTHROPIC_MAX_TOKENS) if ANTHROPIC_MAX_TOKENS else 200000
        self.AI_TEMPERATURE = (
            float(ANTHROPIC_TEMPERATURE) if ANTHROPIC_TEMPERATURE else 0.7
        )
        self.GOOGLE_VERTEX_REGION = ANTHROPIC_GOOGLE_VERTEX_REGION
        self.GOOGLE_VERTEX_PROJECT_ID = ANTHROPIC_GOOGLE_VERTEX_PROJECT_ID
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
            "Generate Response with Anthropic": self.generate_response_command,
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

    def _get_client(self):
        """Get configured Anthropic client"""
        if self.GOOGLE_VERTEX_PROJECT_ID:
            return anthropic.AnthropicVertex(
                access_token=self.ANTHROPIC_API_KEY,
                region=self.GOOGLE_VERTEX_REGION,
                project_id=self.GOOGLE_VERTEX_PROJECT_ID,
            )
        else:
            return anthropic.Client(api_key=self.ANTHROPIC_API_KEY)

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
            for image in images:
                # If the image is a url, download it
                if image.startswith("http"):
                    image_base64 = base64.b64encode(httpx.get(image).content).decode(
                        "utf-8"
                    )
                else:
                    with open(image, "rb") as f:
                        image_base64 = base64.b64encode(f.read()).decode("utf-8")

                file_type = image.split(".")[-1] if "." in image else "jpeg"
                if file_type == "jpg":
                    file_type = "jpeg"

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": f"image/{file_type}",
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                )
        else:
            messages.append({"role": "user", "content": prompt})

        client = self._get_client()

        if self.WAIT_BETWEEN_REQUESTS > 0:
            time.sleep(self.WAIT_BETWEEN_REQUESTS)

        try:
            if stream:
                # Use streaming API - return stream object directly
                stream_response = client.messages.stream(
                    messages=messages,
                    model=self.AI_MODEL,
                    max_tokens=4096,
                )
                return stream_response
            else:
                response = client.messages.create(
                    messages=messages,
                    model=self.AI_MODEL,
                    max_tokens=4096,
                )
                return response.content[0].text

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
