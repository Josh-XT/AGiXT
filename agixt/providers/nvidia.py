import requests
import time
import logging
import asyncio


class NvidiaProvider:
    def __init__(
        self,
        API_KEY: str = "",
        API_URI: str = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/1361fa56-61d7-4a12-af32-69a3825746fa",
        MAX_TOKENS: int = 1024,
        AI_TEMPERATURE: float = 0.2,
        AI_TOP_P: float = 0.7,
        WAIT_BETWEEN_REQUESTS: int = 0,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.API_URI = API_URI
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_TOP_P = AI_TOP_P
        self.API_KEY = API_KEY
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE
        self.WAIT_BETWEEN_REQUESTS = WAIT_BETWEEN_REQUESTS
        self.FAILURES = []

    async def inference(self, prompt, tokens: int = 0):
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            await asyncio.sleep(int(self.WAIT_BETWEEN_REQUESTS))

        # Adjusting max tokens based on the additional tokens parameter
        max_tokens = int(self.MAX_TOKENS) - tokens

        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.AI_TEMPERATURE,
            "top_p": self.AI_TOP_P,
            "max_tokens": max_tokens,
            "stream": False,
        }

        response = await asyncio.to_thread(
            requests.post,
            self.API_URI,
            headers={
                "Authorization": f"Bearer {self.API_KEY}",
                "content-type": "application/json",
            },
            json=payload,
        )

        full_response = ""
        for line in response.iter_lines():
            if line:
                full_response += line.decode("utf-8") + "\n"

        # Extracting the content from the response
        content = response.json()["choices"][0]["message"]["content"]

        return str(content)
