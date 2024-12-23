import logging
from Providers import Providers
from typing import List, Any
import re

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
        self.coding_provider = str(coding_provider).lower()
        self.AGENT_SETTINGS = kwargs

        # Common coding keywords and patterns
        self.code_indicators = {
            "symbols": set(["()", "{}", "[]", "=>", "->", ";"]),
            "keywords": set(
                [
                    "function",
                    "class",
                    "def",
                    "return",
                    "import",
                    "const",
                    "let",
                    "var",
                    "async",
                    "await",
                    "public",
                    "private",
                    "protected",
                    "static",
                ]
            ),
            "file_extensions": set(
                [
                    ".py",
                    ".js",
                    ".java",
                    ".cpp",
                    ".cs",
                    ".php",
                    ".rb",
                    ".go",
                    ".ts",
                    ".sql",
                    ".html",
                    ".css",
                ]
            ),
        }

    def is_coding_task(self, prompt: str) -> bool:
        """
        Determines if the given prompt is likely a coding-related task.

        Args:
            prompt (str): The user's input prompt

        Returns:
            bool: True if the prompt appears to be coding-related
        """
        # Convert to lowercase for case-insensitive matching
        lower_prompt = prompt.lower()

        # Check for code blocks
        if "```" in prompt or "'''" in prompt:
            return True

        # Check for file extension mentions
        for ext in self.code_indicators["file_extensions"]:
            if ext in lower_prompt:
                return True

        # Look for common coding symbols patterns
        symbol_count = sum(
            1 for symbol in self.code_indicators["symbols"] if symbol in prompt
        )
        if symbol_count >= 2:  # Multiple coding symbols suggest code
            return True

        # Check for coding keywords
        keyword_count = sum(
            1
            for keyword in self.code_indicators["keywords"]
            if re.search(rf"\b{keyword}\b", lower_prompt)
        )
        if keyword_count >= 2:  # Multiple keywords suggest code
            return True

        # Check for specific coding-related phrases
        coding_phrases = [
            "write (a |the )?code",
            "implement",
            "function",
            "algorithm",
            "debug",
            "compile",
            "programming",
            "syntax",
            "code review",
        ]
        if any(re.search(phrase, lower_prompt) for phrase in coding_phrases):
            return True

        # Look for indentation patterns (common in code)
        lines = prompt.split("\n")
        if len(lines) > 2:
            indented_lines = sum(
                1 for line in lines if line.startswith("    ") or line.startswith("\t")
            )
            if indented_lines >= 2:
                return True

        return False

    async def inference(
        self, prompt: str, tokens: int = 0, images: List[Any] = None
    ) -> str:
        images = images or []

        try:
            # Use the new method to determine provider
            provider = (
                self.coding_provider
                if self.is_coding_task(prompt)
                else self.default_provider
            )

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
                # Fallback logic remains the same
                if provider == self.default_provider:
                    logging.error("Attempting to use backup provider")
                    provider = self.coding_provider
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
