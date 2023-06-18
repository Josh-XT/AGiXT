import requests
import random


class LlamacppapiProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "http://localhost:8000",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        STOP_SEQUENCE: str = "</s>",
        **kwargs,
    ):
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.STOP_SEQUENCE = STOP_SEQUENCE
        self.MAX_TOKENS = int(self.MAX_TOKENS)

    async def instruct(self, prompt, tokens: int = 0):
        params = {
            "prompt": prompt,
            "temperature": float(self.AI_TEMPERATURE),
            "stop": self.STOP_SEQUENCE,
            "seed": random.randint(1, 1000000000),
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/v1/completions", json=params)
        data = response.json()
        print(data)
        choices = data["choices"]
        if choices:
            return choices[0]["text"]
        return None
