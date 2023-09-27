from Extensions import Extensions
import requests


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

    async def speak_with_elevenlabs(self, text: str) -> bool:
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.ELEVENLABS_VOICE,
        }
        try:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.ELEVENLABS_VOICE}",
                headers=headers,
                json={"text": text},
            )
            response.raise_for_status()
        except:
            self.ELEVENLABS_VOICE = "ErXwobaYiN019PkySvjV"
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.ELEVENLABS_VOICE}",
                headers=headers,
                json={"text": text},
            )
        if response.status_code == 200:
            # Return the base64 audio/wav
            return f"#GENERATED_AUDIO:{response.content.decode('utf-8')}"
        else:
            return "Failed to generate audio."
