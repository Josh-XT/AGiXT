import logging

import g4f


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4000,
        **kwargs,
    ):
        self.requirements = ["gpt4free"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS

    async def instruct(self, prompt, tokens: int = 0):
        try:
            return g4f.ChatCompletion.create(model=g4f.Model.gpt_35_turbo, messages=[
                {"role": "user", "content": prompt}])
        except Exception as e:
            logging.error(f"[GPT4Free] Exception: {e}")
