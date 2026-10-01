"""MiniMax speech synthesis for AGiXT.

Configure MINIMAX_API_KEY and select minimax_speech as a TTS provider, or enable
Text to Speech with MiniMax. MINIMAX_TTS_MODEL selects the speech model;
MINIMAX_TTS_REGION accepts global_en or cn_zh, and MINIMAX_TTS_VOICE accepts a
voice ID from the corresponding account. These settings also accept environment
values. Synthesis returns base64 WAV audio for the agent TTS pipeline, and the
command saves a WAV file in the current conversation workspace.

API reference: https://platform.minimax.io/docs/api-reference/speech-t2a-http
"""

import asyncio
import base64
import uuid
from pathlib import Path

import requests

from Extensions import Extensions
from Globals import getenv

TTS_ENDPOINTS = {
    "global_en": "https://api.minimax.io/v1/t2a_v2",
    "cn_zh": "https://api.minimaxi.com/v1/t2a_v2",
}
DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICE = "English_expressive_narrator"


class minimax_speech(Extensions):
    """MiniMax text-to-speech with configurable speech model, region, and voice."""

    CATEGORY = "AI Provider"
    friendly_name = "MiniMax Speech"
    SERVICES = ["tts"]

    def __init__(
        self,
        MINIMAX_API_KEY: str = "",
        MINIMAX_TTS_MODEL: str = DEFAULT_MODEL,
        MINIMAX_TTS_REGION: str = "global_en",
        MINIMAX_TTS_VOICE: str = DEFAULT_VOICE,
        **kwargs,
    ):
        self.MINIMAX_API_KEY = (
            MINIMAX_API_KEY or getenv("MINIMAX_API_KEY", "")
        ).strip()
        self.MODEL = MINIMAX_TTS_MODEL
        if not self.MODEL or self.MODEL == DEFAULT_MODEL:
            self.MODEL = getenv("MINIMAX_TTS_MODEL", DEFAULT_MODEL)
        region = MINIMAX_TTS_REGION
        if not region or region == "global_en":
            region = getenv("MINIMAX_TTS_REGION", "global_en")
        if region not in TTS_ENDPOINTS:
            raise ValueError("MINIMAX_TTS_REGION must be global_en or cn_zh")
        self.API_URI = TTS_ENDPOINTS[region]
        self.VOICE = MINIMAX_TTS_VOICE
        if not self.VOICE or self.VOICE == DEFAULT_VOICE:
            self.VOICE = getenv("MINIMAX_TTS_VOICE", DEFAULT_VOICE)
        self.configured = bool(
            self.MINIMAX_API_KEY
        ) and self.MINIMAX_API_KEY.lower() not in (
            "none",
            "null",
            "false",
            "0",
            "your_minimax_api_key",
        )
        self.MAX_TOKENS = 8192
        self.ApiClient = kwargs.get("ApiClient")
        self.conversation_directory = Path(
            kwargs.get("conversation_directory") or "./WORKSPACE"
        )
        self.output_url = kwargs.get("output_url") or (
            getenv("AGIXT_URI").rstrip("/") + "/outputs/"
        )
        self.commands = {"Text to Speech with MiniMax": self.text_to_speech_command}

    @staticmethod
    def services():
        return ["tts"]

    def get_max_tokens(self):
        return self.MAX_TOKENS

    def is_configured(self):
        return self.configured

    async def text_to_speech(self, text: str) -> str:
        """Synthesize text and return base64-encoded WAV audio for AGiXT."""
        if not self.configured:
            raise ValueError("MiniMax speech provider not configured")
        if not isinstance(text, str) or not text.strip() or len(text) >= 10000:
            raise ValueError("Speech text must contain 1 to 9999 characters")

        def synthesize():
            with requests.post(
                self.API_URI,
                headers={
                    "Authorization": f"Bearer {self.MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "text": text,
                    "stream": False,
                    "output_format": "hex",
                    "voice_setting": {"voice_id": self.VOICE},
                    "audio_setting": {"format": "wav"},
                },
                timeout=120,
            ) as response:
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("MiniMax speech returned an invalid response")
            status = payload.get("base_resp")
            if not isinstance(status, dict) or status.get("status_code") != 0:
                raise ValueError("MiniMax speech request failed")
            data = payload.get("data")
            if not isinstance(data, dict) or data.get("status") != 2:
                raise ValueError("MiniMax speech did not return completed audio")
            audio_hex = data.get("audio")
            if not isinstance(audio_hex, str) or not audio_hex.strip():
                raise ValueError("MiniMax speech returned no audio")
            try:
                audio = bytes.fromhex(audio_hex)
            except ValueError as error:
                raise ValueError(
                    "MiniMax speech returned invalid hexadecimal audio"
                ) from error
            return base64.b64encode(audio).decode("ascii")

        return await asyncio.to_thread(synthesize)

    async def text_to_speech_command(self, text: str) -> str:
        """Save synthesized WAV audio and return its conversation output URL."""
        audio = base64.b64decode(await self.text_to_speech(text))
        self.conversation_directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}.wav"
        (self.conversation_directory / filename).write_bytes(audio)
        return f"{self.output_url.rstrip('/')}/{filename}"
