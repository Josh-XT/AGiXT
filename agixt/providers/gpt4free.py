import logging
import asyncio
from g4f.Provider import RetryProvider
from g4f.models import ModelUtils


class Gpt4freeProvider:
    def __init__(self, AI_MODEL: str = "gemini-pro", **kwargs):
        self.requirements = ["g4f"]  # Breaking changes were made after g4f v0.2.6.2
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gemini-pro"

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        try:
            model = ModelUtils.convert[self.AI_MODEL]
        except:
            model = ModelUtils.convert["gemini-pro"]
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
            raise e
        finally:
            if provider and isinstance(provider, RetryProvider):
                if hasattr(provider, "exceptions"):
                    for provider_name in provider.exceptions:
                        error = provider.exceptions[provider_name]
                        logging.error(f"[Gpt4Free] {provider_name}: {error}")
