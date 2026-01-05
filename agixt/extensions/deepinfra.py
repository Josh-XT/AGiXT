"""
DeepInfra AI Provider Extension for AGiXT

This extension provides AI inference capabilities using the DeepInfra API.
Get your API key from https://deepinfra.com

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


class deepinfra(Extensions):
    """
    DeepInfra AI Provider - Access to various models via DeepInfra

    Get your API key at https://deepinfra.com
    """

    CATEGORY = "AI Provider"
    friendly_name = "DeepInfra"
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        DEEPINFRA_API_KEY: str = "",
        DEEPINFRA_ENDPOINT_URL: str = "https://api.deepinfra.com/v1/openai",
        DEEPINFRA_MODEL: str = "Qwen/Qwen3-235B-A22B-Instruct-2507",
        DEEPINFRA_VISION_MODEL: str = "Qwen/Qwen3-VL-30B-A3B-Instruct",
        DEEPINFRA_CODING_MODEL: str = "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        DEEPINFRA_MAX_TOKENS: int = 128000,
        DEEPINFRA_TEMPERATURE: float = 0.7,
        DEEPINFRA_TOP_P: float = 0.9,
        DEEPINFRA_WAIT_BETWEEN_REQUESTS: int = 1,
        DEEPINFRA_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        if not DEEPINFRA_API_KEY:
            DEEPINFRA_API_KEY = getenv("DEEPINFRA_API_KEY", "")

        self.DEEPINFRA_API_KEY = DEEPINFRA_API_KEY
        self.ENDPOINT_URL = (
            DEEPINFRA_ENDPOINT_URL
            if DEEPINFRA_ENDPOINT_URL
            else "https://api.deepinfra.com/v1/openai"
        )
        self.AI_MODEL = (
            DEEPINFRA_MODEL if DEEPINFRA_MODEL else "Qwen/Qwen3-235B-A22B-Instruct-2507"
        )
        self.VISION_MODEL = (
            DEEPINFRA_VISION_MODEL
            if DEEPINFRA_VISION_MODEL
            else "Qwen/Qwen3-VL-30B-A3B-Instruct"
        )
        self.CODING_MODEL = (
            DEEPINFRA_CODING_MODEL
            if DEEPINFRA_CODING_MODEL
            else "Qwen/Qwen3-Coder-480B-A35B-Instruct"
        )
        self.MAX_TOKENS = int(DEEPINFRA_MAX_TOKENS) if DEEPINFRA_MAX_TOKENS else 128000
        self.AI_TEMPERATURE = (
            float(DEEPINFRA_TEMPERATURE) if DEEPINFRA_TEMPERATURE else 0.7
        )
        self.AI_TOP_P = float(DEEPINFRA_TOP_P) if DEEPINFRA_TOP_P else 0.9
        self.WAIT_BETWEEN_REQUESTS = (
            int(DEEPINFRA_WAIT_BETWEEN_REQUESTS)
            if DEEPINFRA_WAIT_BETWEEN_REQUESTS
            else 1
        )
        self.WAIT_AFTER_FAILURE = (
            int(DEEPINFRA_WAIT_AFTER_FAILURE) if DEEPINFRA_WAIT_AFTER_FAILURE else 3
        )
        self.failures = 0

        self.configured = bool(self.DEEPINFRA_API_KEY and self.DEEPINFRA_API_KEY != "")

        self.commands = {
            "Generate Response with DeepInfra": self.generate_response_command,
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
            raise Exception("DeepInfra provider not configured")

        model = self.AI_MODEL
        if use_smartest:
            model = self.CODING_MODEL
        if images:
            model = self.VISION_MODEL

        base_url = self.ENDPOINT_URL.rstrip("/")
        api_url = (
            f"{base_url}/chat/completions"
            if not base_url.endswith("/chat/completions")
            else base_url
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.DEEPINFRA_API_KEY}",
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

        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(self.AI_TEMPERATURE),
            "max_tokens": int(self.MAX_TOKENS),
            "top_p": float(self.AI_TOP_P),
            "stream": stream,
        }

        if self.WAIT_BETWEEN_REQUESTS > 0:
            time.sleep(self.WAIT_BETWEEN_REQUESTS)

        try:
            if stream:
                response = requests.post(
                    api_url, headers=headers, json=payload, stream=True, timeout=120
                )
                response.raise_for_status()

                def stream_generator():
                    for line in response.iter_lines():
                        if line:
                            line_str = line.decode("utf-8").strip()
                            if line_str.startswith("data: "):
                                data = line_str[6:]
                                if data != "[DONE]":
                                    try:
                                        chunk = json.loads(data)
                                        if (
                                            "choices" in chunk
                                            and len(chunk["choices"]) > 0
                                        ):
                                            delta = chunk["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                yield content
                                    except json.JSONDecodeError:
                                        pass

                return stream_generator()
            else:
                response = requests.post(
                    api_url, headers=headers, json=payload, timeout=120
                )
                response.raise_for_status()
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                return "No response from model"
        except Exception as e:
            self.failures += 1
            logging.error(f"DeepInfra API Error: {e}")
            if self.failures >= 3:
                raise Exception(f"DeepInfra API Error: Too many failures. {e}")
            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, stream=stream
            )

    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using DeepInfra

        Args:
            prompt: The prompt to send to DeepInfra

        Returns:
            The generated text response
        """
        return await self.inference(prompt=prompt)
