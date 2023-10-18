try:
    from whisper_cpp import Whisper
except ImportError:
    import sys
    import subprocess

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "whisper-cpp-pybind",
        ]
    )
    from whisper_cpp import Whisper

try:
    from pydub import AudioSegment
except ImportError:
    import sys
    import subprocess

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "pydub",
        ]
    )
    from pydub import AudioSegment

import base64
import requests
import os
import io
from Extensions import Extensions


class whisper_stt(Extensions):
    def __init__(self, WHISPER_MODEL="base.en", **kwargs):
        self.commands = {
            "Transcribe Audio from File": self.transcribe_audio_from_file,
            "Transcribe Base64 Audio": self.transcribe_base64_audio,
        }
        # https://huggingface.co/ggerganov/whisper.cpp
        # Models: tiny, tiny.en, base, base.en, small, small.en, medium, medium.en, large, large-v1
        if WHISPER_MODEL not in [
            "tiny",
            "tiny.en",
            "base",
            "base.en",
            "small",
            "small.en",
            "medium",
            "medium.en",
            "large",
            "large-v1",
        ]:
            self.WHISPER_MODEL = "base.en"
        else:
            self.WHISPER_MODEL = WHISPER_MODEL
        os.makedirs(os.path.join(os.getcwd(), "models", "whispercpp"), exist_ok=True)
        self.model_path = os.path.join(
            os.getcwd(), "models", "whispercpp", f"ggml-{WHISPER_MODEL}.bin"
        )
        if not os.path.exists(self.model_path):
            r = requests.get(
                f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{WHISPER_MODEL}.bin",
                allow_redirects=True,
            )
            open(self.model_path, "wb").write(r.content)

    async def transcribe_audio_from_file(self, filename: str = "recording.wav"):
        w = Whisper(model_path=self.model_path)
        file_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        if not os.path.exists(file_path):
            raise RuntimeError(f"Failed to load audio: {filename} does not exist.")
        w.transcribe(file_path)
        return w.output()

    async def transcribe_base64_audio(self, base64_audio: str):
        # Convert the base64 audio to a 16k WAV format
        audio_data = base64.b64decode(base64_audio)
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data), format="m4a")
        audio_segment = audio_segment.set_frame_rate(16000)
        filename = "recording.wav"
        file_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        audio_segment.export(file_path, format="wav")
        output = await self.transcribe_audio_from_file(filename)
        os.remove(file_path)
        return output
