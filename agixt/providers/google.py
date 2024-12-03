import asyncio
import os
from pathlib import Path

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

from pydub import AudioSegment
import uuid


class GoogleProvider:
    def __init__(
        self,
        GOOGLE_API_KEY: str = "None",
        AI_MODEL: str = "gemini-1.5-pro-002",
        MAX_TOKENS: int = 2000000,
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.requirements = ["google-generativeai", "gTTS", "pydub"]
        self.GOOGLE_API_KEY = GOOGLE_API_KEY
        self.AI_MODEL = AI_MODEL
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_TEMPERATURE = AI_TEMPERATURE

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
            return f"Gemini Error: {e}"

    async def text_to_speech(self, text: str):
        try:
            tts = ts.gTTS(text)
            mp3_path = os.path.join(os.getcwd(), "WORKSPACE", f"{uuid.uuid4()}.mp3")
            wav_path = os.path.join(os.getcwd(), "WORKSPACE", f"{uuid.uuid4()}.wav")

            print(f"Saving MP3 to: {mp3_path}")  # Debug logging
            tts.save(mp3_path)

            if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
                raise Exception("MP3 file is empty or not created")

            print("Converting to WAV")  # Debug logging
            audio = AudioSegment.from_mp3(mp3_path)
            audio.export(wav_path, format="wav")

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
                raise Exception("WAV file is empty or not created")

            with open(wav_path, "rb") as f:
                audio_content = f.read()

            print(f"Audio content size: {len(audio_content)} bytes")  # Debug logging
            return audio_content

        except Exception as e:
            print(f"TTS Error: {e}")  # Error logging
            raise
        finally:
            # Cleanup
            for path in [mp3_path, wav_path]:
                if os.path.exists(path):
                    os.remove(path)
