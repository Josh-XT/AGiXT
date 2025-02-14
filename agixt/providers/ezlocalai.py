import logging
import random
import re
import numpy as np
import requests
from Globals import getenv
import uuid

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai
from Globals import getenv


class EzlocalaiProvider:
    """
    This provider uses the ezLocalai API to generate text from prompts. Learn how to set up ezLocalai at <https://github.com/DevXT-LLC/ezlocalai>.
    """

    friendly_name = "ezLocalai"

    def __init__(
        self,
        EZLOCALAI_API_KEY: str = "",
        EZLOCALAI_API_URI: str = getenv("EZLOCALAI_API_URI"),
        EZLOCALAI_AI_MODEL: str = "ezlocalai",
        EZLOCALAI_MAX_TOKENS: int = 8192,
        EZLOCALAI_TEMPERATURE: float = 1.33,
        EZLOCALAI_TOP_P: float = 0.95,
        EZLOCALAI_VOICE: str = "HAL9000",
        EZLOCALAI_LANGUAGE: str = "en",
        EZLOCALAI_TRANSCRIPTION_MODEL: str = "base",
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = EZLOCALAI_AI_MODEL if EZLOCALAI_AI_MODEL else "ezlocalai"
        self.MAX_TOKENS = EZLOCALAI_MAX_TOKENS if EZLOCALAI_MAX_TOKENS else 8192
        if not EZLOCALAI_API_URI.endswith("/"):
            EZLOCALAI_API_URI += "/"
        self.API_URI = (
            EZLOCALAI_API_URI if EZLOCALAI_API_URI else getenv("EZLOCALAI_API_URI")
        )
        if "v1/" not in self.API_URI:
            self.API_URI += "v1/"
        self.VOICE = EZLOCALAI_VOICE if EZLOCALAI_VOICE else "HAL9000"
        self.TTS_LANGUAGE = EZLOCALAI_LANGUAGE if EZLOCALAI_LANGUAGE else "en"
        if len(self.TTS_LANGUAGE) > 2:
            self.TTS_LANGUAGE = self.TTS_LANGUAGE[:2].lower()
        self.OUTPUT_URL = self.API_URI.replace("/v1/", "") + "/outputs/"
        self.AI_TEMPERATURE = EZLOCALAI_TEMPERATURE if EZLOCALAI_TEMPERATURE else 1.33
        self.AI_TOP_P = EZLOCALAI_TOP_P if EZLOCALAI_TOP_P else 0.95
        self.EZLOCALAI_API_KEY = (
            EZLOCALAI_API_KEY if EZLOCALAI_API_KEY else getenv("EZLOCALAI_API_KEY")
        )
        self.TRANSCRIPTION_MODEL = (
            EZLOCALAI_TRANSCRIPTION_MODEL if EZLOCALAI_TRANSCRIPTION_MODEL else "base"
        )
        self.FAILURES = []
        self.failure_count = 0
        self.chunk_size = 1024

    @staticmethod
    def services():
        return [
            "llm",
            "tts",
            "image",
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
        if not self.API_URI.endswith("/"):
            self.API_URI += "/"
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        openai.api_type = "openai"
        max_tokens = (
            int(self.MAX_TOKENS) - int(tokens) if tokens > 0 else self.MAX_TOKENS
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
        try:
            response = openai.chat.completions.create(
                model=self.AI_MODEL,
                messages=messages,
                max_tokens=int(max_tokens),
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
                n=1,
                stream=False,
            )
            if not isinstance(response, str):
                response = response.choices[0].message.content
            if "User:" in response:
                response = response.split("User:")[0]
            response = response.lstrip()
            response.replace("<s>", "").replace("</s>", "")
            if "http://localhost:8091/outputs/" in response:
                response = response.replace(
                    "http://localhost:8091/outputs/", self.OUTPUT_URL
                )
            if self.OUTPUT_URL in response:
                urls = re.findall(f"{re.escape(self.OUTPUT_URL)}[^\"' ]+", response)
                urls = urls[0].split("\n\n")
                for url in urls:
                    file_type = url.split(".")[-1]
                    if file_type == "wav":
                        response = response.replace(
                            url,
                            f'<audio controls><source src="{url}" type="audio/wav"></audio>',
                        )
                    else:
                        response = response.replace(url, f"![{file_type}]({url})")
            return response
        except Exception as e:
            self.failure_count += 1
            logging.info(f"ezLocalai API Error: {e}")
            if "," in self.API_URI:
                self.rotate_uri()
            if self.failure_count >= 3:
                logging.info("ezLocalai failed 3 times, unable to proceed.")
                raise Exception(f"ezLocalai API Error: Too many failures. {e}")
            return await self.inference(prompt=prompt, tokens=tokens, images=images)

    async def transcribe_audio(self, audio_path: str):
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        openai.api_type = "openai"
        with open(audio_path, "rb") as audio_file:
            transcription = openai.audio.transcriptions.create(
                model=self.TRANSCRIPTION_MODEL, file=audio_file
            )
        return transcription.text

    async def translate_audio(self, audio_path: str):
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        openai.api_type = "openai"
        with open(audio_path, "rb") as audio_file:
            translation = openai.audio.translations.create(
                model=self.TRANSCRIPTION_MODEL, file=audio_file
            )
        return translation.text

    async def text_to_speech(self, text: str):
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        openai.api_type = "openai"
        tts_response = openai.audio.speech.create(
            model="tts-1",
            voice=self.VOICE,
            input=text,
            extra_body={"language": self.TTS_LANGUAGE},
        )
        return tts_response.content

    async def generate_image(self, prompt: str) -> str:
        filename = f"{uuid.uuid4()}.png"
        image_path = f"./WORKSPACE/{filename}"
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        openai.api_type = "openai"
        response = openai.images.generate(
            prompt=prompt,
            model="stabilityai/sdxl-turbo",
            n=1,
            size="512x512",
            response_format="url",
        )
        logging.info(f"Image Generated for prompt:{prompt}")
        url = response.data[0].url
        with open(image_path, "wb") as f:
            f.write(requests.get(url).content)
        agixt_uri = getenv("AGIXT_URI")
        return f"{agixt_uri}/outputs/{filename}"

    def embeddings(self, input) -> np.ndarray:
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        openai.api_type = "openai"
        response = openai.embeddings.create(
            input=input,
            model="bge-m3",
        )
        return response.data[0].embedding
