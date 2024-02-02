import requests
import base64
import uuid
import os
from Extensions import Extensions


class alltalk_tts(Extensions):
    def __init__(
        self,
        USE_ALLTALK_TTS: bool = False,
        ALLTALK_URI: str = "http://alltalk-tts:7851",
        ALLTALK_VOICE: str = "default",
        **kwargs,
    ):
        self.ALLTALK_URI = ALLTALK_URI
        self.ALLTALK_VOICE = ALLTALK_VOICE
        self.USE_ALLTALK_TTS = USE_ALLTALK_TTS
        if USE_ALLTALK_TTS:
            self.commands = {
                "Speak with TTS with Alltalk Text to Speech": self.speak_with_alltalk_tts,
                "Get list of Alltalk TTS Voices": self.get_voices,
            }

    async def get_voices(self):
        voices = []
        for file in os.listdir(os.path.join(os.getcwd(), "voices")):
            if file.endswith(".wav"):
                voices.append(file[:-4])
        return voices

    async def speak_with_alltalk_tts(
        self,
        text: str,
    ):
        output_file = f"{uuid.uuid4()}.wav"
        file_path = os.path.join(os.getcwd(), "WORKSPACE", "outputs", output_file)
        os.makedirs(
            os.path.dirname(os.path.join(os.getcwd(), "WORKSPACE", "outputs")),
            exist_ok=True,
        )
        data = {
            "text": text,
            "voice": self.ALLTALK_VOICE,
            "language": "en",
            "temperature": 0.7,
            "repetition_penalty": 10.0,
            "output_file": output_file,
            "streaming": False,
        }
        response = requests.post(
            f"{self.ALLTALK_URI}/api/generate",
            json=data,
        )
        if response.status_code != 200:
            return f"Error: {response.text}"
        with open(file_path, "rb") as f:
            wav_content = f.read()
        new_response = (
            f"{text}\n#GENERATED_AUDIO:{base64.b64encode(wav_content).decode('utf-8')}"
        )
        os.remove(file_path)
        return new_response
