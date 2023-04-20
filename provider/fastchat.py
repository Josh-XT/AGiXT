import requests
import json
from Config import Config

CFG = Config()

class AIProvider:
    def instruct(self, prompt):
        messages = [{"role": "system", "content": prompt}]
        params = {
            "model": CFG.AI_MODEL,
            "messages": messages
        }
        response = requests.post(f"{CFG.AI_PROVIDER_URI}/v1/chat/completions", json={"data": [json.dumps([prompt, params])]})
        return response.json()['data'][0].replace("\n", "\n")