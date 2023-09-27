from Extensions import Extensions
import logging
import base64

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai


class dalle(Extensions):
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        **kwargs,
    ):
        self.OPENAI_API_KEY = OPENAI_API_KEY
        if self.OPENAI_API_KEY:
            self.commands = {
                "Generate Image with DALLE": self.generate_image_with_dalle
            }

    async def generate_image_with_dalle(
        self, prompt: str, filename: str = "image.png"
    ) -> str:
        image_path = f"./WORKSPACE/{filename}"
        openai.api_key = self.OPENAI_API_KEY
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="256x256",
            response_format="b64_json",
        )
        logging.info(f"Image Generated for prompt:{prompt}")
        image_data = base64.b64decode(response["data"][0]["b64_json"])
        with open(image_path, mode="wb") as png:
            png.write(image_data)
        # REturn base64 image
        encoded_image_data = base64.b64encode(image_data).decode("utf-8")
        return f"#GENERATED_IMAGE:{encoded_image_data}"
