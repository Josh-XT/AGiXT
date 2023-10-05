from local_llm import LLM
import logging
import os


class LocalProvider:
    def __init__(
        self,
        AI_MODEL: str = "Mistral-7B-OpenOrca",
        AI_TEMPERATURE: float = 1.31,
        AI_TOP_P: float = 1.0,
        **kwargs,
    ):
        self.requirements = ["local-llm"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "Mistral-7B-OpenOrca"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 1.31
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 1.0

    def models(self):
        return LLM().models()

    async def instruct(self, prompt, tokens: int = 0):
        models_dir = os.path.join(os.getcwd(), "models")
        try:
            response = LLM(
                models_dir=models_dir,
                model=self.AI_MODEL,
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
            ).completion(
                prompt=prompt,
            )
            return response["choices"][0]["text"]
        except Exception as e:
            logging.error(f"Local-LLM Error: {e}")
            return "Unable to communicate with Local-LLM."
