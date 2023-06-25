from time import time
import requests
import logging


class HuggingfaceProvider:
    def __init__(
        self,
        HUGGINGFACE_API_KEY: str = "",
        HUGGINGFACE_API_URL: str = "",
        AI_MODEL: str = "gpt2",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        **kwargs,
    ):
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.HUGGINGFACE_API_URL = HUGGINGFACE_API_URL
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt2"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096

    async def instruct(self, prompt: str, tokens: int = 0) -> str:
        num_retries = 3
        headers = {"Authorization": f"Bearer {self.HUGGINGFACE_API_KEY}"}
        payload = {
            "inputs": prompt,
            "max_tokens": int(self.MAX_TOKENS),
            "temperature": float(self.AI_TEMPERATURE),
        }
        for _ in range(num_retries):
            try:
                response = requests.post(
                    self.HUGGINGFACE_API_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()[0]["generated_text"]
            except requests.exceptions.RequestException as e:
                logging.error(e)
                logging.info("Rate limit exceeded. Retrying after 20 seconds.")
                time.sleep(20)
                continue
