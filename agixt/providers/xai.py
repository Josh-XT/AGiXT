import time
import logging

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai


class XaiProvider:
    """
    This provider uses the xAI API to generate text from prompts. Get your xAI API key at <https://docs.x.ai/docs#getting-started>.
    """

    friendly_name = "xAI"

    def __init__(
        self,
        XAI_API_KEY: str = "",
        XAI_MODEL: str = "grok-beta",
        XAI_API_URI: str = "https://api.x.ai/v1/",
        XAI_MAX_TOKENS: int = 128000,
        XAI_TEMPERATURE: float = 0.7,
        XAI_TOP_P: float = 0.7,
        XAI_WAIT_BETWEEN_REQUESTS: int = 1,
        XAI_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = XAI_MODEL if XAI_MODEL else "grok-beta"
        self.AI_TEMPERATURE = XAI_TEMPERATURE if XAI_TEMPERATURE else 0.7
        self.AI_TOP_P = XAI_TOP_P if XAI_TOP_P else 0.7
        self.MAX_TOKENS = XAI_MAX_TOKENS if XAI_MAX_TOKENS else 128000
        self.API_URI = XAI_API_URI if XAI_API_URI else "https://api.x.ai/v1/"
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        self.WAIT_AFTER_FAILURE = (
            XAI_WAIT_AFTER_FAILURE if XAI_WAIT_AFTER_FAILURE else 3
        )
        self.WAIT_BETWEEN_REQUESTS = (
            XAI_WAIT_BETWEEN_REQUESTS if XAI_WAIT_BETWEEN_REQUESTS else 1
        )
        self.XAI_API_KEY = XAI_API_KEY
        self.FAILURES = []
        self.failures = 0

    @staticmethod
    def services():
        return [
            "llm",
            "vision",
        ]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        openai.base_url = self.API_URI if self.API_URI else "https://api.x.ai/v1/"
        openai.api_key = f"Bearer {self.XAI_API_KEY}"
        openai.api_type = "openai"
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
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{file_type};base64,{image_base64}"
                            },
                        }
                    )
        else:
            messages.append({"role": "user", "content": prompt})

        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        try:
            response = openai.chat.completions.create(
                model=self.AI_MODEL,
                messages=messages,
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=4096,
                top_p=float(self.AI_TOP_P),
                n=1,
                stream=False,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.info(f"xAI API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"xAI API Error: Too many failures. {e}")
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(prompt=prompt, tokens=tokens)
            return str(response)
