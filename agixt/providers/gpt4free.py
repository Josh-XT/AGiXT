import logging
import asyncio
import random
from g4f.models import ModelUtils


class Gpt4freeProvider:
    def __init__(self, AI_MODEL: str = "claude-v2", **kwargs):
        self.requirements = ["g4f"]  # Breaking changes were made after g4f v0.2.6.2
        self.AI_MODEL = AI_MODEL if AI_MODEL else "claude-v2"
        self.models = [
            "gpt-3.5-turbo",
            "mistral-7b",
            "claude-v2",
            "claude-3-sonnet",
            "claude-3-opus",
            "gemini",
            "gemini-pro",
        ]
        self.failures = []

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        try:
            model = ModelUtils.convert[self.AI_MODEL]
        except:
            model = ModelUtils.convert["claude-v2"]
        provider = model.best_provider
        if provider:
            append_model = f" and model: {model.name}" if model.name else ""
            logging.info(
                f"[Gpt4Free] Using provider: {provider.__name__}{append_model}"
            )
        try:
            return (
                await asyncio.gather(
                    provider.create_async(
                        model=model.name,
                        messages=[{"role": "user", "content": prompt}],
                    )
                )
            )[0]
        except Exception as e:
            logging.error(f"[Gpt4Free] {e}")
            self.failures.append(model.name)
            if len(self.failures) <= len(self.models):
                model_list = self.models.copy()
                # Shuffle model list so that we're not always trying the same models
                random.shuffle(model_list)
                for model in model_list:
                    if model not in self.failures:
                        logging.info(f"[Gpt4Free] Trying model: {model}")
                        self.AI_MODEL = model
                        break
                return await self.inference(prompt=prompt, tokens=tokens, images=images)
            else:
                return "Unable to retrieve response."
