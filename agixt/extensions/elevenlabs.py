from Extensions import Extensions
import os
import requests
from playsound import playsound


class elevenlabs(Extensions):
    def __init__(
        self,
        ELEVENLABS_API_KEY: str = "",
        ELEVENLABS_VOICE: str = "Josh",
        **kwargs,
    ):
        self.ELEVENLABS_API_KEY = ELEVENLABS_API_KEY
        self.ELEVENLABS_VOICE = ELEVENLABS_VOICE
        self.commands = {"Speak with TTS Using Elevenlabs": self.speak_with_elevenlabs}

    def speak_with_elevenlabs(self, text: str, voice_index: int = 0) -> bool:
        voices = ["ErXwobaYiN019PkySvjV", "EXAVITQu4vr4xnSDxMaL"]
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.ELEVENLABS_VOICE,
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
