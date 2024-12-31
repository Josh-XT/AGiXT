import logging
from Providers import get_providers, Providers
from typing import List, Dict, Any


class RotationProvider:
    def __init__(
        self,
        SMARTEST_PROVIDER: str = "anthropic",  # Can be a comma-separated list
        **kwargs,
    ):
        self.requirements = []
        self.providers = get_providers()
        self.AGENT_SETTINGS = kwargs
        if "," in SMARTEST_PROVIDER:
            self.intelligence_tiers = SMARTEST_PROVIDER.split(",")
        else:
            self.intelligence_tiers = [SMARTEST_PROVIDER]
        self.failed_providers = set()

    @staticmethod
    def services():
        return [
            "llm",
            "vision",
        ]

    def _get_provider_token_limits(self) -> Dict[str, int]:
        """Get token limits for all available providers."""
        provider_max_tokens = {}
        for provider in self.providers:
            if provider in self.failed_providers:
                continue
            setting_key = f"{provider.upper()}_MAX_TOKENS"
            try:
                if setting_key in self.AGENT_SETTINGS:
                    provider_max_tokens[provider] = int(
                        self.AGENT_SETTINGS[setting_key]
                    )
                    logging.info(
                        f"Provider {provider} has max token limit: {provider_max_tokens[provider]}"
                    )
            except:
                self.failed_providers.add(provider)
                continue
        return provider_max_tokens

    def _filter_suitable_providers(
        self, provider_max_tokens: Dict[str, int], required_tokens: int
    ) -> Dict[str, int]:
        """Filter providers that can handle the required token count."""
        suitable = {
            provider: max_tokens
            for provider, max_tokens in provider_max_tokens.items()
            if max_tokens >= required_tokens and provider not in self.failed_providers
        }
        logging.info(
            f"Input requires {required_tokens} tokens. Suitable providers: {list(suitable.keys())}"
        )
        return suitable

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: List[Any] = None,
        use_smartest: bool = False,
    ) -> str:
        """
        Attempt inference using providers with sufficient token limits.

        Args:
            prompt: The input prompt
            tokens: Required token count (0 if unknown)
            images: List of images for vision tasks
            use_smartest: Whether to try providers in order of intelligence

        Returns:
            Response from successful provider or error message
        """
        images = images or []

        # Remove providers that shouldn't be part of rotation
        excluded_providers = {"agixt", "rotation", "gpt4free", "default"}
        available_providers = [
            p
            for p in self.providers
            if p not in excluded_providers and p not in self.failed_providers
        ]

        # Filter out providers without API keys
        for provider in available_providers[:]:  # Create a copy to iterate over
            if provider.upper() + "_API_KEY" not in self.AGENT_SETTINGS:
                self.failed_providers.add(provider)
                continue
            if self.AGENT_SETTINGS[provider.upper() + "_API_KEY"] == "":
                self.failed_providers.add(provider)

        logging.info(f"Available providers after exclusions: {available_providers}")

        if not available_providers:
            if len(self.failed_providers) > 0:
                # Reset failed providers and try again
                logging.info("All providers failed, resetting failed providers list")
                self.failed_providers.clear()
                return await self.inference(
                    prompt=prompt,
                    tokens=tokens,
                    images=images,
                    use_smartest=use_smartest,
                )
            logging.error("No providers available for inference")
            return "Unable to process request. No providers available."

        # Get provider token limits
        provider_max_tokens = self._get_provider_token_limits()

        # Filter providers that can handle the token count
        if tokens > 0:
            suitable_providers = self._filter_suitable_providers(
                provider_max_tokens, tokens
            )
            if not suitable_providers:
                logging.error(f"No providers can handle input size of {tokens} tokens")
                return (
                    f"Unable to process request. Input size ({tokens} tokens) exceeds "
                    "all provider limits. Please reduce input size."
                )
        else:
            suitable_providers = provider_max_tokens
            logging.info("Token count not specified, all providers considered suitable")

        try:
            # Select provider based on intelligence tiers if use_smartest is True
            if use_smartest:
                # Try each tier in order until we find an available provider
                for tier_provider in self.intelligence_tiers:
                    if (
                        tier_provider in suitable_providers
                        and tier_provider not in self.failed_providers
                    ):
                        provider = tier_provider
                        break
                else:
                    # If no tier provider is available, fall back to token-based selection
                    provider = min(suitable_providers, key=suitable_providers.get)
            else:
                # Use token-based selection
                provider = min(suitable_providers, key=suitable_providers.get)

            logging.info(
                f"Selected provider {provider} for inference "
                f"(limit: {suitable_providers[provider]} tokens)"
            )

            # Try inference
            provider_instance = Providers(
                name=provider,
                **self.AGENT_SETTINGS,
            )
            result = await provider_instance.inference(
                prompt=prompt, tokens=tokens, images=images
            )
            self.failed_providers.discard(
                provider
            )  # Provider succeeded, remove from failed list
            return result

        except Exception as e:
            logging.error(f"Provider {provider} failed with error: {str(e)}")
            self.failed_providers.add(provider)
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, use_smartest=use_smartest
            )
