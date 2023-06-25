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
        self.AI_PROVIDER_URI = (
            AI_PROVIDER_URI if AI_PROVIDER_URI else "http://localhost:8000"
        )
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.STOP_SEQUENCE = STOP_SEQUENCE if STOP_SEQUENCE else "</s>"
        self.MAX_TOKENS = int(self.MAX_TOKENS) if self.MAX_TOKENS else 2048

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
