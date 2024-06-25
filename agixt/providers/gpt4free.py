import logging
import asyncio
from g4f.models import ModelUtils, _all_models


class Gpt4freeProvider:
    def __init__(self, AI_MODEL: str = "gpt-3.5-turbo", **kwargs):
        self.requirements = ["g4f"]  # Breaking changes were made after g4f v0.2.6.2
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo"
        self.failures = []

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        try:
            model = ModelUtils.convert[self.AI_MODEL]
        except:
            model = ModelUtils.convert["gpt-3.5-turbo"]
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
            # Add model to failure list and try again.
            self.failures.append(model.name)
            if len(self.failures) < len(_all_models):
                for model in _all_models:
                    if model not in self.failures:
                        self.AI_MODEL = model
                        break
                return await self.inference(prompt=prompt, tokens=tokens, images=images)
            else:
                return "Unable to retrieve response."
