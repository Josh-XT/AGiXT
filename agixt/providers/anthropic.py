try:
    import anthropic
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic"])
    import anthropic
import httpx
import base64
import logging
import time


# List of models available at https://docs.anthropic.com/claude/docs/models-overview
# Get API key at https://console.anthropic.com/settings/keys
class AnthropicProvider:
    """
    This provider uses the Anthropic API to generate text from prompts. Get your Anthroic API key at <https://console.anthropic.com/settings/keys>.
    """

    def __init__(
        self,
        ANTHROPIC_API_KEY: str = "",
        ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20240620",
        ANTHROPIC_MAX_TOKENS: int = 200000,
        ANTHROPIC_TEMPERATURE: float = 0.7,
        ANTHROPIC_GOOGLE_VERTEX_REGION: str = "europe-west1",
        ANTHROPIC_GOOGLE_VERTEX_PROJECT_ID: str = "",  # Leave empty if using Anthropic service
        ANTHROPIC_WAIT_BETWEEN_REQUESTS: int = 1,
        **kwargs,
    ):
        self.friendly_name = "Anthropic"
        self.ANTHROPIC_API_KEY = ANTHROPIC_API_KEY
        self.MAX_TOKENS = ANTHROPIC_MAX_TOKENS if ANTHROPIC_MAX_TOKENS else 200000
        self.AI_MODEL = (
            ANTHROPIC_MODEL if ANTHROPIC_MODEL else "claude-3-5-sonnet-20240620"
        )
        self.AI_TEMPERATURE = ANTHROPIC_TEMPERATURE if ANTHROPIC_TEMPERATURE else 0.7
        self.GOOGLE_VERTEX_REGION = ANTHROPIC_GOOGLE_VERTEX_REGION
        self.GOOGLE_VERTEX_PROJECT_ID = ANTHROPIC_GOOGLE_VERTEX_PROJECT_ID
        self.WAIT_BETWEEN_REQUESTS = (
            ANTHROPIC_WAIT_BETWEEN_REQUESTS if ANTHROPIC_WAIT_BETWEEN_REQUESTS else 1
        )
        self.failures = 0

    @staticmethod
    def services():
        return ["llm", "vision"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        if (
            self.ANTHROPIC_API_KEY == ""
            or self.ANTHROPIC_API_KEY == "YOUR_ANTHROPIC_API_KEY"
        ):
            return (
                "Please go to the Agent Management page to set your Anthropic API key."
            )

        messages = []
        if images:
            for image in images:
                # If the image is a url, download it
                if image.startswith("http"):
                    image_base64 = base64.b64encode(httpx.get(image).content).decode(
                        "utf-8"
                    )
                else:
                    with open(image, "rb") as f:
                        image_base64 = f.read()
                file_type = image.split(".")[-1]
                if not file_type:
                    file_type = "jpeg"
                if file_type == "jpg":
                    file_type = "jpeg"
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": f"image/{file_type}",
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                )
        else:
            messages.append({"role": "user", "content": prompt})

        if self.GOOGLE_VERTEX_PROJECT_ID != "":
            c = anthropic.AnthropicVertex(
                access_token=self.ANTHROPIC_API_KEY,
                region=self.GOOGLE_VERTEX_REGION,
                project_id=self.GOOGLE_VERTEX_PROJECT_ID,
            )
        else:
            c = anthropic.Client(api_key=self.ANTHROPIC_API_KEY)
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
        try:
            response = c.messages.create(
                messages=messages,
                model=self.AI_MODEL,
                max_tokens=4096,
            )
            return response.content[0].text
        except Exception as e:
            logging.info(f"[CLAUDE PROVIDER] Error: {e}")
            self.failures += 1
            if self.failures > 3:
                raise Exception(f"Claude Error: Too many failures. {e}")
            else:
                # https://console.anthropic.com/settings/limits
                # Rate limits that impact AGiXT most with Anthropic API are the input tokens per minute being limited to 80k.
                # If we hit an error, it is almost always because we exceeded this by sending 2 or more prompts in a row exceeding 80k.
                # To get around it, we sleep for 61 seconds.
                time.sleep(61)
                return await self.inference(prompt=prompt, tokens=tokens, images=images)
