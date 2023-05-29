from time import time
from openai.error import RateLimitError
import openai
import logging


class AzureProvider:
    def __init__(
        self,
        AZURE_API_KEY: str = "",
        AZURE_OPENAI_ENDPOINT: str = "",
        DEPLOYMENT_ID: str = "",
        AZURE_EMBEDDER_DEPLOYMENT_ID: str = "",
        AI_MODEL: str = "gpt-35-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        **kwargs,
    ):
        openai.api_type = "azure"
        openai.api_base = AZURE_OPENAI_ENDPOINT
        openai.api_version = "2023-05-15"
        openai.api_key = AZURE_API_KEY
        self.requirements = ["openai"]
        self.DEPLOYMENT_ID = DEPLOYMENT_ID
        self.AZURE_API_KEY = AZURE_API_KEY
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AZURE_EMBEDDER_DEPLOYMENT_ID = AZURE_EMBEDDER_DEPLOYMENT_ID

    def instruct(self, prompt: str, tokens: int = 0) -> str:
        num_retries = 3
        messages = [{"role": "system", "content": prompt}]
        for _ in range(num_retries):
            try:
                resp = openai.ChatCompletion.create(
                    engine=self.AI_MODEL,
                    messages=messages,
                    max_tokens=int(self.MAX_TOKENS),
                    temperature=float(self.AI_TEMPERATURE),
                )["choices"][0]["message"]["content"]
                return resp

            except RateLimitError:
                logging.info("Rate limit exceeded. Retrying after 20 seconds.")
                time.sleep(20)
                continue
