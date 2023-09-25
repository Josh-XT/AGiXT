import logging
import asyncio

from g4f.Provider import RetryProvider
from g4f.models import ModelUtils, gpt_35_turbo, default


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = gpt_35_turbo.name,
        MAX_TOKENS: int = 4096,
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["g4f", "httpx"]
        if not AI_MODEL:
            self.AI_MODEL = default
        elif AI_MODEL in ModelUtils.convert:
            self.AI_MODEL = ModelUtils.convert[AI_MODEL]
        else:
            raise ValueError(f"Model not found: {AI_MODEL}")
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = (
            int(self.MAX_TOKENS) - int(tokens) if tokens > 0 else self.MAX_TOKENS
        )
        model = self.AI_MODEL
        provider = model.best_provider
        if provider:
            append_model = f" and model: {model.name}" if model.name else ""
            logging.info(f"[Gpt4Free] Use provider: {provider.__name__}{append_model}")
        try:
            return (
                await asyncio.gather(
                    provider.create_async(
                        model=model.name,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_new_tokens,
                        temperature=float(self.AI_TEMPERATURE),
                        top_p=float(self.AI_TOP_P),
                    ),
                    asyncio.sleep(int(self.WAIT_BETWEEN_REQUESTS)),
                )
            )[0]
        except Exception as e:
            if int(self.WAIT_AFTER_FAILURE) > 0:
                await asyncio.sleep(int(self.WAIT_AFTER_FAILURE))
            raise e
        finally:
            if provider and isinstance(provider, RetryProvider):
                if hasattr(provider, "exceptions"):
                    for provider_name in provider.exceptions:
                        error = provider.exceptions[provider_name]
                        logging.error(f"[Gpt4Free] {provider_name}: {error}")


if __name__ == "__main__":
    import asyncio, time

    async def run_test():
        petal = Gpt4freeProvider()
        start = time.time()
        response = await petal.instruct("What is the meaning of life?")
        print(response)
        print(f"{round(time.time()-start, 2)} secs")

    asyncio.run(run_test())
