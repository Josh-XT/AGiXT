from time import time
from openai.error import RateLimitError

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
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
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 4096,
        **kwargs,
    ):
        openai.api_type = "azure"
        openai.base_url = AZURE_OPENAI_ENDPOINT
        openai.api_version = "2023-05-15"
        openai.api_key = AZURE_API_KEY
        self.requirements = ["openai"]
        self.DEPLOYMENT_ID = DEPLOYMENT_ID
        self.AZURE_API_KEY = AZURE_API_KEY
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-35-turbo"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096
        self.AZURE_EMBEDDER_DEPLOYMENT_ID = AZURE_EMBEDDER_DEPLOYMENT_ID

    async def inference(self, prompt: str, tokens: int = 0) -> str:
        num_retries = 3
        messages = [{"role": "system", "content": prompt}]
        for _ in range(num_retries):
            try:
                resp = openai.ChatCompletion.create(
                    engine=self.AI_MODEL,
                    messages=messages,
                    max_tokens=int(self.MAX_TOKENS),
                    temperature=float(self.AI_TEMPERATURE),
                    top_p=float(self.AI_TOP_P),
                )["choices"][0]["message"]["content"]
                return resp

            except RateLimitError:
                logging.info("Rate limit exceeded. Retrying after 20 seconds.")
                time.sleep(20)
                continue
