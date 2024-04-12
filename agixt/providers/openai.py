import time
import logging
import random
import base64
import numpy as np
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai


class OpenaiProvider:
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        AI_MODEL: str = "gpt-3.5-turbo-16k-0613",
        API_URI: str = "https://api.openai.com/v1",
        MAX_TOKENS: int = 16000,
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        SYSTEM_MESSAGE: str = "",
        VOICE: str = "alloy",
        TRANSCRIPTION_MODEL: str = "whisper-1",
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo-16k-0613"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 16000
        self.API_URI = API_URI if API_URI else "https://api.openai.com/v1"
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.OPENAI_API_KEY = OPENAI_API_KEY
        self.SYSTEM_MESSAGE = SYSTEM_MESSAGE
        self.VOICE = VOICE if VOICE else "alloy"
        self.TRANSCRIPTION_MODEL = (
            TRANSCRIPTION_MODEL if TRANSCRIPTION_MODEL else "whisper-1"
        )
        self.FAILURES = []
        try:
            self.embedder = OpenAIEmbeddingFunction(
                model_name="text-embedding-3-small",
                api_key=self.OPENAI_API_KEY,
                api_base=self.API_URI,
            )
        except Exception as e:
            self.embedder = None
        self.chunk_size = 1024

    @staticmethod
    def services():
        return [
            "llm",
            "tts",
            "image",
            "embeddings",
            "transcription",
            "translation",
            "vision",
        ]

    def rotate_uri(self):
        self.FAILURES.append(self.API_URI)
        uri_list = self.API_URI.split(",")
        random.shuffle(uri_list)
        for uri in uri_list:
            if uri not in self.FAILURES:
                self.API_URI = uri
                openai.base_url = self.API_URI
                break

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        if images != []:
            if "vision" not in self.AI_MODEL:
                self.AI_MODEL = "gpt-4-vision-preview"
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        openai.base_url = self.API_URI if self.API_URI else "https://api.openai.com/v1/"
        openai.api_key = self.OPENAI_API_KEY
        if self.OPENAI_API_KEY == "" or self.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY":
            if self.API_URI == "https://api.openai.com/v1/":
                return (
                    "Please go to the Agent Management page to set your OpenAI API key."
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
        if self.SYSTEM_MESSAGE:
            messages.append({"role": "system", "content": self.SYSTEM_MESSAGE})

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
            logging.info(f"OpenAI API Error: {e}")
            if "," in self.API_URI:
                self.rotate_uri()
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(prompt=prompt, tokens=tokens)
            return str(response)

    async def transcribe_audio(self, audio_path: str):
        openai.base_url = self.API_URI if self.API_URI else "https://api.openai.com/v1/"
        openai.api_key = self.OPENAI_API_KEY
        with open(audio_path, "rb") as audio_file:
            transcription = openai.audio.transcriptions.create(
                model=self.TRANSCRIPTION_MODEL, file=audio_file
            )
        return transcription.text

    async def translate_audio(self, audio_path: str):
        openai.base_url = self.API_URI if self.API_URI else "https://api.openai.com/v1/"
        openai.api_key = self.OPENAI_API_KEY
        with open(audio_path, "rb") as audio_file:
            translation = openai.audio.translations.create(
                model=self.TRANSCRIPTION_MODEL, file=audio_file
            )
        return translation.text

    async def text_to_speech(self, text: str):
        openai.base_url = self.API_URI if self.API_URI else "https://api.openai.com/v1/"
        openai.api_key = self.OPENAI_API_KEY
        tts_response = openai.audio.speech.create(
            model="tts-1",
            voice=self.VOICE,
            input=text,
        )
        return tts_response.content

    async def generate_image(self, prompt: str, filename: str = "image.png") -> str:
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
        encoded_image_data = base64.b64encode(image_data).decode("utf-8")
        return f"data:image/png;base64,{encoded_image_data}"

    def embeddings(self, input) -> np.ndarray:
        openai.base_url = self.API_URI
        openai.api_key = self.OPENAI_API_KEY
        response = openai.embeddings.create(
            input=input,
            model="text-embedding-3-small",
        )
        return response.data[0].embedding
