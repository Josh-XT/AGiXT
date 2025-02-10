import asyncio
import os
from pathlib import Path
from Globals import getenv

try:
    import google.generativeai as genai  # Primary import attempt
except ImportError:
    import sys
    import subprocess

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "google-generativeai"]
    )
    import google.generativeai as genai  # Import again after installation

try:
    import gtts as ts
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "gTTS"])
    import gtts as ts

import uuid


class GoogleProvider:
    """
    This provider uses the Google AI Studio API to generate text from prompts. Get your Google API key at <https://aistudio.google.com/>.
    """

    def __init__(
        self,
        GOOGLE_API_KEY: str = "",
        GOOGLE_MODEL: str = "gemini-2.0-flash-exp",
        GOOGLE_MAX_TOKENS: int = 1000000,
        GOOGLE_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.friendly_name = "Google AI Studio"
        self.requirements = ["google-generativeai", "gTTS", "pydub"]
        self.GOOGLE_API_KEY = GOOGLE_API_KEY
        self.AI_MODEL = GOOGLE_MODEL
        self.MAX_TOKENS = GOOGLE_MAX_TOKENS
        self.AI_TEMPERATURE = GOOGLE_TEMPERATURE

    @staticmethod
    def services():
        return ["llm", "tts", "vision"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        if not self.GOOGLE_API_KEY or self.GOOGLE_API_KEY == "None":
            return "Please set your Google API key in the Agent Management page."
        try:
            genai.configure(api_key=self.GOOGLE_API_KEY)
            generation_config = genai.types.GenerationConfig(
                temperature=float(self.AI_TEMPERATURE)
            )
            model = genai.GenerativeModel(
                model_name=self.AI_MODEL,
                generation_config=generation_config,
            )
            new_prompt = []
            if images:
                for image in images:
                    file_extension = Path(image).suffix
                    new_prompt.append(
                        {
                            "mime_type": f"image/{file_extension}",
                            "data": Path(image).read_bytes(),
                        }
                    )
                new_prompt.append(prompt)
                prompt = new_prompt
            response = await asyncio.to_thread(
                model.generate_content,
                contents=prompt,
                generation_config=generation_config,
            )
            if response.parts:
                generated_text = "".join(part.text for part in response.parts)
            else:
                generated_text = "".join(
                    part.text for part in response.candidates[0].content.parts
                )
            return generated_text
        except Exception as e:
            raise Exception(f"Gemini Error: {e}")

    async def text_to_speech(self, text: str):
        tts = ts.gTTS(text)
        filename = f"{uuid.uuid4()}.mp3"
        mp3_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        tts.save(mp3_path)
        agixt_uri = getenv("AGIXT_URI")
        return f"{agixt_uri}/outputs/{filename}"
