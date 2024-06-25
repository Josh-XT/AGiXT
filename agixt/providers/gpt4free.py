import logging
import asyncio
import random
from g4f.Provider import (
    ChatgptNext,
    HuggingChat,
    ChatgptDemo,
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
    def __init__(self, AI_MODEL: str = "claude-v2", **kwargs):
        self.requirements = ["g4f"]  # Breaking changes were made after g4f v0.2.6.2
        self.AI_MODEL = AI_MODEL if AI_MODEL else "claude-v2"
        self.providers = [
            {
                "name": "ChatgptNext",
                "class": ChatgptNext,
                "models": [
                    "gpt-3.5-turbo",
                ],
            },
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
                "name": "ChatgptDemo",
                "class": ChatgptDemo,
                "models": [
                    "gpt-3.5-turbo",
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
        self.models = [
            "gpt-3.5-turbo",
            "claude-v2",
            "gemini",
            "gemini-pro",
        ]
        self.failures = []

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        # Provider data is a list of providers for the selected model
        provider = None
        provider_name = None
        model = None
        for p in self.providers:
            if self.AI_MODEL in p["models"]:
                # Make sure the provider is not on the failure list
                if p["name"] in [f["provider"] for f in self.failures]:
                    continue
                provider = p["class"]
                provider_name = p["name"]
                # If the provider has no models, skip it
                if p["models"] == []:
                    continue
                model = p
                break
        logging.info(f"[Gpt4Free] Using provider: {provider_name} with model: {model}")
        try:
            return (
                await asyncio.gather(
                    provider.create_async(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                )
            )[0]
        except Exception as e:
            logging.error(f"[Gpt4Free] {e}")
            self.failures.append({"provider": provider_name, "model": model})
            provider_count = len(provider_name)
            if len(self.failures) < provider_count:
                for provider in self.providers:
                    if provider_name not in self.failures:
                        provider_models = provider["models"]
                        if not isinstance(provider_models, list):
                            provider_models = [provider_models]
                        # Remove any models that have failed
                        for failure in self.failures:
                            if failure["provider"] == provider["name"]:
                                if failure["model"] in provider_models:
                                    # delete the model from the list for the provider
                                    provider_models.remove(failure["model"])
                                    self.providers[provider["name"]][
                                        "models"
                                    ] = provider_models
                        if len(provider_models) > 0:
                            # Skip this provider and try another
                            continue
                        model = random.choice(provider_models)
                        logging.info(
                            f"[Gpt4Free] Switching to provider: {provider['name']} with model: {model}"
                        )
                        self.AI_MODEL = model
                        break
                return await self.inference(prompt=prompt, tokens=tokens, images=images)
            else:
                return "Unable to retrieve response."
