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
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS

    def instruct(self, prompt: str, tokens: int = 0) -> str:
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
                    f"{self.HUGGINGFACE_API_URL}/models/{self.AI_MODEL}",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                return response.json()[0]["generated_text"]
            except:
                logging.info("Rate limit exceeded. Retrying after 20 seconds.")
                time.sleep(20)
                continue
