"""
LiteLLM AI Provider Extension for AGiXT

Routes to 100+ LLM providers via litellm.completion().
Provider API keys are read from environment variables automatically
(OPENAI_API_KEY, ANTHROPIC_API_KEY, AWS_ACCESS_KEY_ID, GEMINI_API_KEY, etc.).

Model names use LiteLLM format: "provider/model-name", e.g.:
    anthropic/claude-sonnet-4-20250514, openai/gpt-4o,
    bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0

See https://docs.litellm.ai/docs/providers for the full list.

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid model name.
"""

import base64
import logging
import time

from Extensions import Extensions
from Globals import getenv


class litellm(Extensions):
    """
    LiteLLM AI Provider - routes to 100+ LLM providers via a unified interface.

    Set your provider's API key as an environment variable
    (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, AWS_ACCESS_KEY_ID, etc.)
    and specify the model in LiteLLM format (provider/model-name).

    See https://docs.litellm.ai/docs/providers for the full list.
    """

    CATEGORY = "AI Provider"
    friendly_name = "LiteLLM"
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        LITELLM_MODEL: str = "openai/gpt-4o-mini",
        LITELLM_MAX_TOKENS: int = 4096,
        LITELLM_TEMPERATURE: float = 0.1,
        LITELLM_TOP_P: float = 0.95,
        LITELLM_WAIT_BETWEEN_REQUESTS: int = 0,
        LITELLM_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.AI_MODEL = LITELLM_MODEL if LITELLM_MODEL else "openai/gpt-4o-mini"
        self.MAX_TOKENS = int(LITELLM_MAX_TOKENS) if LITELLM_MAX_TOKENS else 4096
        self.AI_TEMPERATURE = float(LITELLM_TEMPERATURE) if LITELLM_TEMPERATURE else 0.1
        self.AI_TOP_P = float(LITELLM_TOP_P) if LITELLM_TOP_P else 0.95
        self.WAIT_BETWEEN_REQUESTS = (
            int(LITELLM_WAIT_BETWEEN_REQUESTS) if LITELLM_WAIT_BETWEEN_REQUESTS else 0
        )
        self.WAIT_AFTER_FAILURE = (
            int(LITELLM_WAIT_AFTER_FAILURE) if LITELLM_WAIT_AFTER_FAILURE else 3
        )
        self.failures = 0
        self.configured = bool(self.AI_MODEL and self.AI_MODEL != "")

        self.commands = {
            "Generate Response with LiteLLM": self.generate_response_command,
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
        import litellm as _litellm

        if not self.configured:
            raise Exception("LiteLLM provider not configured")

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
            completion_kwargs = {
                "model": self.AI_MODEL,
                "messages": messages,
                "max_tokens": 4096,
                "n": 1,
                "stream": stream,
                "stop": ["</execute>"],
                "drop_params": True,
            }
            if self.AI_TEMPERATURE is not None:
                completion_kwargs["temperature"] = float(self.AI_TEMPERATURE)
            if self.AI_TOP_P is not None and self.AI_TEMPERATURE is None:
                completion_kwargs["top_p"] = float(self.AI_TOP_P)

            response = _litellm.completion(**completion_kwargs)

            if stream:
                return response

            return response.choices[0].message.content
        except Exception as e:
            logging.info(f"LiteLLM API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"LiteLLM API Error: Too many failures. {e}")
            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, stream=stream
            )

    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using LiteLLM.

        Args:
            prompt: The prompt to send to LiteLLM

        Returns:
            The generated text response
        """
        return await self.inference(prompt=prompt)
