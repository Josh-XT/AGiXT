import os
import base64
import uuid
import logging
import ffmpeg
import requests
from faster_whisper import WhisperModel


class AudioToText:
    def __init__(self, model="base"):
        # Will need to add speech-to-text providers later, such as OpenAI's Whisper.
        # For now, we will only use faster-whisper running locally on CPU.
        self.w = WhisperModel(model, download_root="models", device="cpu")

    async def transcribe_audio(
        self,
        file: str,
        language: str = None,
        prompt: str = None,
        temperature: float = 0.0,
        translate: bool = False,
    ):
        """
        Transcribe an audio file to text.
        :param file: The audio file to transcribe. Can be a local file path, a URL, or a base64 encoded string.
        :param language: The language of the audio file. If not provided, the language will be automatically detected.
        :param prompt: The prompt to use for the transcription.
        :param temperature: The temperature to use for the transcription.
        :param translate: Whether to translate the transcription to English.
        """
        if file.startswith("data:"):
            audio_format = file.split(",")[0].split("/")[1].split(";")[0]
            base64_audio = file.split(",")[1]
        elif file.startswith("http"):
            try:
                audio_data = requests.get(file).content
                audio_format = file.split("/")[-1]
                base64_audio = base64.b64encode(audio_data).decode("utf-8")
            except Exception as e:
                return f"Failed to download audio file: {e}"
        else:
            file_path = os.path.join(os.getcwd(), "WORKSPACE", file)
            if not os.path.exists(file_path):
                return "File not found."
            audio_format = file_path.split(".")[-1]
            with open(file_path, "rb") as f:
                audio_data = f.read()
            base64_audio = base64.b64encode(audio_data).decode("utf-8")
        if "/" in audio_format:
            audio_format = audio_format.split("/")[1]
        input_file = os.path.join(
            os.getcwd(), "WORKSPACE", f"{uuid.uuid4().hex}.{audio_format}"
        )
        filename = f"{uuid.uuid4().hex}.wav"
        file_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        ffmpeg.input(input_file).output(file_path, ar=16000).run(overwrite_output=True)
        audio_data = base64.b64decode(base64_audio)
        with open(file_path, "wb") as audio_file:
            audio_file.write(audio_data)
        if not os.path.exists(file_path):
            raise RuntimeError(f"Failed to load audio.")
        segments, _ = self.w.transcribe(
            file_path,
            task="transcribe" if not translate else "translate",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt=prompt,
            language=language,
            temperature=temperature,
        )
        segments = list(segments)
        user_input = ""
        for segment in segments:
            user_input += segment.text
        logging.info(f"[AudioToText] Transcribed User Input: {user_input}")
        os.remove(file_path)
        return user_input
