from io import BytesIO
import os.path
import uuid
from base64 import b64decode
import openai
import requests
from PIL import Image
from Commands import Commands
import logging


class image_generator(Commands):
    def __init__(
        self, HUGGINGFACE_API_KEY: str = "", OPENAI_API_KEY: str = "", **kwargs
    ):
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.OPENAI_API_KEY = OPENAI_API_KEY
        if self.HUGGINGFACE_API_KEY or self.OPENAI_API_KEY:
            self.commands = {"Generate Image": self.generate_image}

    def generate_image(self, prompt: str) -> str:
        filename = f"{str(uuid.uuid4())}.jpg"

        if self.OPENAI_API_KEY:
            return self.generate_image_with_dalle(prompt, filename)
        elif self.HUGGINGFACE_API_KEY:
            return self.generate_image_with_hf(prompt, filename)
        else:
            return "No Image Provider Set"

    def generate_image_with_hf(self, prompt: str, filename: str) -> str:
        API_URL = (
            "https://api-inference.huggingface.co/models/CompVis/stable-diffusion-v1-4"
        )
        headers = {"Authorization": f"Bearer {self.HUGGINGFACE_API_TOKEN}"}

        response = requests.post(
            API_URL,
            headers=headers,
            json={
                "inputs": prompt,
            },
        )

        image = Image.open(BytesIO(response.content))
        logging.info(f"Image Generated for prompt:{prompt}")

        image.save(os.path.join(self.WORKING_DIRECTORY, filename))

        return f"Saved to disk:{filename}"

    def generate_image_with_dalle(self, prompt: str, filename: str) -> str:
        openai.api_key = self.OPENAI_API_KEY

        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="256x256",
            response_format="b64_json",
        )

        logging.info(f"Image Generated for prompt:{prompt}")

        image_data = b64decode(response["data"][0]["b64_json"])

        with open(f"{self.WORKING_DIRECTORY}/{filename}", mode="wb") as png:
            png.write(image_data)

        return f"Saved to disk:{filename}"
