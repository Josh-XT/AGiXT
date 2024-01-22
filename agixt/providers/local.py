import requests
import time
import logging
import os
from dotenv import load_dotenv

load_dotenv()


class LocalProvider:
    def __init__(
        self,
        LOCAL_LLM_SERVER: str = "http://local-llm:8091",
        LOCAL_LLM_API_KEY: str = "",
        SYSTEM_MESSAGE: str = "",
        AI_MODEL: str = "zephyr-7b-beta",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.95,
        MAX_TOKENS: int = 4096,
        WAIT_BETWEEN_REQUESTS: int = 0,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.LOCAL_LLM_SERVER = (
            LOCAL_LLM_SERVER if LOCAL_LLM_SERVER else "http://local-llm:8091"
        )
        self.LOCAL_LLM_API_KEY = (
            LOCAL_LLM_API_KEY if LOCAL_LLM_API_KEY else os.getenv("AGIXT_API_KEY", "")
        )
        self.SYSTEM_MESSAGE = SYSTEM_MESSAGE if SYSTEM_MESSAGE else ""
        self.AI_MODEL = AI_MODEL if AI_MODEL else "zephyr-7b-beta"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.95
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 0
        )
        self.MAX_TOKENS = int(MAX_TOKENS) if MAX_TOKENS else 4096

    async def inference(self, prompt, tokens: int = 0):
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        params = {
            "prompt": prompt,
            "model": self.AI_MODEL,
            "temperature": float(self.AI_TEMPERATURE),
            "max_tokens": int(self.MAX_TOKENS),
            "top_p": float(self.AI_TOP_P),
            "stream": False,
            "system_message": self.SYSTEM_MESSAGE,
        }
        response = requests.post(
            f"{self.LOCAL_LLM_SERVER}/v1/completions",
            headers={"Authorization": f"Bearer {self.LOCAL_LLM_API_KEY}"},
            json=params,
        )
        data = response.json()
        if data:
            if "choices" in data:
                if data["choices"]:
                    if "text" in data["choices"][0]:
                        return data["choices"][0]["text"].strip()
            if "error" in data:
                logging.info(f"Local-LLM API Error: {data}")
                if int(self.WAIT_AFTER_FAILURE) > 0:
                    time.sleep(int(self.WAIT_AFTER_FAILURE))
                    return await self.inference(prompt=prompt, tokens=tokens)
            return str(data)
