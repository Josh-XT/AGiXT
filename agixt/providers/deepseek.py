import time
import logging

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai


class DeepseekProvider:
    """
    This provider uses the Deepseek API to generate text from prompts. Get your Deepseek API key at <https://platform.deepseek.com/>.
    """

    def __init__(
        self,
        DEEPSEEK_API_KEY: str = "",
        DEEPSEEK_MODEL: str = "deepseek-chat",
        DEEPSEEK_API_URI: str = "https://api.deepseek.com/",
        DEEPSEEK_MAX_TOKENS: int = 64000,
        DEEPSEEK_TEMPERATURE: float = 0.1,
        DEEPSEEK_TOP_P: float = 0.95,
        DEEPSEEK_WAIT_BETWEEN_REQUESTS: int = 0,
        DEEPSEEK_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.friendly_name = "Deepseek"
        self.requirements = ["openai"]
        self.AI_MODEL = DEEPSEEK_MODEL if DEEPSEEK_MODEL else "deepseek-chat"
        self.AI_TEMPERATURE = DEEPSEEK_TEMPERATURE if DEEPSEEK_TEMPERATURE else 0.1
        self.AI_TOP_P = DEEPSEEK_TOP_P if DEEPSEEK_TOP_P else 0.95
        self.MAX_TOKENS = DEEPSEEK_MAX_TOKENS if DEEPSEEK_MAX_TOKENS else 64000
        self.API_URI = (
            DEEPSEEK_API_URI if DEEPSEEK_API_URI else "https://api.deepseek.com/"
        )
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        self.WAIT_AFTER_FAILURE = (
            DEEPSEEK_WAIT_AFTER_FAILURE if DEEPSEEK_WAIT_AFTER_FAILURE else 3
        )
        self.WAIT_BETWEEN_REQUESTS = (
            DEEPSEEK_WAIT_BETWEEN_REQUESTS if DEEPSEEK_WAIT_BETWEEN_REQUESTS else 1
        )
        self.DEEPSEEK_API_KEY = DEEPSEEK_API_KEY
        self.FAILURES = []
        self.failures = 0

    @staticmethod
    def services():
        return [
            "llm",
            "vision",
        ]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        openai.base_url = self.API_URI if self.API_URI else "https://api.deepseek.com/"
        openai.api_key = self.DEEPSEEK_API_KEY
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
            logging.info(f"Deepseek API Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"Deepseek API Error: Too many failures. {e}")
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(prompt=prompt, tokens=tokens)
            return str(response)
