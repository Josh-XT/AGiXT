import requests
import base64
import uuid
from Extensions import Extensions


class alltalk_tts(Extensions):
    def __init__(
        self,
        voice: str = "default",
        **kwargs,
    ):
        self.voice = voice
        self.commands = {
            "Speak with TTS with Alltalk Text to Speech": self.speak_with_alltalk_tts
        }

    async def speak_with_alltalk_tts(
        self,
        text: str,
    ):
        data = {
            "text": text,
            "voice": self.voice,
            "language": "en",
            "temperature": 0.7,
            "repetition_penalty": 10.0,
            "output_file": f"{uuid.uuid4()}.wav",
            "streaming": False,
        }
        response = requests.post(
            "http://alltalk-tts:7851/api/generate",
            json=data,
        )
        return f"{text}\n#GENERATED_AUDIO:{base64.b64encode(response.content).decode('utf-8')}"
