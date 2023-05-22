from Commands import Commands
import os
from threading import Semaphore
import requests
from playsound import playsound
import gtts


class voice(Commands):
    def __init__(
        self,
        ELEVENLABS_API_KEY: str = "",
        USE_MAC_OS_TTS: bool = False,
        USE_BRIAN_TTS: bool = True,
        ELEVENLABS_VOICE: str = "Josh",
        **kwargs,
    ):
        self.ELEVENLABS_API_KEY = ELEVENLABS_API_KEY
        self.USE_MAC_OS_TTS = USE_MAC_OS_TTS
        self.USE_BRIAN_TTS = USE_BRIAN_TTS
        self.ELEVENLABS_VOICE = ELEVENLABS_VOICE
        self.commands = {"Speak with TTS": self.speak}
        self._mutex = Semaphore(1)

    def speak(self, text: str, engine: str = "gtts") -> bool:
        with self._mutex:
            if engine == "elevenlabs" and self.ELEVENLABS_API_KEY:
                return self._elevenlabs_speech(text, self.ELEVENLABS_VOICE)
            elif engine == "macos" and self.USE_MAC_OS_TTS == "True":
                return self._macos_speech(text, self.ELEVENLABS_VOICE)
            elif engine == "brian" and self.USE_BRIAN_TTS == "True":
                return self._brian_speech(text)
            else:
                return self._gtts_speech(text)

    def _gtts_speech(self, text: str) -> bool:
        tts = gtts.gTTS(text)
        tts.save("speech.mp3")
        playsound("speech.mp3", True)
        os.remove("speech.mp3")
        return True

    def _brian_speech(self, text: str) -> bool:
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

    def _elevenlabs_speech(self, text: str, voice_index: int = 0) -> bool:
        voices = ["ErXwobaYiN019PkySvjV", "EXAVITQu4vr4xnSDxMaL"]
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.ELEVENLABS_API_KEY,
        }

        tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voices[voice_index]}"
        response = requests.post(tts_url, headers=headers, json={"text": text})

        if response.status_code == 200:
            with open("speech.mpeg", "wb") as f:
                f.write(response.content)
            playsound("speech.mpeg", True)
            os.remove("speech.mpeg")
            return True
        else:
            return False

    def _macos_speech(self, text: str, voice_index: int = 0) -> bool:
        if voice_index == 0:
            os.system(f'say "{text}"')
        elif voice_index == 1:
            os.system(f'say -v "Ava (Premium)" "{text}"')
        else:
            os.system(f'say -v Samantha "{text}"')
        return True
