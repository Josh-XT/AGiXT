from time import time
from openai.error import RateLimitError
import openai


class AzureProvider:
    def __init__(
        self,
        AZURE_API_KEY: str = "",
        DEPLOYMENT_ID: str = "",
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        **kwargs,
    ):
        openai.api_type = "azure"
        self.requirements = ["openai"]
        self.DEPLOYMENT_ID = DEPLOYMENT_ID
        self.AZURE_API_KEY = AZURE_API_KEY
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS

    def instruct(self, prompt: str, tokens: int = 0) -> str:
        num_retries = 3
        messages = [{"role": "system", "content": prompt}]
        for _ in range(num_retries):
            try:
                resp = openai.ChatCompletion.create(
                    engine=self.DEPLOYMENT_ID,
                    messages=messages,
                    api_key=self.AZURE_API_KEY,
                    max_tokens=self.MAX_TOKENS,
                    temperature=float(self.AI_TEMPERATURE),
                )["choices"][0]["message"]["content"]
                return resp

            except RateLimitError:
                print("Rate limit exceeded. Retrying after 20 seconds.")
                time.sleep(20)
                continue
