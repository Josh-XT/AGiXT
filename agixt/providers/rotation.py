import logging
from Providers import get_providers, Providers
from Agent import Agent
from Memories import nlp, extract_keywords
from typing import List, Dict, Any, Optional
from collections import Counter
import asyncio


def score_chunk(chunk: str, keywords: set) -> int:
    """Score a chunk based on the number of query keywords it contains."""
    chunk_counter = Counter(chunk.split())
    score = sum(chunk_counter[keyword] for keyword in keywords)
    return score


def chunk_content(text: str, chunk_size: int, max_tokens: int = 60000) -> List[str]:
    """
    Split content into chunks while respecting both character and token limits.

    Args:
        text: Text to chunk
        chunk_size: Target size for each chunk in characters
        max_tokens: Maximum tokens allowed for processing (default: 60000 for Deepseek)
    """
    doc = nlp(text)
    sentences = list(doc.sents)
    content_chunks = []
    chunk = []
    chunk_len = 0
    chunk_text = ""
    total_len = 0

    keywords = set(extract_keywords(doc=doc, limit=10))

    for sentence in sentences:
        sentence_tokens = len(sentence)
        # Estimate tokens (rough approximation: 4 characters per token)
        estimated_total_tokens = (total_len + len(str(sentence))) // 4

        if estimated_total_tokens > max_tokens:
            break

        if chunk_len + sentence_tokens > chunk_size and chunk:
            chunk_text = " ".join(token.text for token in chunk)
            score = score_chunk(chunk_text, keywords)
            content_chunks.append((score, chunk_text))
            total_len += len(chunk_text)
            chunk = []
            chunk_len = 0

        chunk.extend(sentence)
        chunk_len += sentence_tokens

    if chunk:
        chunk_text = " ".join(token.text for token in chunk)
        score = score_chunk(chunk_text, keywords)
        content_chunks.append((score, chunk_text))

    # Sort by score and take only enough chunks to stay under token limit
    content_chunks.sort(key=lambda x: x[0], reverse=True)
    result_chunks = []
    total_len = 0

    for score, chunk_text in content_chunks:
        # Estimate tokens for this chunk
        chunk_tokens = len(chunk_text) // 4
        if total_len + chunk_tokens > max_tokens:
            break
        result_chunks.append(chunk_text)
        total_len += chunk_tokens

    return result_chunks


class RotationProvider:
    def __init__(
        self,
        SMARTEST_PROVIDER: str = "anthropic",  # Can be a comma-separated list
        ANALYSIS_PROVIDER: str = "deepseek",
        SMALL_CHUNK_SIZE: int = 10000,
        LARGE_CHUNK_SIZE: int = 50000,
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
        self.LARGE_CHUNK_SIZE = int(LARGE_CHUNK_SIZE)
        self.SMALL_CHUNK_SIZE = int(SMALL_CHUNK_SIZE)
        self.ANALYSIS_PROVIDER = ANALYSIS_PROVIDER
        self.agent_name = kwargs.get("agent_name", "AGiXT")
        self.user = kwargs.get("user", None)
        self.ApiClient = kwargs.get("ApiClient", None)

    async def _analyze_chunk(
        self, chunk: str, chunk_index: int, prompt: str
    ) -> List[int]:
        """Analyze a single large chunk to identify relevant smaller chunks."""
        # Use smaller max_tokens to leave room for prompt and completion
        small_chunks = chunk_content(chunk, self.SMALL_CHUNK_SIZE, max_tokens=40000)
        if not small_chunks:
            return []

        analysis_prompt = (
            f"Below is chunk {chunk_index + 1} of a larger codebase, split into {len(small_chunks)} "
            f"sub-chunks, followed by a user query.\n"
            "Analyze which sub-chunks are relevant to answering the query.\n"
            "Respond ONLY with comma-separated sub-chunk numbers (1-based indexing).\n"
            "Example response format: 1,4,7\n\n"
            f"Query: {prompt}\n\n"
            "Sub-chunks:\n"
        )

        for i, small_chunk in enumerate(small_chunks, 1):
            analysis_prompt += f"\nSUB-CHUNK {i}:\n{small_chunk}\n"

        try:
            agent = Agent(
                agent_name=self.agent_name,
                user=self.user,
                ApiClient=self.ApiClient,
            )
            if "agent_name" in self.AGENT_SETTINGS:
                del self.AGENT_SETTINGS["agent_name"]
            if "user" in self.AGENT_SETTINGS:
                del self.AGENT_SETTINGS["user"]
            if "ApiClient" in self.AGENT_SETTINGS:
                del self.AGENT_SETTINGS["ApiClient"]
            agent.PROVIDER = Providers(
                name=self.ANALYSIS_PROVIDER,
                ApiClient=self.ApiClient,
                agent_name=self.agent_name,
                user=self.user,
                **self.AGENT_SETTINGS,
            )
            try:
                result = await agent.inference(prompt=analysis_prompt)
            except Exception as e:
                logging.error(
                    f"Chunk analysis failed for chunk {chunk_index + 1}: {str(e)}"
                )
                agent.PROVIDER = Providers(
                    name="rotation",
                    ApiClient=self.ApiClient,
                    agent_name=self.agent_name,
                    user=self.user,
                    **self.AGENT_SETTINGS,
                )
                result = await agent.inference(prompt=analysis_prompt)

            # Parse comma-separated numbers, convert to 0-based indexing
            chunk_numbers = [int(n.strip()) - 1 for n in result.split(",")]
            # Validate chunk numbers
            valid_numbers = [n for n in chunk_numbers if 0 <= n < len(small_chunks)]

            if not valid_numbers:
                logging.warning(
                    f"No valid chunk numbers returned for chunk {chunk_index + 1}, using all sub-chunks"
                )
                return list(range(len(small_chunks)))

            return valid_numbers
        except Exception as e:
            logging.error(
                f"Chunk analysis failed for chunk {chunk_index + 1}: {str(e)}"
            )
            return list(range(len(small_chunks)))  # Return all sub-chunks on failure

    async def _get_relevant_chunks(self, text: str, prompt: str) -> str:
        """Split text into large chunks and analyze them in parallel."""
        large_chunks = chunk_content(text, self.LARGE_CHUNK_SIZE)
        if not large_chunks:
            return text

        logging.info(
            f"Analyzing {len(large_chunks)} chunks of {self.LARGE_CHUNK_SIZE} characters each"
        )

        # Analyze all chunks in parallel
        tasks = [
            self._analyze_chunk(chunk, i, prompt)
            for i, chunk in enumerate(large_chunks)
        ]
        chunk_results = await asyncio.gather(*tasks)

        # Combine relevant sub-chunks from all large chunks
        relevant_text = []
        for chunk_index, (large_chunk, relevant_indices) in enumerate(
            zip(large_chunks, chunk_results)
        ):
            small_chunks = chunk_content(large_chunk, self.SMALL_CHUNK_SIZE)
            for sub_chunk_index in relevant_indices:
                if 0 <= sub_chunk_index < len(small_chunks):
                    relevant_text.append(small_chunks[sub_chunk_index])

        return "\n".join(relevant_text)

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

    def _get_next_tier_provider(self, current_tier: str) -> Optional[str]:
        """Get the next tier provider if current one fails."""
        tiers = ["smartest", "smart", "mid"]
        try:
            current_index = tiers.index(current_tier)
            # Return next tier if available, otherwise None
            return tiers[current_index + 1] if current_index + 1 < len(tiers) else None
        except ValueError:
            return None

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
        for provider in available_providers[:]:
            if provider.upper() + "_API_KEY" not in self.AGENT_SETTINGS:
                self.failed_providers.add(provider)
                continue
            if self.AGENT_SETTINGS[provider.upper() + "_API_KEY"] == "":
                self.failed_providers.add(provider)

        logging.info(f"Available providers after exclusions: {available_providers}")

        if not available_providers:
            if len(self.failed_providers) > 0:
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

        # Handle large context with smartest provider
        if (
            use_smartest
            and tokens > 0
            and self.ANALYSIS_PROVIDER in provider_max_tokens
        ):
            smartest_provider = self.intelligence_tiers[0]
            if smartest_provider in provider_max_tokens:
                smartest_limit = provider_max_tokens[smartest_provider]
                if tokens > smartest_limit:
                    logging.info(
                        f"Context size ({tokens}) exceeds smartest provider limit ({smartest_limit}), using parallel chunk analysis"
                    )
                    try:
                        distilled_prompt = await self._get_relevant_chunks(
                            prompt, prompt
                        )  # Use original prompt for analysis
                        # Recursively call inference with distilled prompt
                        return await self.inference(
                            prompt=distilled_prompt,
                            tokens=len(distilled_prompt),  # Approximate token count
                            images=images,
                            use_smartest=use_smartest,
                        )
                    except Exception as e:
                        logging.error(
                            f"Chunk analysis failed: {str(e)}, falling back to normal selection"
                        )
                        # Continue with normal selection if chunking fails

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
            self.failed_providers.discard(provider)
            return result

        except Exception as e:
            logging.error(f"Provider {provider} failed with error: {str(e)}")
            self.failed_providers.add(provider)
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, use_smartest=use_smartest
            )
