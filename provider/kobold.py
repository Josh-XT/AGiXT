import requests
from Config import Config

CFG = Config()


class AIProvider:
    def instruct(self, prompt):
        try:
            max_tokens = int(CFG.MAX_TOKENS)
        except:
            max_tokens = 2000
        response = requests.post(
            f"{CFG.AI_PROVIDER_URI}/generate",
            json={
                "prompt": prompt,
                "max_length": max_tokens,
                "temperature": float(CFG.TEMPERATURE),
            },
        )
        try:
            return response.json()["results"][0]["text"].replace("\n", "\n")
        except:
            return response.json()["detail"][0]["msg"].replace("\n", "\n")
