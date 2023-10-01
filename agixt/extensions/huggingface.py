import requests
import json
import os
from Extensions import Extensions
import requests


class huggingface(Extensions):
    def __init__(
        self,
        HUGGINGFACE_API_KEY: str = "",
        HUGGINGFACE_AUDIO_TO_TEXT_MODEL: str = "facebook/wav2vec2-large-960h-lv60-self",
        USE_HUGGINGFACE_TTS: bool = False,
        **kwargs,
    ):
        self.requirements = []
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL = (
            HUGGINGFACE_AUDIO_TO_TEXT_MODEL
            if HUGGINGFACE_AUDIO_TO_TEXT_MODEL
            else "facebook/wav2vec2-large-960h-lv60-self"
        )
        self.WORKING_DIRECTORY = os.path.join(os.getcwd(), "WORKSPACE")
        if self.HUGGINGFACE_API_KEY is not None:
            self.commands = {
                "Read Audio from File with Huggingface": self.read_audio_from_file,
                "Read Audio with Huggingface": self.read_audio,
                "Transcribe Base64 Audio with Huggingface": self.transcribe_base64_audio,
            }

    async def read_audio_from_file(self, audio_path: str):
        audio_path = os.path.join(self.WORKING_DIRECTORY, audio_path)
        with open(audio_path, "rb") as audio_file:
            audio = audio_file.read()
        return await self.read_audio(audio)

    async def read_audio(self, audio):
        if self.HUGGINGFACE_API_KEY is None:
            raise ValueError(
                "You need to set your Hugging Face API token in the config file."
            )
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL}",
            headers={"Authorization": f"Bearer {self.HUGGINGFACE_API_KEY}"},
            data=audio,
        )

        text = json.loads(response.content.decode("utf-8"))["text"]
        return text

    async def transcribe_base64_audio(self, audio: str):
        if self.HUGGINGFACE_API_KEY is None:
            raise ValueError(
                "You need to set your Hugging Face API token in the config file."
            )
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL}",
            headers={"Authorization": f"Bearer {self.HUGGINGFACE_API_KEY}"},
            data=audio,
        )

        text = json.loads(response.content.decode("utf-8"))["text"]
        return text
