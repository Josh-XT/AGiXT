import requests
import json


class AIProvider:
    def __init__(self, AI_PROVIDER_URI: str = "", AI_MODEL: str = ""):
        self.requirements = []
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.AI_MODEL = AI_MODEL

    def instruct(self, prompt):
        messages = [{"role": "system", "content": prompt}]
        params = {"model": self.AI_MODEL, "messages": messages}
        response = requests.post(
            f"{self.AI_PROVIDER_URI}/v1/chat/completions",
            json={"data": [json.dumps([prompt, params])]},
        )
        return response.json()["data"][0].replace("\n", "\n")
