try:
    import anthropic
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic"])
    import anthropic

import httpx
import base64


# List of models available at https://docs.anthropic.com/claude/docs/models-overview
# Get API key at https://console.anthropic.com/settings/keys
class ClaudeProvider:
    def __init__(
        self,
        ANTHROPIC_API_KEY: str = "",
        AI_MODEL: str = "claude-3-opus-20240229",
        MAX_TOKENS: int = 200000,
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.ANTHROPIC_API_KEY = ANTHROPIC_API_KEY
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 200000
        self.AI_MODEL = AI_MODEL if AI_MODEL else "claude-3-opus-20240229"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7

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

        try:
            c = anthropic.Client(api_key=self.ANTHROPIC_API_KEY)
            response = c.messages.create(
                messages=messages,
                model=self.AI_MODEL,
                max_tokens=4096,
            )
            return response.content[0].text
        except Exception as e:
            return f"Claude Error: {e}"
