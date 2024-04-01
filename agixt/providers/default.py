from providers.gpt4free import Gpt4freeProvider
from providers.huggingface import HuggingfaceProvider
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from faster_whisper import WhisperModel
from pydub import AudioSegment
import os
import io
import logging
import numpy as np
import ffmpeg
import uuid
import base64


class DefaultProvider:
    def __init__(
        self,
        AI_MODEL: str = "mixtral-8x7b",
        TRANSCRIPTION_MODEL: str = "base",
        HUGGINGFACE_API_KEY: str = "",
        VOICE: str = "Brian",
        **kwargs,
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
        self.embedder = ONNXMiniLM_L6_V2()
        self.embedder.DOWNLOAD_PATH = os.getcwd()
        self.chunk_size = 256

    @staticmethod
    def services():
        return [
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

    def embeddings(self, input) -> np.ndarray:
        return self.embedder.__call__(input=[input])[0]

    async def convert_to_wav(self, base64_audio, audio_type="webm"):
        audio_data = base64.b64decode(base64_audio)
        input_filename = f"{uuid.uuid4().hex}.{audio_type}"
        input_file = os.path.join("./WORKSPACE", input_filename)
        with open(input_file, "wb") as f:
            f.write(audio_data)
        filename = f"{uuid.uuid4().hex}.wav"
        file_path = os.path.join("./WORKSPACE", filename)
        ffmpeg.input(input_file).output(file_path, ar=16000).run(overwrite_output=True)
        return file_path, filename

    async def transcribe_audio(
        self,
        audio_path,
        translate=False,
    ):
        self.w = WhisperModel(
            self.TRANSCRIPTION_MODEL, download_root="models", device="cpu"
        )
        audio_format = audio_path.split(".")[-1]
        with open(audio_path, "rb") as f:
            audio = f.read()
        base64_audio = f"{base64.b64encode(audio).decode('utf-8')}"
        filename = f"{uuid.uuid4().hex}.wav"
        audio_data = base64.b64decode(base64_audio)
        audio_segment = AudioSegment.from_file(
            io.BytesIO(audio_data), format=audio_format.lower()
        )
        audio_segment = audio_segment.set_frame_rate(16000)
        file_path = os.path.join("./WORKSPACE", filename)
        audio_segment.export(file_path, format="wav")
        if audio_format.lower() != "wav":
            file_path, filename = await self.convert_to_wav(
                base64_audio=base64_audio, audio_type=audio_format
            )
        with open(file_path, "rb") as f:
            audio = f.read()
        user_audio = f"{base64.b64encode(audio).decode('utf-8')}"
        segments, _ = self.w.transcribe(
            user_audio,
            task="transcribe" if not translate else "translate",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        segments = list(segments)
        user_input = ""
        for segment in segments:
            user_input += segment.text
        logging.info(f"[STT] Transcribed User Input: {user_input}")
        return user_input

    async def translate_audio(self, audio_path: str):
        return await self.transcribe_audio(
            audio_path=audio_path,
            translate=True,
        )

    async def generate_image(self, prompt: str):
        return await HuggingfaceProvider(
            HUGGINGFACE_API_KEY=self.HUGGINGFACE_API_KEY
        ).generate_image(prompt=prompt)

    # Would be nice to add a generate_image method here, but I don't have a good default that doesn't require configuration yet.
