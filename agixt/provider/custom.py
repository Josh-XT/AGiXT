import requests
import time
import logging


# Custom OpenAI Style Provider
class CustomProvider:
    def __init__(
        self,
        API_KEY: str = "",
        API_URI: str = "https://api.openai.com/v1/engines/davinci/completions",
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 4096,
        WAIT_BETWEEN_REQUESTS: int = 0,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_TOP_P = AI_TOP_P
        self.MAX_TOKENS = MAX_TOKENS
        self.API_KEY = API_KEY
        self.API_URI = API_URI
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE
        self.WAIT_BETWEEN_REQUESTS = WAIT_BETWEEN_REQUESTS

    async def instruct(self, prompt, tokens: int = 0):
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
                if int(self.WAIT_AFTER_FAILURE) > 0:
                    time.sleep(int(self.WAIT_AFTER_FAILURE))
                    return await self.instruct(prompt=prompt, tokens=tokens)
            return str(data)
