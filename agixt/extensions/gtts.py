from Extensions import Extensions
import os
from playsound import playsound
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

    def speak_with_gtts(self, text: str) -> bool:
        tts = ts.gTTS(text)
        tts.save("speech.mp3")
        playsound("speech.mp3", True)
        os.remove("speech.mp3")
        return True
