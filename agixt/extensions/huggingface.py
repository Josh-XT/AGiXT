import requests
import json
import os
from Extensions import Extensions
from io import BytesIO
import requests
from PIL import Image
import logging


class huggingface(Extensions):
    def __init__(
        self,
        HUGGINGFACE_API_KEY: str = "",
        HUGGINGFACE_AUDIO_TO_TEXT_MODEL: str = "facebook/wav2vec2-large-960h-lv60-self",
        WORKING_DIRECTORY: str = "./WORKSPACE",
        **kwargs,
    ):
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL = HUGGINGFACE_AUDIO_TO_TEXT_MODEL
        self.WORKING_DIRECTORY = WORKING_DIRECTORY
        if self.HUGGINGFACE_API_KEY is not None:
            self.commands = {
                "Read Audio from File": self.read_audio_from_file,
                "Read Audio": self.read_audio,
                "Generate Image with Stable Diffusion": self.generate_image_with_hf,
            }

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

    def read_audio_from_file(self, audio_path: str):
        audio_path = os.path.join(self.WORKING_DIRECTORY, audio_path)
        with open(audio_path, "rb") as audio_file:
            audio = audio_file.read()
        return self.read_audio(audio)

    def read_audio(self, audio):
        model = self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        api_token = self.HUGGINGFACE_API_KEY
        headers = {"Authorization": f"Bearer {api_token}"}

        if api_token is None:
            raise ValueError(
                "You need to set your Hugging Face API token in the config file."
            )

        response = requests.post(
            api_url,
            headers=headers,
            data=audio,
        )

        text = json.loads(response.content.decode("utf-8"))["text"]
        return "The audio says: " + text
