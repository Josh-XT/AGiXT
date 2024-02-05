from ApiClient import log_interaction
from Defaults import DEFAULT_USER
from Extensions import Extensions
import logging
import os
import base64
import io
import requests
import uuid

try:
    from whisper_cpp import Whisper
except ImportError:
    import sys
    import subprocess

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "whisper-cpp-pybind",
        ]
    )
    from whisper_cpp import Whisper

try:
    from pydub import AudioSegment
except ImportError:
    import sys
    import subprocess

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "pydub",
        ]
    )
    from pydub import AudioSegment


class voice_chat(Extensions):
    def __init__(self, WHISPER_MODEL="base.en", **kwargs):
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        if "agent_name" in kwargs:
            self.agent_name = kwargs["agent_name"]
        else:
            self.agent_name = "gpt4free"
        self.user = kwargs["user"] if "user" in kwargs else DEFAULT_USER
        self.tts_command = "Speak with TTS with Streamlabs Text to Speech"
        if "USE_STREAMLABS_TTS" in kwargs:
            if str(kwargs["USE_STREAMLABS_TTS"]).lower() == "true":
                self.tts_command = "Speak with TTS with Streamlabs Text to Speech"
        if "USE_GTTS" in kwargs:
            if str(kwargs["USE_GTTS"]).lower() == "true":
                self.tts_command = "Speak with GTTS"
        if "ELEVENLABS_API_KEY" in kwargs:
            if kwargs["ELEVENLABS_API_KEY"] != "":
                self.tts_command = "Speak with TTS Using Elevenlabs"
        if "USE_ALLTALK_TTS" in kwargs:
            if str(kwargs["USE_ALLTALK_TTS"]).lower() == "true":
                self.tts_command = "Speak with TTS with Alltalk Text to Speech"

        self.commands = {
            "Prompt with Voice": self.prompt_with_voice,
            "Command with Voice": self.command_with_voice,
            "Translate Text to Speech": self.text_to_speech,
            "Transcribe M4A Audio": self.transcribe_m4a_audio,
        }
        self.conversation_name = f"Voice Chat with {self.agent_name}"
        if "conversation_name" in kwargs:
            self.conversation_name = kwargs["conversation_name"]
        # https://huggingface.co/ggerganov/whisper.cpp
        if WHISPER_MODEL not in [
            "tiny",
            "tiny.en",
            "base",
            "base.en",
            "small",
            "small.en",
            "medium",
            "medium.en",
            "large-v1",
            "large-v2",
            "large-v3",
        ]:
            self.WHISPER_MODEL = "base.en"
        else:
            self.WHISPER_MODEL = WHISPER_MODEL
        os.makedirs(os.path.join(os.getcwd(), "models", "whispercpp"), exist_ok=True)
        self.model_path = os.path.join(
            os.getcwd(), "models", "whispercpp", f"ggml-{WHISPER_MODEL}.bin"
        )
        if not os.path.exists(self.model_path):
            r = requests.get(
                f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{WHISPER_MODEL}.bin",
                allow_redirects=True,
            )
            open(self.model_path, "wb").write(r.content)

    async def transcribe_audio_from_file(self, filename: str = "recording.wav"):
        w = Whisper(model_path=self.model_path)
        file_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        if not os.path.exists(file_path):
            raise RuntimeError(f"Failed to load audio: {filename} does not exist.")
        w.transcribe(file_path)
        return w.output()

    async def text_to_speech(self, text: str):
        # Get the audio response from the TTS engine and return it.
        audio_response = self.ApiClient.execute_command(
            agent_name=self.agent_name,
            command_name=self.tts_command,
            command_args={"text": text},
        )
        return f"{audio_response}"

    async def get_user_input(self, base64_audio, audio_format="m4a"):
        filename = f"{uuid.uuid4().hex}.wav"
        if audio_format.lower() != "wav":
            audio_data = base64.b64decode(base64_audio)
            audio_segment = AudioSegment.from_file(
                io.BytesIO(audio_data), format=audio_format.lower()
            )
            audio_segment = audio_segment.set_frame_rate(16000)
            file_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
            audio_segment.export(file_path, format="wav")
            with open(file_path, "rb") as f:
                audio = f.read()
            return f"{base64.b64encode(audio).decode('utf-8')}"
        else:
            user_audio = base64_audio
        # Transcribe the audio to text.
        user_input = await self.transcribe_audio_from_file(filename=filename)
        user_message = f"{user_input}\n#GENERATED_AUDIO:{user_audio}"
        log_interaction(
            agent_name=self.agent_name,
            conversation_name=self.conversation_name,
            role="USER",
            message=user_message,
            user=self.user,
        )
        logging.info(f"[Whisper]: Transcribed User Input: {user_input}")
        return user_input

    async def prompt_with_voice(
        self,
        base64_audio,
        audio_format="m4a",
        audio_variable="user_input",
        prompt_name="Custom Input",
        prompt_args={
            "context_results": 6,
            "inject_memories_from_collection_number": 0,
        },
        tts=False,
    ):
        user_input = await self.get_user_input(
            base64_audio=base64_audio, audio_format=audio_format
        )
        prompt_args[audio_variable] = user_input
        text_response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name=prompt_name,
            prompt_args=prompt_args,
        )
        if str(tts).lower() == "true":
            return self.text_to_speech(text=text_response)
        return f"{text_response}"

    async def command_with_voice(
        self,
        base64_audio,
        audio_format="m4a",
        audio_variable="data_to_correlate_with_input",
        command_name="Store information in my long term memory",
        command_args={"input": "Voice transcription from user"},
        tts=False,
    ):
        user_input = await self.get_user_input(
            base64_audio=base64_audio, audio_format=audio_format
        )
        command_args[audio_variable] = user_input
        text_response = self.ApiClient.execute_command(
            agent_name=self.agent_name,
            command_name=command_name,
            command_args=command_args,
            conversation_name="AGiXT Terminal",
        )
        if str(tts).lower() == "true":
            return self.text_to_speech(text=text_response)
        return f"{text_response}"

    async def convert_m4a_to_wav(
        self, base64_audio: str, filename: str = "recording.wav"
    ):
        # Convert the base64 audio to a 16k WAV format
        audio_data = base64.b64decode(base64_audio)
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data), format="m4a")
        audio_segment = audio_segment.set_frame_rate(16000)
        file_path = os.path.join(os.getcwd(), "WORKSPACE", filename)
        audio_segment.export(file_path, format="wav")
        with open(file_path, "rb") as f:
            audio = f.read()
        return f"{base64.b64encode(audio).decode('utf-8')}"

    async def transcribe_m4a_audio(
        self,
        base64_audio: str,
    ):
        # Convert from M4A to WAV
        filename = f"{uuid.uuid4().hex}.wav"
        user_audio = await self.convert_m4a_to_wav(
            base64_audio=base64_audio, filename=filename
        )
        # Transcribe the audio to text.
        user_input = await self.transcribe_audio_from_file(filename=filename)
        user_input.replace("[BLANK_AUDIO]", "")
        os.remove(os.path.join(os.getcwd(), "WORKSPACE", filename))
        return user_input
