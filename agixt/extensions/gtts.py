from Extensions import Extensions
import os

try:
    import gtts as ts
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "gTTS==2.3.2"])
    import gtts as ts


class gtts(Extensions):
    def __init__(
        self,
        USE_GTTS: bool = False,
        **kwargs,
    ):
        self.USE_GTTS = USE_GTTS
        if USE_GTTS:
            self.commands = {"Speak with GTTS": self.speak_with_gtts}

    async def speak_with_gtts(self, text: str) -> bool:
        tts = ts.gTTS(text)
        tts.save("speech.mp3")
        with open("speech.mp3", "rb") as f:
            audio = f.read()
        os.remove("speech.mp3")
        audio = audio.decode("utf-8")
        return f"#GENERATED_AUDIO:{audio}"
