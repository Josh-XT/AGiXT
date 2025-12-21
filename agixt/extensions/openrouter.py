"""
OpenRouter AI Provider Extension for AGiXT

This extension provides AI inference capabilities using the OpenRouter API,
which provides access to a wide variety of AI models.

Get your API key at https://openrouter.ai/keys

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import base64
import logging

import httpx
from Extensions import Extensions
from Globals import getenv, install_package_if_missing

install_package_if_missing("openai")
import openai as openai_module


class openrouter(Extensions):
    """
    OpenRouter AI Provider - Access to multiple AI models through a unified API.

    Get your API key at https://openrouter.ai/keys
    """

    CATEGORY = "AI Provider"
    friendly_name = "OpenRouter"
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        OPENROUTER_API_KEY: str = "",
        OPENROUTER_API_URI: str = "https://openrouter.ai/api/v1/",
        OPENROUTER_AI_MODEL: str = "openai/gpt-4o",
        OPENROUTER_CODING_MODEL: str = "anthropic/claude-sonnet-4",
        OPENROUTER_MAX_TOKENS: int = 16384,
        OPENROUTER_TEMPERATURE: float = 0.7,
        OPENROUTER_TOP_P: float = 0.95,
        **kwargs,
    ):
        if not OPENROUTER_API_KEY:
            OPENROUTER_API_KEY = getenv("OPENROUTER_API_KEY", "")

        self.OPENROUTER_API_KEY = OPENROUTER_API_KEY
        self.AI_MODEL = OPENROUTER_AI_MODEL if OPENROUTER_AI_MODEL else "openai/gpt-4o"
        self.CODING_MODEL = (
            OPENROUTER_CODING_MODEL
            if OPENROUTER_CODING_MODEL
            else "anthropic/claude-sonnet-4"
        )
        self.API_URI = (
            OPENROUTER_API_URI
            if OPENROUTER_API_URI
            else "https://openrouter.ai/api/v1/"
        )
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        self.MAX_TOKENS = int(OPENROUTER_MAX_TOKENS) if OPENROUTER_MAX_TOKENS else 16384
        self.AI_TEMPERATURE = (
            float(OPENROUTER_TEMPERATURE) if OPENROUTER_TEMPERATURE else 0.7
        )
        self.AI_TOP_P = float(OPENROUTER_TOP_P) if OPENROUTER_TOP_P else 0.95
        self.failure_count = 0

        self.configured = bool(
            self.OPENROUTER_API_KEY and self.OPENROUTER_API_KEY != ""
        )

        self.commands = {
            "Generate Response with OpenRouter": self.generate_response_command,
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

    def _get_client(self):
        return openai_module.OpenAI(
            base_url=self.API_URI,
            api_key=self.OPENROUTER_API_KEY,
            timeout=httpx.Timeout(300.0, read=300.0, write=30.0, connect=10.0),
            default_headers={
                "HTTP-Referer": getenv("AGIXT_URI"),
                "X-Title": "AGiXT",
            },
        )

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        if not self.configured:
            raise Exception("OpenRouter provider not configured")

        model = self.CODING_MODEL if use_smartest else self.AI_MODEL
        client = self._get_client()

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

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=int(self.MAX_TOKENS),
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
                n=1,
                stream=stream,
            )
            if stream:
                return response
            return response.choices[0].message.content
        except Exception as e:
            self.failure_count += 1
            logging.info(f"OpenRouter API Error: {e}")
            if self.failure_count >= 3:
                raise Exception(f"OpenRouter API Error: Too many failures. {e}")
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, stream=stream
            )

    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using OpenRouter.

        Args:
            prompt: The prompt to send to OpenRouter

        Returns:
            The generated text response
        """
        return await self.inference(prompt=prompt)
