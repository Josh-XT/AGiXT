"""
Azure OpenAI AI Provider Extension for AGiXT

This extension provides AI inference capabilities using Azure OpenAI API.
Learn more at https://learn.microsoft.com/en-us/azure/ai-services/openai/

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import base64
import logging
import time

from Extensions import Extensions
from Globals import getenv, install_package_if_missing

install_package_if_missing("openai")
from openai import AzureOpenAI


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

        if not self.AZURE_OPENAI_ENDPOINT.endswith("/"):
            self.AZURE_OPENAI_ENDPOINT += "/"

        client = AzureOpenAI(
            api_key=self.AZURE_API_KEY,
            api_version="2024-02-01",
            azure_endpoint=self.AZURE_OPENAI_ENDPOINT,
            azure_deployment=self.AI_MODEL,
        )

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
            response = client.chat.completions.create(
                model=self.AI_MODEL,
                messages=messages,
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=4096,
                top_p=float(self.AI_TOP_P),
                n=1,
                stream=stream,
            )
            if stream:
                return response
            return response.choices[0].message.content
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
