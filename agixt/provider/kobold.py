import requests


class KoboldProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        **kwargs,
    ):
        self.requirements = []
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_MODEL = AI_MODEL

    def instruct(self, prompt, tokens: int = 0):
        try:
            max_tokens = int(self.MAX_TOKENS - tokens)
        except:
            max_tokens = 2000
        response = requests.post(
            f"{self.AI_PROVIDER_URI}/api/v1/generate",
            json={
                "prompt": prompt,
                "max_context_length": max_tokens,
                "max_length": 200,
                "temperature": float(self.AI_TEMPERATURE),
            },
        )
        try:
            return response.json()["results"][0]["text"].replace("\n", "\n")
        except:
            return response.json()["detail"][0]["msg"].replace("\n", "\n")
