import requests


class ElevenlabsProvider:
    """
    This provider uses the Elevenlabs API to generate text-to-speech audio. Get your Elevenlabs API key at <https://elevenlabs.io>.
    """

    def __init__(
        self,
        ELEVENLABS_API_KEY: str = "",
        ELEVENLABS_VOICE: str = "Josh",
        **kwargs,
    ):
        self.friendly_name = "Elevenlabs"
        self.MAX_TOKENS = 8192
        self.ELEVENLABS_API_KEY = ELEVENLABS_API_KEY
        self.ELEVENLABS_VOICE = ELEVENLABS_VOICE

    @staticmethod
    def services():
        return ["tts"]

    async def text_to_speech(self, text: str) -> bool:
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
            return response.content
        else:
            return "Failed to generate audio."
