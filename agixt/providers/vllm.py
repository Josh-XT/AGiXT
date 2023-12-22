import time
import logging
import random

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai


class VllmProvider:
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        AI_MODEL: str = "mistralai/Mistral-7B-Instruct-v0.2",
        API_URI: str = "http://localhost:8091/v1",
        MAX_TOKENS: int = 16000,
        AI_TEMPERATURE: float = 1.34,
        AI_TOP_P: float = 0.9,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        PROMPT_PREFIX: str = "[INST]",
        PROMPT_SUFFIX: str = "[/INST]",
        STOP_STRING: str = "</s>",
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "mistralai/Mistral-7B-Instruct-v0.2"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 16000
        self.API_URI = API_URI if API_URI else "http://localhost:8091/v1"
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else "[INST]"
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else "[/INST]"
        self.STOP_STRING = STOP_STRING if STOP_STRING else "</s>"
        self.OPENAI_API_KEY = OPENAI_API_KEY
        openai.api_base = self.API_URI
        openai.api_key = OPENAI_API_KEY
        self.FAILURES = []

    def rotate_uri(self):
        self.FAILURES.append(self.API_URI)
        uri_list = self.API_URI.split(",")
        random.shuffle(uri_list)
        for uri in uri_list:
            if uri not in self.FAILURES:
                self.API_URI = uri
                openai.api_base = self.API_URI
                break

    async def inference(self, prompt, tokens: int = 0):
        prompt = f"{self.PROMPT_PREFIX}{prompt}{self.PROMPT_SUFFIX}"
        model_max_tokens = int(self.MAX_TOKENS) - tokens - 100
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        try:
            response = openai.Completion.create(
                model=self.AI_MODEL,
                prompt=prompt,
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=model_max_tokens,
                top_p=float(self.AI_TOP_P),
                n=1,
                stop=self.STOP_STRING,
                stream=False,
            )
            return response.choices[0].text
        except Exception as e:
            logging.info(f"vLLM API Error: {e}")
            if "," in self.API_URI:
                self.rotate_uri()
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(prompt=prompt, tokens=tokens)
            return str(response)
