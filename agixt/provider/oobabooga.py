import requests
import random
import re


class OobaboogaProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        **kwargs,
    ):
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_MODEL = AI_MODEL
        self.requirements = []

    def instruct(self, prompt, tokens: int = 0):
        new_tokens = int(self.MAX_TOKENS) - tokens
        params = {
            "prompt": prompt,
            "max_new_tokens": new_tokens,
            "do_sample": True,
            "temperature": float(self.AI_TEMPERATURE),
            "top_p": 0.73,
            "typical_p": 1,
            "repetition_penalty": 1.1,
            "top_k": 0,
            "min_length": 0,
            "no_repeat_ngram_size": 0,
            "num_beams": 1,
            "penalty_alpha": 0,
            "length_penalty": 1,
            "early_stopping": False,
            "seed": random.randint(1, 1000000000),
            "add_bos_token": True,
            "truncation_length": 4096,
            "ban_eos_token": False,
            "skip_special_tokens": True,
            "stopping_strings": [],
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/api/v1/generate", json=params)
        data = None
        if response.status_code == 200:
            data = response.json()["results"][0]["text"]
            data = re.sub(r"(?<!\\)\\(?!n)", "", data)
        return data
