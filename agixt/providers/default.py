from providers.gpt4free import Gpt4freeProvider
from providers.google import GoogleProvider
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from faster_whisper import WhisperModel
import os
import logging
import numpy as np
import requests
import base64
from pydub import AudioSegment
import uuid

# Default provider uses:
# llm: gpt4free
# tts: Streamlabs TTS
# transcription: faster-whisper
# translation: faster-whisper


class DefaultProvider:
    def __init__(
        self,
        AI_MODEL: str = "mixtral-8x7b",
        VOICE: str = "Brian",
        **kwargs,
    ):
        self.AI_MODEL = AI_MODEL if AI_MODEL else "mixtral-8x7b"
        self.VOICE = VOICE if VOICE else "Brian"
        self.AI_TEMPERATURE = 0.7
        self.AI_TOP_P = 0.7
        self.MAX_TOKENS = 16000
        self.TRANSCRIPTION_MODEL = (
            "base"
            if "TRANSCRIPTION_MODEL" not in kwargs
            else kwargs["TRANSCRIPTION_MODEL"]
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
        ]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        return await Gpt4freeProvider(
            AI_MODEL=self.AI_MODEL,
            VOICE=self.VOICE,
        ).inference(prompt=prompt, tokens=tokens, images=images)

    async def text_to_speech(self, text: str):
        voices = [
            "Filiz",
            "Astrid",
            "Tatyana",
            "Maxim",
            "Carmen",
            "Ines",
            "Cristiano",
            "Vitoria",
            "Ricardo",
            "Maja",
            "Jan",
            "Jacek",
            "Ewa",
            "Ruben",
            "Lotte",
            "Liv",
            "Seoyeon",
            "Takumi",
            "Mizuki",
            "Giorgio",
            "Carla",
            "Bianca",
            "Karl",
            "Dora",
            "Mathieu",
            "Celine",
            "Chantal",
            "Penelope",
            "Miguel",
            "Mia",
            "Enrique",
            "Conchita",
            "Geraint",
            "Salli",
            "Matthew",
            "Kimberly",
            "Kendra",
            "Justin",
            "Joey",
            "Joanna",
            "Ivy",
            "Raveena",
            "Aditi",
            "Emma",
            "Brian",
            "Amy",
            "Russell",
            "Nicole",
            "Vicki",
            "Marlene",
            "Hans",
            "Naja",
            "Mads",
            "Gwyneth",
            "Zhiyu",
            "es-ES-Standard-A",
            "it-IT-Standard-A",
            "it-IT-Wavenet-A",
            "ja-JP-Standard-A",
            "ja-JP-Wavenet-A",
            "ko-KR-Standard-A",
            "ko-KR-Wavenet-A",
            "pt-BR-Standard-A",
            "tr-TR-Standard-A",
            "sv-SE-Standard-A",
            "nl-NL-Standard-A",
            "nl-NL-Wavenet-A",
            "en-US-Wavenet-A",
            "en-US-Wavenet-B",
            "en-US-Wavenet-C",
            "en-US-Wavenet-D",
            "en-US-Wavenet-E",
            "en-US-Wavenet-F",
            "en-GB-Standard-A",
            "en-GB-Standard-B",
            "en-GB-Standard-C",
            "en-GB-Standard-D",
            "en-GB-Wavenet-A",
            "en-GB-Wavenet-B",
            "en-GB-Wavenet-C",
            "en-GB-Wavenet-D",
            "en-US-Standard-B",
            "en-US-Standard-C",
            "en-US-Standard-D",
            "en-US-Standard-E",
            "de-DE-Standard-A",
            "de-DE-Standard-B",
            "de-DE-Wavenet-A",
            "de-DE-Wavenet-B",
            "de-DE-Wavenet-C",
            "de-DE-Wavenet-D",
            "en-AU-Standard-A",
            "en-AU-Standard-B",
            "en-AU-Wavenet-A",
            "en-AU-Wavenet-B",
            "en-AU-Wavenet-C",
            "en-AU-Wavenet-D",
            "en-AU-Standard-C",
            "en-AU-Standard-D",
            "fr-CA-Standard-A",
            "fr-CA-Standard-B",
            "fr-CA-Standard-C",
            "fr-CA-Standard-D",
            "fr-FR-Standard-C",
            "fr-FR-Standard-D",
            "fr-FR-Wavenet-A",
            "fr-FR-Wavenet-B",
            "fr-FR-Wavenet-C",
            "fr-FR-Wavenet-D",
            "da-DK-Wavenet-A",
            "pl-PL-Wavenet-A",
            "pl-PL-Wavenet-B",
            "pl-PL-Wavenet-C",
            "pl-PL-Wavenet-D",
            "pt-PT-Wavenet-A",
            "pt-PT-Wavenet-B",
            "pt-PT-Wavenet-C",
            "pt-PT-Wavenet-D",
            "ru-RU-Wavenet-A",
            "ru-RU-Wavenet-B",
            "ru-RU-Wavenet-C",
            "ru-RU-Wavenet-D",
            "sk-SK-Wavenet-A",
            "tr-TR-Wavenet-A",
            "tr-TR-Wavenet-B",
            "tr-TR-Wavenet-C",
            "tr-TR-Wavenet-D",
            "tr-TR-Wavenet-E",
            "uk-UA-Wavenet-A",
            "ar-XA-Wavenet-A",
            "ar-XA-Wavenet-B",
            "ar-XA-Wavenet-C",
            "cs-CZ-Wavenet-A",
            "nl-NL-Wavenet-B",
            "nl-NL-Wavenet-C",
            "nl-NL-Wavenet-D",
            "nl-NL-Wavenet-E",
            "en-IN-Wavenet-A",
            "en-IN-Wavenet-B",
            "en-IN-Wavenet-C",
            "fil-PH-Wavenet-A",
            "fi-FI-Wavenet-A",
            "el-GR-Wavenet-A",
            "hi-IN-Wavenet-A",
            "hi-IN-Wavenet-B",
            "hi-IN-Wavenet-C",
            "hu-HU-Wavenet-A",
            "id-ID-Wavenet-A",
            "id-ID-Wavenet-B",
            "id-ID-Wavenet-C",
            "it-IT-Wavenet-B",
            "it-IT-Wavenet-C",
            "it-IT-Wavenet-D",
            "ja-JP-Wavenet-B",
            "ja-JP-Wavenet-C",
            "ja-JP-Wavenet-D",
            "cmn-CN-Wavenet-A",
            "cmn-CN-Wavenet-B",
            "cmn-CN-Wavenet-C",
            "cmn-CN-Wavenet-D",
            "nb-no-Wavenet-E",
            "nb-no-Wavenet-A",
            "nb-no-Wavenet-B",
            "nb-no-Wavenet-C",
            "nb-no-Wavenet-D",
            "vi-VN-Wavenet-A",
            "vi-VN-Wavenet-B",
            "vi-VN-Wavenet-C",
            "vi-VN-Wavenet-D",
            "sr-rs-Standard-A",
            "lv-lv-Standard-A",
            "is-is-Standard-A",
            "bg-bg-Standard-A",
            "af-ZA-Standard-A",
            "Tracy",
            "Danny",
            "Huihui",
            "Yaoyao",
            "Kangkang",
            "HanHan",
            "Zhiwei",
            "Asaf",
            "An",
            "Stefanos",
            "Filip",
            "Ivan",
            "Heidi",
            "Herena",
            "Kalpana",
            "Hemant",
            "Matej",
            "Andika",
            "Rizwan",
            "Lado",
            "Valluvar",
            "Linda",
            "Heather",
            "Sean",
            "Michael",
            "Karsten",
            "Guillaume",
            "Pattara",
            "Jakub",
            "Szabolcs",
            "Hoda",
            "Naayf",
        ]
        if self.VOICE not in voices:
            self.VOICE = "Brian"
        response = requests.get(
            f"https://api.streamelements.com/kappa/v2/speech?voice={self.VOICE}&text={text}"
        )
        file_content = base64.b64encode(response.content).decode("utf-8")
        # It is an mp3, convert to 16k wav
        audio = AudioSegment.from_mp3(base64.b64decode(file_content))
        file_path = os.path.join(os.getcwd(), "WORKSPACE", f"{uuid.uuid4()}.wav")
        audio.export(file_path, format="wav")
        # Get content of the wav file to return base64
        with open(file_path, "rb") as f:
            file_content = base64.b64encode(f.read()).decode("utf-8")
        os.remove(file_path)
        return file_content

    def embeddings(self, input) -> np.ndarray:
        return self.embedder.__call__(input=[input])[0]

    async def transcribe_audio(
        self,
        audio_path,
        translate=False,
    ):
        self.w = WhisperModel(
            self.TRANSCRIPTION_MODEL, download_root="models", device="cpu"
        )
        segments, _ = self.w.transcribe(
            audio_path,
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
