import logging
import random
import re
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


class EzlocalaiProvider:
    def __init__(
        self,
        EZLOCALAI_API_KEY: str = "None",
        EZLOCALAI_API_URI: str = "http://localhost:8091/v1/",
        AI_MODEL: str = "TheBloke/phi-2-dpo-GGUF",
        MAX_TOKENS: int = 8192,
        AI_TEMPERATURE: float = 1.33,
        AI_TOP_P: float = 0.95,
        VOICE: str = "HAL9000",
        TRANSCRIPTION_MODEL: str = "base",
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "TheBloke/phi-2-dpo-GGUF"
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 8192
        if not EZLOCALAI_API_URI.endswith("/"):
            EZLOCALAI_API_URI += "/"
        self.API_URI = (
            EZLOCALAI_API_URI if EZLOCALAI_API_URI else "http://localhost:8091/v1/"
        )
        self.VOICE = VOICE if VOICE else "HAL9000"
        self.OUTPUT_URL = self.API_URI.replace("/v1/", "") + "/outputs/"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 1.33
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.95
        self.EZLOCALAI_API_KEY = EZLOCALAI_API_KEY if EZLOCALAI_API_KEY else "None"
        self.TRANSCRIPTION_MODEL = (
            TRANSCRIPTION_MODEL if TRANSCRIPTION_MODEL else "base"
        )
        self.FAILURES = []
        self.failure_count = 0

    @staticmethod
    def services():
        return ["llm", "tts", "transcription", "translation", "vision"]

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
                extra_body={
                    "voice": self.VOICE,
                },
            )
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
                return "ezLocalai failed 3 times, unable to proceed."
            return await self.inference(prompt=prompt, tokens=tokens, images=images)

    async def transcribe_audio(self, audio_path: str):
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        with open(audio_path, "rb") as audio_file:
            transcription = openai.audio.transcriptions.create(
                model=self.TRANSCRIPTION_MODEL, file=audio_file
            )
        return transcription.text

    async def translate_audio(self, audio_path: str):
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        with open(audio_path, "rb") as audio_file:
            translation = openai.audio.translations.create(
                model=self.TRANSCRIPTION_MODEL, file=audio_file
            )
        return translation.text

    async def text_to_speech(self, text: str):
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        tts_response = openai.audio.speech.create(
            model="tts-1",
            voice=self.VOICE,
            input=text,
        )
        return tts_response.content

    def embeddings(self, input) -> np.ndarray:
        openai.base_url = self.API_URI
        openai.api_key = self.EZLOCALAI_API_KEY
        response = openai.embeddings.create(
            input=input,
            model="text-embedding-3-small",
        )
        return response.data[0].embedding
