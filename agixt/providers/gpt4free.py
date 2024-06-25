import logging
import asyncio
import random
from g4f.Provider import (
    HuggingChat,
    GptForLove,
    ChatgptAi,
    DeepInfra,
    ChatBase,
    Liaobots,
    FreeGpt,
    GptGo,
    Gpt6,
)


class Gpt4freeProvider:
    def __init__(self, AI_MODEL: str = "gpt-3.5-turbo", **kwargs):
        self.requirements = ["g4f"]  # Breaking changes were made after g4f v0.2.6.2
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo"
        self.provider = GptForLove
        self.provider_name = "GptForLove"
        self.providers = [
            {
                "name": "HuggingChat",
                "class": HuggingChat,
                "models": [
                    "mistralai/Mixtral-8x7B-Instruct-v0.1",
                    "mistralai/Mistral-7B-Instruct-v0.1",
                    "openchat/openchat_3.5",
                    "meta-llama/Llama-2-70b-chat-hf",
                ],
            },
            {
                "name": "GptForLove",
                "class": GptForLove,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
            {
                "name": "ChatgptAi",
                "class": ChatgptAi,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
            {
                "name": "DeepInfra",
                "class": DeepInfra,
                "models": [
                    "meta-llama/Meta-Llama-3-70B-Instruct",
                    "Qwen/Qwen2-72B-Instruct",
                ],
            },
            {
                "name": "ChatBase",
                "class": ChatBase,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
            {
                "name": "Liaobots",
                "class": Liaobots,
                "models": [
                    "gpt-4",
                ],
            },
            {
                "name": "FreeGpt",
                "class": FreeGpt,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
            {
                "name": "GptGo",
                "class": GptGo,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
            {
                "name": "Gpt6",
                "class": Gpt6,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
        ]
        self.failures = []

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        # Provider data is a list of providers for the selected model
        logging.info(
            f"[Gpt4Free] Using provider: {self.provider_name} with model: {self.AI_MODEL}"
        )
        try:
            return (
                await asyncio.gather(
                    self.provider.create_async(
                        model=self.AI_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                    )
                )
            )[0]
        except Exception as e:
            logging.error(f"[Gpt4Free] {e}")
            self.failures.append(
                {"provider": self.provider_name, "model": self.AI_MODEL}
            )
            if len(self.failures) < len(self.providers):
                for provider in self.providers:
                    provider_models = provider["models"]
                    if not isinstance(provider_models, list):
                        provider_models = [provider_models]
                    # Remove any models that have failed
                    for failure in self.failures:
                        if failure["provider"] == provider["name"]:
                            if failure["model"] in provider_models:
                                # delete the model from the list for the provider
                                del provider_models[
                                    provider_models.index(failure["model"])
                                ]
                    if len(provider_models) > 0:
                        # Skip this provider and try another
                        continue
                    logging.info(
                        f"[Gpt4Free] Available models: {provider_models} for provider: {provider['name']}"
                    )
                    model = random.choice(provider_models)
                    logging.info(
                        f"[Gpt4Free] Switching to provider: {provider['name']} with model: {model}"
                    )
                    self.provider = provider["class"]
                    self.provider_name = provider["name"]
                    self.AI_MODEL = model
                    break
                return await self.inference(prompt=prompt, tokens=tokens, images=images)
            else:
                return "Unable to retrieve response."
