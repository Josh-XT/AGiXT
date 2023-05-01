import requests


class KoboldProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.requirements = []
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE

    def instruct(self, prompt):
        try:
            max_tokens = int(self.MAX_TOKENS - len(prompt))
        except:
            max_tokens = 2000
        response = requests.post(
            f"{self.AI_PROVIDER_URI}/generate",
            json={
                "prompt": prompt,
                "max_length": max_tokens,
                "temperature": float(self.AI_TEMPERATURE),
            },
        )
        try:
            return response.json()["results"][0]["text"].replace("\n", "\n")
        except:
            return response.json()["detail"][0]["msg"].replace("\n", "\n")
