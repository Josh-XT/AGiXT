import logging
import re

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai
from Globals import getenv


class OpenrouterProvider:
    """
    This provider uses the OpenRouter API to access a wide variety of AI models. Get your API key at <https://openrouter.ai/keys>.
    """

    friendly_name = "OpenRouter"

    def __init__(
        self,
        OPENROUTER_API_KEY: str = "",
        OPENROUTER_API_URI: str = "https://openrouter.ai/api/v1/",
        OPENROUTER_AI_MODEL: str = "openai/gpt-4o",
        OPENROUTER_CODING_MODEL: str = "anthropic/claude-sonnet-4",
        OPENROUTER_MAX_TOKENS: int = 16384,
        OPENROUTER_TEMPERATURE: float = 0.7,
        OPENROUTER_TOP_P: float = 0.95,
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = OPENROUTER_AI_MODEL if OPENROUTER_AI_MODEL else "openai/gpt-4o"
        self.MAX_TOKENS = OPENROUTER_MAX_TOKENS if OPENROUTER_MAX_TOKENS else 16384
        self.OPENROUTER_CODING_MODEL = (
            OPENROUTER_CODING_MODEL
            if OPENROUTER_CODING_MODEL
            else "anthropic/claude-sonnet-4"
        )
        if not OPENROUTER_API_URI.endswith("/"):
            OPENROUTER_API_URI += "/"
        self.API_URI = (
            OPENROUTER_API_URI
            if OPENROUTER_API_URI
            else "https://openrouter.ai/api/v1/"
        )
        self.AI_TEMPERATURE = OPENROUTER_TEMPERATURE if OPENROUTER_TEMPERATURE else 0.7
        self.AI_TOP_P = OPENROUTER_TOP_P if OPENROUTER_TOP_P else 0.95
        self.OPENROUTER_API_KEY = (
            OPENROUTER_API_KEY if OPENROUTER_API_KEY else getenv("OPENROUTER_API_KEY")
        )
        self.FAILURES = []
        self.failure_count = 0
        self.chunk_size = 1024

    @staticmethod
    def services():
        return [
            "llm",
            "vision",
        ]

    async def inference(
        self,
        prompt,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ):
        if not self.AI_MODEL:
            self.AI_MODEL = "openai/gpt-4o"
        if use_smartest:
            self.AI_MODEL = self.OPENROUTER_CODING_MODEL
        # Always use MAX_TOKENS for output limit - 'tokens' param is input count for budgeting
        max_tokens = int(self.MAX_TOKENS)

        import httpx
        from openai import OpenAI

        client = OpenAI(
            base_url=self.API_URI,
            api_key=self.OPENROUTER_API_KEY,
            timeout=httpx.Timeout(300.0, read=300.0, write=30.0, connect=10.0),
            default_headers={
                "HTTP-Referer": getenv("AGIXT_URI"),
                "X-Title": "AGiXT",
            },
        )
        messages = []
        if len(images) > 0:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            )
            for image in images:
                if image.startswith("http"):
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image,
                            },
                        }
                    )
                else:
                    file_type = image.split(".")[-1]
                    with open(image, "rb") as f:
                        image_base64 = f.read()
                    import base64

                    encoded_image = base64.b64encode(image_base64).decode("utf-8")
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{file_type};base64,{encoded_image}"
                            },
                        }
                    )
        else:
            messages.append({"role": "user", "content": prompt})
        try:
            response = client.chat.completions.create(
                model=self.AI_MODEL,
                messages=messages,
                max_tokens=int(max_tokens),
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
                n=1,
                stream=stream,
            )

            if stream:
                # Return the raw OpenAI Stream - AGiXT's iterate_stream helper
                # will wrap it in a thread to consume it safely without blocking
                return response
            else:
                if not isinstance(response, str):
                    response = response.choices[0].message.content
                if "User:" in response:
                    response = response.split("User:")[0]
                response = response.lstrip()
                response.replace("<s>", "").replace("</s>", "")
                return response
        except Exception as e:
            self.failure_count += 1
            logging.info(f"OpenRouter API Error: {e}")
            if self.failure_count >= 3:
                logging.info("OpenRouter failed 3 times, unable to proceed.")
                raise Exception(f"OpenRouter API Error: Too many failures. {e}")
            return await self.inference(
                prompt=prompt, tokens=tokens, images=images, stream=stream
            )
