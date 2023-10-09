import requests


class KoboldProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "",
        AI_MODEL: str = "default",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.7,
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        **kwargs,
    ):
        self.requirements = []
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_MODEL = AI_MODEL
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else ""
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else ""

    async def instruct(self, prompt, tokens: int = 0):
        prompt = f"{self.PROMPT_PREFIX}{prompt}{self.PROMPT_SUFFIX}"
        try:
            max_tokens = int(self.MAX_TOKENS - tokens)
        except:
            max_tokens = 2048
        response = requests.post(
            f"{self.AI_PROVIDER_URI}/api/v1/generate",
            json={
                "prompt": prompt,
                "max_context_length": max_tokens,
                "max_length": max_tokens,
                "temperature": float(self.AI_TEMPERATURE),
            },
        )
        try:
            return response.json()["results"][0]["text"].replace("\n", "\n")
        except:
            return response.json()["detail"][0]["msg"].replace("\n", "\n")
