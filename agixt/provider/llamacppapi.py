import requests
import random


class LlamacppapiProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "http://localhost:8000",
        EMBEDDING_URI: str = "http://localhost:8001",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        BATCH_SIZE: int = 512,
        THREADS: int = 0,
        STOP_SEQUENCE: str = "\n",
        EXCLUDE_STRING: str = "",
        **kwargs,
    ):
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.BATCH_SIZE = BATCH_SIZE
        self.THREADS = THREADS if THREADS != 0 else None
        self.STOP_SEQUENCE = STOP_SEQUENCE
        self.EXCLUDE_STRING = EXCLUDE_STRING
        self.EMBEDDING_URI = EMBEDDING_URI
        self.MAX_TOKENS = int(self.MAX_TOKENS)

    def instruct(self, prompt, tokens: int = 0):
        new_tokens = int(self.MAX_TOKENS) - tokens
        params = {
            "prompt": prompt,
            "batch_size": int(self.BATCH_SIZE),
            "temperature": float(self.AI_TEMPERATURE),
            "stop": self.STOP_SEQUENCE,
            "seed": random.randint(1, 1000000000),
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/v1/completion", json=params)
        data = response.json()
        return data["content"]

    def embeddding(self, prompt):
        data = requests.post(
            f"{self.EMBEDDING_URI}/v1/embeddding",
            json={"input": prompt},
        )
        return data["embedding"]
