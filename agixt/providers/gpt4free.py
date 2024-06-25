import logging
import asyncio
import random
from g4f.Provider import (
    HuggingChat,
    DeepInfra,
    Liaobots,
    FreeGpt,
    GptGo,
)


class Gpt4freeProvider:
    def __init__(self, AI_MODEL: str = "gpt-3.5-turbo", **kwargs):
        self.requirements = ["g4f"]  # Breaking changes were made after g4f v0.2.6.2
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo"
        self.provider = FreeGpt
        self.provider_name = "FreeGpt"
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
                "name": "DeepInfra",
                "class": DeepInfra,
                "models": [
                    "meta-llama/Meta-Llama-3-70B-Instruct",
                    "Qwen/Qwen2-72B-Instruct",
                ],
            },
            {
                "name": "Liaobots",
                "class": Liaobots,
                "models": [
                    "claude-3.5-sonnet",
                    "gpt-4o",
                    "gpt-4o-free",
                    "gpt-4-turbo",
                    "claude-3-opus",
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
        ]
        self.failures = []

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
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
                available_providers = self.get_available_providers()
                if available_providers:
                    provider = random.choice(available_providers)
                    self.provider = provider["class"]
                    self.provider_name = provider["name"]
                    self.AI_MODEL = random.choice(provider["models"])
                    logging.info(
                        f"[Gpt4Free] Switching to provider: {self.provider_name} with model: {self.AI_MODEL}"
                    )
                    return await self.inference(
                        prompt=prompt, tokens=tokens, images=images
                    )
                else:
                    return "No available providers. Unable to retrieve response."
            else:
                return "All providers exhausted. Unable to retrieve response."

    def get_available_providers(self):
        available_providers = []
        for provider in self.providers:
            provider_models = provider["models"]
            if not isinstance(provider_models, list):
                provider_models = [provider_models]
            # Remove any models that have failed
            available_models = [
                model
                for model in provider_models
                if not any(
                    failure["provider"] == provider["name"]
                    and failure["model"] == model
                    for failure in self.failures
                )
            ]
            if available_models:
                provider_copy = provider.copy()
                provider_copy["models"] = available_models
                available_providers.append(provider_copy)
        return available_providers
