from providers.gpt4free import Gpt4freeProvider
from providers.huggingface import HuggingfaceProvider
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from AudioToText import AudioToText
import os


class DefaultProvider:
    def __init__(
        self,
        AI_MODEL: str = "mixtral-8x7b",
        TRANSCRIPTION_MODEL: str = "base",
        HUGGINGFACE_API_KEY: str = "",
        VOICE: str = "Brian",
        **kwargs
    ):
        self.AI_MODEL = AI_MODEL if AI_MODEL else "mixtral-8x7b"
        self.AI_TEMPERATURE = 0.7
        self.AI_TOP_P = 0.7
        self.MAX_TOKENS = 16000
        self.VOICE = VOICE if VOICE else "Brian"
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.TRANSCRIPTION_MODEL = (
            TRANSCRIPTION_MODEL if TRANSCRIPTION_MODEL else "base"
        )
        self.chunk_size = 256
        self.services = [
            "llm",
            "embeddings",
            "tts",
            "transcription",
            "translation",
            "image",
        ]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        return await Gpt4freeProvider(
            AI_MODEL=self.AI_MODEL,
            VOICE=self.VOICE,
        ).inference(prompt=prompt, tokens=tokens, images=images)

    async def text_to_speech(self, text: str):
        return await Gpt4freeProvider(VOICE=self.VOICE).text_to_speech(text=text)

    async def embeddings(self, text: str):
        embedder = ONNXMiniLM_L6_V2()
        embedder.DOWNLOAD_PATH = os.getcwd()
        return ONNXMiniLM_L6_V2().__call__(input=[text])[0]

    async def transcribe_audio(self, audio_path: str):
        return await AudioToText(model=self.TRANSCRIPTION_MODEL).transcribe_audio(
            file=audio_path
        )

    async def translate_audio(self, audio_path: str):
        return await AudioToText(model=self.TRANSCRIPTION_MODEL).transcribe_audio(
            file=audio_path, translate=True
        )

    async def generate_image(self, prompt: str):
        return await HuggingfaceProvider(
            HUGGINGFACE_API_KEY=self.HUGGINGFACE_API_KEY
        ).generate_image(prompt=prompt)

    # Would be nice to add a generate_image method here, but I don't have a good default that doesn't require configuration yet.
