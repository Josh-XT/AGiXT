"""
Huggingface AI Provider Extension for AGiXT

This extension provides AI inference and image generation using the Huggingface API.
Get your API key at https://huggingface.co/login

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import base64
import io
import logging
import time
import uuid

import requests
from PIL import Image
from Extensions import Extensions
from Globals import getenv


class huggingface(Extensions):
    """
    Huggingface AI Provider - Access to Huggingface models for LLM and image generation

    Get your API key at https://huggingface.co/login
    """

    CATEGORY = "AI Provider"
    friendly_name = "Hugging Face"
    SERVICES = ["llm", "image"]

    def __init__(
        self,
        HUGGINGFACE_API_KEY: str = "",
        HUGGINGFACE_MODEL: str = "HuggingFaceH4/zephyr-7b-beta",
        HUGGINGFACE_STABLE_DIFFUSION_MODEL: str = "runwayml/stable-diffusion-v1-5",
        HUGGINGFACE_STABLE_DIFFUSION_API_URL: str = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5",
        HUGGINGFACE_STOP_TOKEN: str = "<|end|>",
        HUGGINGFACE_MAX_TOKENS: int = 1024,
        HUGGINGFACE_TEMPERATURE: float = 0.7,
        HUGGINGFACE_MAX_RETRIES: int = 15,
        **kwargs,
    ):
        if not HUGGINGFACE_API_KEY:
            HUGGINGFACE_API_KEY = getenv("HUGGINGFACE_API_KEY", "")

        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.AI_MODEL = (
            HUGGINGFACE_MODEL if HUGGINGFACE_MODEL else "HuggingFaceH4/zephyr-7b-beta"
        )
        self.HUGGINGFACE_API_URL = (
            f"https://api-inference.huggingface.co/models/{self.AI_MODEL}"
        )

        if (
            HUGGINGFACE_STABLE_DIFFUSION_MODEL
            and HUGGINGFACE_STABLE_DIFFUSION_MODEL.startswith("https://")
        ):
            self.STABLE_DIFFUSION_API_URL = HUGGINGFACE_STABLE_DIFFUSION_MODEL
        elif (
            HUGGINGFACE_STABLE_DIFFUSION_MODEL
            and HUGGINGFACE_STABLE_DIFFUSION_MODEL != "runwayml/stable-diffusion-v1-5"
        ):
            self.STABLE_DIFFUSION_API_URL = f"https://api-inference.huggingface.co/models/{HUGGINGFACE_STABLE_DIFFUSION_MODEL}"
        else:
            self.STABLE_DIFFUSION_API_URL = HUGGINGFACE_STABLE_DIFFUSION_API_URL

        self.AI_TEMPERATURE = (
            float(HUGGINGFACE_TEMPERATURE) if HUGGINGFACE_TEMPERATURE else 0.7
        )
        self.MAX_TOKENS = (
            int(HUGGINGFACE_MAX_TOKENS) if HUGGINGFACE_MAX_TOKENS else 1024
        )
        self.stop = (
            [HUGGINGFACE_STOP_TOKEN]
            if isinstance(HUGGINGFACE_STOP_TOKEN, str)
            else HUGGINGFACE_STOP_TOKEN
        )
        self.MAX_RETRIES = (
            int(HUGGINGFACE_MAX_RETRIES) if HUGGINGFACE_MAX_RETRIES else 15
        )

        self.configured = bool(
            self.HUGGINGFACE_API_KEY and self.HUGGINGFACE_API_KEY != ""
        )

        self.commands = {
            "Generate Response with Huggingface": self.generate_response_command,
            "Generate Image with Huggingface": self.generate_image_command,
        }

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient", None)

    @staticmethod
    def services():
        return ["llm", "image"]

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
            raise Exception("Huggingface provider not configured")

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": self.AI_TEMPERATURE,
                "max_new_tokens": (int(self.MAX_TOKENS) - tokens),
                "return_full_text": False,
                "stop": self.stop,
            },
            "stream": stream,
        }

        headers = {}
        if self.HUGGINGFACE_API_KEY:
            headers["Authorization"] = f"Bearer {self.HUGGINGFACE_API_KEY}"

        tries = 0
        while True:
            tries += 1
            if tries > self.MAX_RETRIES:
                raise ValueError(f"Reached max retries: {self.MAX_RETRIES}")

            if stream:
                response = requests.post(
                    self.HUGGINGFACE_API_URL, json=payload, headers=headers, stream=True
                )
                if response.status_code == 429:
                    logging.info(f"Rate limited, waiting {tries} seconds")
                    time.sleep(tries)
                    continue
                elif response.status_code >= 500:
                    logging.info(
                        f"Server error {response.status_code}, waiting {tries} seconds"
                    )
                    time.sleep(tries)
                    continue
                elif response.status_code != 200:
                    raise ValueError(f"Error {response.status_code}: {response.text}")
                return response
            else:
                response = requests.post(
                    self.HUGGINGFACE_API_URL, json=payload, headers=headers
                )
                if response.status_code == 429:
                    logging.info(f"Rate limited, waiting {tries} seconds")
                    time.sleep(tries)
                elif response.status_code >= 500:
                    logging.info(
                        f"Server error {response.status_code}, waiting {tries} seconds"
                    )
                    time.sleep(tries)
                elif response.status_code != 200:
                    raise ValueError(f"Error {response.status_code}: {response.text}")
                else:
                    break

        response_json = response.json()
        result = response_json[0]["generated_text"]
        if self.stop:
            for stop_seq in self.stop:
                find = result.find(stop_seq)
                if find >= 0:
                    result = result[:find]
        return result

    async def generate_image(self, prompt: str) -> str:
        """Generate an image from a text prompt."""
        if not self.configured:
            raise Exception("Huggingface provider not configured")

        headers = {}
        if self.HUGGINGFACE_API_KEY:
            headers["Authorization"] = f"Bearer {self.HUGGINGFACE_API_KEY}"

        try:
            response = requests.post(
                self.STABLE_DIFFUSION_API_URL,
                headers=headers,
                json={"inputs": prompt},
            )
            image_data = response.content
            # Return as base64 encoded string
            return base64.b64encode(image_data).decode("utf-8")
        except Exception as e:
            logging.error(f"Error generating image: {e}")
            raise Exception(f"Error generating image: {e}")

    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using Huggingface.

        Args:
            prompt: The prompt to send to Huggingface

        Returns:
            The generated text response
        """
        return await self.inference(prompt=prompt)

    async def generate_image_command(self, prompt: str) -> str:
        """
        Generate an image using Huggingface Stable Diffusion.

        Args:
            prompt: Text description of the image to generate

        Returns:
            URL to the generated image
        """
        return await self.generate_image(prompt=prompt)
