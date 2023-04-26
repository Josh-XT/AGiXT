from io import BytesIO
import os.path
import uuid
from base64 import b64decode
import openai
import requests
from PIL import Image
from Config import Config
from Commands import Commands

CFG = Config()


class image_generator(Commands):
    def __init__(self):
        self.commands = {"Generate Image": self.generate_image}

    def generate_image(self, prompt: str) -> str:
        filename = f"{str(uuid.uuid4())}.jpg"

        if CFG.image_provider == "dalle":
            return self.generate_image_with_dalle(prompt, filename)
        elif CFG.image_provider == "sd":
            return self.generate_image_with_hf(prompt, filename)
        else:
            return "No Image Provider Set"

    def generate_image_with_hf(self, prompt: str, filename: str) -> str:
        API_URL = (
            "https://api-inference.huggingface.co/models/CompVis/stable-diffusion-v1-4"
        )
        if CFG.HUGGINGFACE_API_TOKEN is None:
            raise ValueError(
                "You need to set your Hugging Face API token in the config file."
            )
        headers = {"Authorization": f"Bearer {CFG.HUGGINGFACE_API_TOKEN}"}

        response = requests.post(
            "https://api-inference.huggingface.co/models/CompVis/stable-diffusion-v1-4",
            headers=headers,
            json={
                "inputs": prompt,
            },
        )

        image = Image.open(BytesIO(response.content))
        print(f"Image Generated for prompt:{prompt}")

        image.save(os.path.join(CFG.WORKING_DIRECTORY, filename))

        return f"Saved to disk:{filename}"

    def generate_image_with_dalle(self, prompt: str, filename: str) -> str:
        openai.api_key = CFG.OPENAI_API_KEY

        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="256x256",
            response_format="b64_json",
        )

        print(f"Image Generated for prompt:{prompt}")

        image_data = b64decode(response["data"][0]["b64_json"])

        with open(f"{CFG.WORKING_DIRECTORY}/{filename}", mode="wb") as png:
            png.write(image_data)

        return f"Saved to disk:{filename}"
