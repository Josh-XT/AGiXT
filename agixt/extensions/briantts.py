from Extensions import Extensions
import os
import requests
from playsound import playsound


class briantts(Extensions):
    def __init__(
        self,
        USE_BRIAN_TTS: bool = True,
        **kwargs,
    ):
        self.USE_BRIAN_TTS = USE_BRIAN_TTS
        if self.USE_BRIAN_TTS:
            self.commands = {"Speak with TTS with BrianTTS": self.speak_with_briantts}

    def speak_with_briantts(self, text: str) -> bool:
        tts_url = (
            f"https://api.streamelements.com/kappa/v2/speech?voice=Brian&text={text}"
        )
        response = requests.get(tts_url)

        if response.status_code == 200:
            with open("speech.mp3", "wb") as f:
                f.write(response.content)
            playsound("speech.mp3")
            os.remove("speech.mp3")
            return True
        else:
            return False
