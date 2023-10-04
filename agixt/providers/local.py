import openai
import time
import logging
import requests


class LocalProvider:
    def __init__(
        self,
        LOCAL_API_KEY: str = "",
        AI_MODEL: str = "TheBloke/Mistral-7B-OpenOrca-GGUF",
        API_URI: str = "https://localhost:8091/v1",
        MAX_TOKENS: int = 8192,
        AI_TEMPERATURE: float = 1.31,
        AI_TOP_P: float = 1.0,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "TheBloke/Mistral-7B-OpenOrca-GGUF"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 1.31
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 1.0
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 8192
        self.API_URI = API_URI if API_URI else "https://localhost:8091/v1"
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.stream = False
        openai.api_base = self.API_URI
        openai.api_key = LOCAL_API_KEY

    def models(self):
        models = requests.get("http://localhost:8091/v1/models")
        return models.json()

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        try:
            response = openai.Completion.create(
                model=self.AI_MODEL,
                prompt=prompt,
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=max_new_tokens,
                top_p=float(self.AI_TOP_P),
            )
            return response.choices[0].text.strip()
        except Exception as e:
            logging.info(f"Local-LLM API Error: {e}")
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.instruct(prompt=prompt, tokens=tokens)
            return str(response)
