"""
Google AI Provider Extension for AGiXT

This extension provides AI inference capabilities using Google AI Studio (Gemini) API,
supporting text generation, vision tasks, and text-to-speech.

Get your Google API key at: https://aistudio.google.com/

This is an AI Provider extension - it will be automatically discovered by AGiXT's
provider rotation system when configured with a valid API key.
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path
from Extensions import Extensions
from Globals import getenv, install_package_if_missing

install_package_if_missing("google-generativeai", "google.generativeai")
install_package_if_missing("gTTS", "gtts")

import google.generativeai as genai
import gtts as ts


class gemini(Extensions):
    """
    Google Gemini AI Provider - Gemini models supporting LLM, TTS, and vision.

    Get your API key at https://aistudio.google.com/app/apikey
    """

    CATEGORY = "AI Provider"
    friendly_name = "Google Gemini"

    # Services this AI provider supports
    SERVICES = ["llm", "tts", "vision"]

    def __init__(
        self,
        GOOGLE_API_KEY: str = "",
        GOOGLE_AI_MODEL: str = "gemini-2.5-flash-preview-04-17",
        GOOGLE_MAX_TOKENS: int = 1000000,
        GOOGLE_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        # Get from parameter or environment
        if not GOOGLE_API_KEY:
            GOOGLE_API_KEY = getenv("GOOGLE_API_KEY", "")
        if not GOOGLE_AI_MODEL or GOOGLE_AI_MODEL == "gemini-2.5-flash-preview-04-17":
            GOOGLE_AI_MODEL = getenv("GOOGLE_MODEL", "gemini-2.5-flash-preview-04-17")

        self.GOOGLE_API_KEY = GOOGLE_API_KEY
        self.AI_MODEL = (
            GOOGLE_AI_MODEL if GOOGLE_AI_MODEL else "gemini-2.5-flash-preview-04-17"
        )
        self.MAX_TOKENS = int(GOOGLE_MAX_TOKENS) if GOOGLE_MAX_TOKENS else 1000000
        self.AI_TEMPERATURE = float(GOOGLE_TEMPERATURE) if GOOGLE_TEMPERATURE else 0.7

        self.failure_count = 0

        # Check if configured
        self.configured = bool(
            self.GOOGLE_API_KEY
            and self.GOOGLE_API_KEY != ""
            and self.GOOGLE_API_KEY != "None"
        )

        # Commands that allow the AI to use this provider directly
        self.commands = {
            "Generate Response with Gemini": self.generate_response_command,
            "Text to Speech with Gemini": self.text_to_speech_command,
        }

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient", None)

    @staticmethod
    def services():
        """Return list of services this provider supports"""
        return ["llm", "tts", "vision"]

    def get_max_tokens(self):
        """Return the maximum token limit for this provider"""
        return self.MAX_TOKENS

    def is_configured(self):
        """Check if this provider is properly configured"""
        return self.configured

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        """
        Generate text using Google Gemini.

        Args:
            prompt: The input prompt
            tokens: Input token count (for budgeting)
            images: List of image paths for vision tasks
            stream: Whether to stream the response
            use_smartest: Use the smartest model

        Returns:
            Generated text response or stream object
        """
        if not self.configured:
            raise Exception("Google provider not configured - missing API key")

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

            if stream:
                # Use streaming API - return the response directly as it's an iterator
                response = await asyncio.to_thread(
                    model.generate_content,
                    contents=prompt,
                    generation_config=generation_config,
                    stream=True,
                )
                return response
            else:
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
            logging.error(f"Google Gemini Error: {e}")
            raise Exception(f"Gemini Error: {e}")

    async def text_to_speech(self, text: str) -> str:
        """
        Convert text to speech using Google TTS.

        Args:
            text: Text to convert to speech

        Returns:
            URL to the generated audio file
        """
        tts = ts.gTTS(text)
        filename = f"{uuid.uuid4()}.mp3"
        mp3_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        tts.save(mp3_path)
        agixt_uri = getenv("AGIXT_URI")
        return f"{agixt_uri}/outputs/{filename}"

    # Command methods for AI to use this provider directly
    async def generate_response_command(self, prompt: str) -> str:
        """
        Generate a response using Google Gemini.

        Args:
            prompt: The prompt to send to Gemini

        Returns:
            The generated text response from Gemini
        """
        return await self.inference(prompt=prompt)

    async def text_to_speech_command(self, text: str) -> str:
        """
        Convert text to speech using Google TTS.

        Args:
            text: The text to convert to speech

        Returns:
            URL to the generated audio file
        """
        return await self.text_to_speech(text=text)
