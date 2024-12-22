import logging
from Providers import Providers
from typing import List, Any

# The coding provider will let users choose to offload coding tasks to a different provider
# The user defines their default provider, then they define their coding provider
# For example, default provider could be OpenAI, and coding provider could be Anthropic


class CodingProvider:
    def __init__(
        self,
        default_provider: str = "gpt4free",
        coding_provider: str = "gpt4free",
        **kwargs,
    ):
        self.requirements = []
        self.default_provider = str(default_provider).lower()
        # A good idea would be to use the rotation provider as the default, then Anthropic as the coding provider
        self.coding_provider = str(coding_provider).lower()
        self.AGENT_SETTINGS = kwargs

    @staticmethod
    def services():
        return [
            "llm",
            "vision",
        ]

    async def inference(
        self, prompt: str, tokens: int = 0, images: List[Any] = None
    ) -> str:
        images = images or []

        try:
            # If there is code in the prompt, offload to coding provider
            if "```" in prompt:
                provider = self.coding_provider
            else:
                provider = self.default_provider
            # Try inference
            provider_instance = Providers(
                name=provider,
                **self.AGENT_SETTINGS,
            )
            return await provider_instance.inference(
                prompt=prompt, tokens=tokens, images=images
            )

        except Exception as e:
            logging.error(f"Provider {provider} failed with error: {str(e)}")
            try:
                if provider == self.default_provider:
                    logging.error("Attempting to use backup provider")
                    provider = self.coding_provider
                    provider_instance = Providers(
                        name=provider,
                        **self.AGENT_SETTINGS,
                    )
                    return await provider_instance.inference(
                        prompt=prompt, tokens=tokens, images=images
                    )
                else:
                    logging.error(
                        "Coding provider failed, attempting to use default provider"
                    )
                    provider = self.default_provider
                    provider_instance = Providers(
                        name=provider,
                        **self.AGENT_SETTINGS,
                    )
                    return await provider_instance.inference(
                        prompt=prompt, tokens=tokens, images=images
                    )
            except Exception as e:
                logging.error(f"Provider {provider} failed with error: {str(e)}")
                return "Failed to generate response"
