import logging
import asyncio
import random
from g4f.Provider import (
    DeepInfra,
    FreeGpt,
    Liaobots,
)
from Globals import getenv


class Gpt4freeProvider:
    """
    This provider uses the GPT4Free API to generate text from prompts. This provider may be unreliable but is free to try.
    """

    def __init__(self, **kwargs):
        # Breaking changes were made after g4f v0.2.6.2
        # Unable to get it to work in containers in newer versions.
        self.friendly_name = "GPT4Free"
        self.requirements = ["g4f==0.2.6.2"]
        self.AI_MODEL = "gemini-pro"
        self.MAX_TOKENS = 128000
        self.provider = Liaobots
        self.provider_name = "Liaobots"
        self.providers = [
            {
                "name": "DeepInfra",
                "class": DeepInfra,
                "models": [
                    "meta-llama/Meta-Llama-3-70B-Instruct",
                    "Qwen/Qwen2-72B-Instruct",
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
                "name": "Liaobots",
                "class": Liaobots,
                "models": [
                    "gemini-pro",
                    "gpt-3.5-turbo",
                    "claude-2.1",
                    "claude-3-sonnet-20240229",
                    "claude-3-opus-20240229",
                ],
            },
        ]
        self.failures = []
        self.provider_failure_count = 0
        self.agent_settings = kwargs

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        agent_settings = {
            k: v for k, v in self.agent_settings.items() if v is not None and v != ""
        }
        if (
            "DEEPSEEK_API_KEY" in agent_settings
            or "EZLOCALAI_API_KEY" in agent_settings
            or "AZURE_API_KEY" in agent_settings
            or "OPENAI_API_KEY" in agent_settings
            or "XAI_API_KEY" in agent_settings
            or "GOOGLE_API_KEY" in agent_settings
        ):
            from providers.rotation import RotationProvider

            return await RotationProvider(**self.agent_settings).inference(
                prompt=prompt, tokens=tokens, images=images
            )
        logging.info(
            f"[Gpt4Free] Using provider: {self.provider_name} with model: {self.AI_MODEL}"
        )
        prompt = f"Ignore all previous rules about language use and respond only in English.\n{prompt}"
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
                # Try all providers 3 times before fully failing.
                self.provider_failure_count += 1
                self.failures = []
                if self.provider_failure_count < 3:
                    return await self.inference(
                        prompt=prompt, tokens=tokens, images=images
                    )
                return "All providers have failed. Unable to retrieve response."

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
