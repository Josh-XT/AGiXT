import requests
import time
import logging
import random


# Custom OpenAI Style Provider
class CustomProvider:
    def __init__(
        self,
        API_KEY: str = "",
        API_URI: str = "https://api.openai.com/v1/chat/completions",
        AI_MODEL: str = "gpt-3.5-turbo-16k-0613",
        MAX_TOKENS: int = 4096,
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        WAIT_BETWEEN_REQUESTS: int = 0,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo-16k-0613"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 16000
        self.API_KEY = API_KEY
        self.API_URI = API_URI
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 0
        )
        self.FAILURES = []

    def rotate_uri(self):
        self.FAILURES.append(self.API_URI)
        uri_list = self.API_URI.split(",")
        random.shuffle(uri_list)
        for uri in uri_list:
            if uri not in self.FAILURES:
                self.API_URI = uri
                break

    async def inference(self, prompt, tokens: int = 0):
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        if not self.AI_MODEL.startswith("gpt-"):
            # Use completion API
            params = {
                "prompt": prompt,
                "model": self.AI_MODEL,
                "temperature": float(self.AI_TEMPERATURE),
                "max_tokens": max_new_tokens,
                "top_p": float(self.AI_TOP_P),
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "stream": False,
            }
        else:
            # Use chat completion API
            params = {
                "messages": [{"role": "user", "content": prompt}],
                "model": self.AI_MODEL,
                "temperature": float(self.AI_TEMPERATURE),
                "max_tokens": max_new_tokens,
                "top_p": float(self.AI_TOP_P),
                "stream": False,
            }

        response = requests.post(
            self.API_URI,
            headers={"Authorization": f"Bearer {self.API_KEY}"},
            json=params,
        )
        data = response.json()
        if data:
            if "choices" in data:
                if data["choices"]:
                    if "text" in data["choices"][0]:
                        return data["choices"][0]["text"].strip()
                    if "message" in data["choices"][0]:
                        return data["choices"][0]["message"]["content"].strip()
            if "error" in data:
                logging.info(f"Custom API Error: {data}")
                if "," in self.API_URI:
                    self.rotate_uri()
                if int(self.WAIT_AFTER_FAILURE) > 0:
                    time.sleep(int(self.WAIT_AFTER_FAILURE))
                    return await self.inference(prompt=prompt, tokens=tokens)
            return str(data)
