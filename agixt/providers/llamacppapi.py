import requests
import random


class LlamacppapiProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "http://localhost:8000",
        AI_MODEL: str = "default",
        STOP_SEQUENCE: str = "</s>",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        **kwargs,
    ):
        self.AI_PROVIDER_URI = (
            AI_PROVIDER_URI if AI_PROVIDER_URI else "http://localhost:8000"
        )
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.STOP_SEQUENCE = STOP_SEQUENCE if STOP_SEQUENCE else "</s>"
        self.MAX_TOKENS = int(self.MAX_TOKENS) if self.MAX_TOKENS else 2048

    async def instruct(self, prompt, tokens: int = 0):
        max_tokens = int(self.MAX_TOKENS) - tokens
        params = {
            "prompt": prompt,
            "temperature": float(self.AI_TEMPERATURE),
            "top_p": float(self.AI_TOP_P),
            "stop": self.STOP_SEQUENCE,
            "seed": random.randint(1, 1000000000),
            "n_predict": int(max_tokens),
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/completion", json=params)
        data = response.json()
        print(data)
        if "choices" in data:
            choices = data["choices"]
            if choices:
                return choices[0]["text"]
        if "content" in data:
            return data["content"]
        return data
