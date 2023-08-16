import json
import logging

import requests
from websocket import WebSocket


class PetalProvider():
    def __init__(
            self,
            AI_TEMPERATURE: float = 0.7,
            MAX_TOKENS: int = 1024,
            AI_MODEL: str = "enoch/llama-65b-hf",
            **kwargs,
    ):
        self.AI_TEMPERATURE = AI_TEMPERATURE,
        self.MAX_TOKENS = MAX_TOKENS,
        self.AI_MODEL = AI_MODEL,
        self.base_url = "https://chat.petals.dev/api/v1/generate"

    async def instruct(self, prompt, tokens: int = 0):
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            'max_length': self.MAX_TOKENS,
            'do_sample': 0,
            'inputs': prompt,
        }
        response = requests.post(url=self.base_url, headers=headers, data=payload)
        return response.json()


if __name__ == '__main__':
    import asyncio


    async def run_test():
        petal = PetalProvider()
        response = await petal.instruct('What is the meaning of life?')
        print(response)


    asyncio.run(run_test())
