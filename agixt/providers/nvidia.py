import requests
import time
import logging
import random


class NvidiaProvider:
    def __init__(
        self,
        API_KEY: str = "",
        API_URI: str = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/8f4118ba-60a8-4e6b-8574-e38a4067a4a3",
        FETCH_URL_FORMAT: str = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/",
        MAX_TOKENS: int = 1024,
        AI_TEMPERATURE: float = 0.2,
        AI_TOP_P: float = 0.7,
        SEED: int = 42,
        WAIT_BETWEEN_REQUESTS: int = 0,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.API_KEY = API_KEY
        self.API_URI = API_URI
        self.FETCH_URL_FORMAT = FETCH_URL_FORMAT
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_TOP_P = AI_TOP_P
        self.SEED = SEED
        self.WAIT_BETWEEN_REQUESTS = WAIT_BETWEEN_REQUESTS
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE
        self.FAILURES = []

    async def inference(self, prompt, tokens: int = 0):
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))

        tokens = int(tokens)
        max_tokens = int(self.MAX_TOKENS) - tokens

        payload = {
            "messages": [{"content": prompt, "role": "user"}],
            "temperature": self.AI_TEMPERATURE,
            "top_p": self.AI_TOP_P,
            "max_tokens": max_tokens,
            "seed": self.SEED,
            "bad": None,
            "stop": None,
            "stream": False,
        }

        session = requests.Session()
        headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Accept": "application/json",
        }

        response = session.post(self.API_URI, headers=headers, json=payload)

        while response.status_code == 202:
            request_id = response.headers.get("NVCF-REQID")
            fetch_url = self.FETCH_URL_FORMAT + request_id
            response = session.get(fetch_url, headers=headers)

        response.raise_for_status()
        response_body = response.json()

        # Extracting content from the response
        content = response_body["choices"][0]["message"]["content"]

        return str(content)
