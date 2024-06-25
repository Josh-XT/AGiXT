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
        # Breaking changes were made after g4f v0.2.6.2
        # Unable to get it to work in containers in newer versions.
        self.requirements = ["g4f==0.2.6.2"]
        self.AI_MODEL = "gpt-4o"
        self.provider = Liaobots
        self.provider_name = "Liaobots"
        self.providers = [
            {
                "name": "HuggingChat",
                "class": HuggingChat,
                "models": [
                    "HuggingFaceH4/zephyr-orpo-141b-A35b-v0.1",
                    "mistralai/Mixtral-8x7B-Instruct-v0.1",
                    "mistralai/Mistral-7B-Instruct-v0.2",
                    "openchat/openchat_3.5",
                    "meta-llama/Llama-3-70B-Instruct",
                    "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
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
                    "gpt-4o",
                    "claude-3-opus-20240229",
                    "claude-3-sonnet-20240229",
                    "gemini-pro",
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
        if self.provider_name == "Liaobots":
            self.provider.models = {
                "gpt-4o": {
                    "context": "8K",
                    "id": "gpt-4o-free",
                    "maxLength": 31200,
                    "model": "ChatGPT",
                    "name": "GPT-4o-free",
                    "provider": "OpenAI",
                    "tokenLimit": 7800,
                },
                "gemini-pro": {
                    "id": "gemini-pro",
                    "name": "Gemini-Pro",
                    "maxLength": 120000,
                    "tokenLimit": 30000,
                    "context": "32K",
                },
                "claude-3-opus-20240229": {
                    "id": "claude-3-opus-20240229",
                    "name": "Claude-3-Opus",
                    "maxLength": 800000,
                    "tokenLimit": 200000,
                    "context": "200K",
                },
                "claude-3-sonnet-20240229": {
                    "id": "claude-3-sonnet-20240229",
                    "name": "Claude-3-Sonnet",
                    "maxLength": 800000,
                    "tokenLimit": 200000,
                    "context": "200K",
                },
            }
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
