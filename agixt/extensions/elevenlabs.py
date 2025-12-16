"""
ElevenLabs AI Provider Extension for AGiXT

This extension provides text-to-speech capabilities using the ElevenLabs API.
Get your API key at https://elevenlabs.io

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import uuid
import requests
from Extensions import Extensions
from Globals import getenv


class elevenlabs(Extensions):
    """
    ElevenLabs AI Provider - High-quality text-to-speech

    Get your API key at https://elevenlabs.io
    """

    CATEGORY = "AI Provider"
    friendly_name = "ElevenLabs"
    SERVICES = ["tts"]

    def __init__(
        self,
        ELEVENLABS_API_KEY: str = "",
        ELEVENLABS_VOICE: str = "ErXwobaYiN019PkySvjV",
        **kwargs,
    ):
        if not ELEVENLABS_API_KEY:
            ELEVENLABS_API_KEY = getenv("ELEVENLABS_API_KEY", "")

        self.ELEVENLABS_API_KEY = ELEVENLABS_API_KEY
        self.ELEVENLABS_VOICE = (
            ELEVENLABS_VOICE if ELEVENLABS_VOICE else "ErXwobaYiN019PkySvjV"
        )
        self.MAX_TOKENS = 8192

        self.configured = bool(
            self.ELEVENLABS_API_KEY and self.ELEVENLABS_API_KEY != ""
        )

        self.commands = {
            "Text to Speech with ElevenLabs": self.text_to_speech_command,
        }

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient", None)

    @staticmethod
    def services():
        return ["tts"]

    def get_max_tokens(self):
        return self.MAX_TOKENS

    def is_configured(self):
        return self.configured

    async def text_to_speech(self, text: str) -> bytes:
        """
        Convert text to speech using ElevenLabs TTS.

        Args:
            text: Text to convert to speech

        Returns:
            Audio content as bytes
        """
        if not self.configured:
            raise Exception("ElevenLabs provider not configured")

        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.ELEVENLABS_API_KEY,
        }

        try:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.ELEVENLABS_VOICE}",
                headers=headers,
                json={"text": text},
            )
            response.raise_for_status()
            return response.content
        except Exception:
            # Try with default voice
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/ErXwobaYiN019PkySvjV",
                headers=headers,
                json={"text": text},
            )
            if response.status_code == 200:
                return response.content
            raise Exception("Failed to generate audio")

    async def text_to_speech_command(self, text: str) -> str:
        """
        Convert text to speech using ElevenLabs TTS.

        Args:
            text: The text to convert to speech

        Returns:
            URL to the generated audio file
        """
        audio_bytes = await self.text_to_speech(text=text)
        filename = f"{uuid.uuid4()}.mp3"
        audio_path = f"./WORKSPACE/{filename}"
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        agixt_uri = getenv("AGIXT_URI")
        return f"{agixt_uri}/outputs/{filename}"
