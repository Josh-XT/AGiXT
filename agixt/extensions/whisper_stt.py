try:
    import ffmpeg
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "ffmpeg-python"])
    import ffmpeg
try:
    from whispercpp import Whisper
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "whispercpp"])
    from whispercpp import Whisper

import base64
import requests
import os
import numpy as np
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
        model_path = os.path.join(
            os.getcwd(), "models", "whispercpp", f"ggml-{WHISPER_MODEL}.bin"
        )
        if not os.path.exists(model_path):
            r = requests.get(
                f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{WHISPER_MODEL}.bin",
                allow_redirects=True,
            )
            open(model_path, "wb").write(r.content)

    def transcribe_audio_from_file(self, filename: str = "recording.wav"):
        w = Whisper.from_pretrained(
            model_name=self.WHISPER_MODEL, basedir=os.path.join(os.getcwd(), "models")
        )
        if not filename.startswith(os.path.join(os.getcwd(), "WORKSPACE")):
            filename = os.path.join(os.getcwd(), "WORKSPACE", filename)
        try:
            y, _ = (
                ffmpeg.input(filename, threads=0)
                .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=16000)
                .run(
                    cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True
                )
            )
        except ffmpeg.Error as e:
            raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e

        arr = np.frombuffer(y, np.int16).flatten().astype(np.float32) / 32768.0
        return w.transcribe(arr)

    def transcribe_base64_audio(self, base64_audio: str):
        w = Whisper.from_pretrained(
            model_name=self.WHISPER_MODEL, basedir=os.path.join(os.getcwd(), "models")
        )
        arr = (
            np.frombuffer(base64.b64decode(base64_audio), np.int16)
            .flatten()
            .astype(np.float32)
            / 32768.0
        )
        return w.transcribe(arr)
