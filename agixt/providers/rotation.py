import logging
from Providers import get_providers, Providers
from typing import List, Dict, Any


class RotationProvider:
    """
    The AGiXT provider rotates between available providers to handle requested based on token limits.
    """

    def __init__(
        self,
        SMARTEST_PROVIDER: str = "anthropic",  # Can be a comma-separated list
        **kwargs,
    ):
        self.friendly_name = "AGiXT"
        self.requirements = []
        self.providers = get_providers()
        self.AGENT_SETTINGS = kwargs
        if "," in SMARTEST_PROVIDER:
            self.intelligence_tiers = SMARTEST_PROVIDER.split(",")
        else:
            self.intelligence_tiers = [SMARTEST_PROVIDER]
        self.failed_providers = set()
        self.smartest_provider = self.intelligence_tiers[0]
        self.agent_name = kwargs.get("agent_name", "AGiXT")
        self.user = kwargs.get("user", None)
        self.ApiClient = kwargs.get("ApiClient", None)

    def _get_provider_token_limits(self) -> Dict[str, int]:
        """Get token limits for all available providers."""
        provider_max_tokens = {}
        for provider in self.providers:
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
                self.providers.remove(provider)
                continue
        return provider_max_tokens

    def _filter_suitable_providers(
        self, provider_max_tokens: Dict[str, int], required_tokens: int
    ) -> Dict[str, int]:
        """Filter providers that can handle the required token count."""
        suitable = {
            provider: max_tokens
            for provider, max_tokens in provider_max_tokens.items()
            if max_tokens >= required_tokens
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
            use_smartest: Whether to try the smartest provider first

        Returns:
            Response from successful provider or error message
        """
        images = images or []

        # Remove providers that shouldn't be part of rotation
        excluded_providers = {"agixt", "rotation", "gpt4free", "default"}
        self.providers = [p for p in self.providers if p not in excluded_providers]
        for provider in self.providers:
            if provider.upper() + "_API_KEY" not in self.AGENT_SETTINGS:
                self.providers.remove(provider)
                continue
            if self.AGENT_SETTINGS[provider.upper() + "_API_KEY"] == "":
                self.providers.remove(provider)
        logging.info(f"Available providers after exclusions: {self.providers}")

        if not self.providers:
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
            # If use_smartest is True and smartest provider is available, try it first
            if (
                use_smartest
                and self.smartest_provider in suitable_providers
                and self.smartest_provider not in self.failed_providers
            ):
                provider = self.smartest_provider
            else:
                # Select provider with lowest token limit that can handle the request
                available_providers = {
                    k: v
                    for k, v in suitable_providers.items()
                    if k not in self.failed_providers
                }
                if not available_providers:
                    self.failed_providers.clear()  # Reset failed providers if all have failed
                    available_providers = suitable_providers
                provider = min(available_providers, key=available_providers.get)

            logging.info(
                f"Selected provider {provider} for inference (limit: {suitable_providers[provider]} tokens)"
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
            )  # Remove from failed providers if successful
            return result

        except Exception as e:
            logging.error(f"Provider {provider} failed with error: {str(e)}")
            self.failed_providers.add(provider)  # Add to failed providers set
            if provider in self.providers:
                self.providers.remove(provider)
                logging.info(
                    f"Removed failed provider {provider}. Remaining providers: {self.providers}"
                )
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, use_smartest=use_smartest
            )
