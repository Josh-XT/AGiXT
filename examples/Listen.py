import base64
import threading
import sys
import subprocess
import wave
import os
import uuid
from io import BytesIO
from datetime import datetime

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests
try:
    import pyaudio
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyaudio"])
    import pyaudio
try:
    import webrtcvad
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "webrtcvad"])
    import webrtcvad
try:
    import numpy as np
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
    import numpy as np
try:
    from agixtsdk import AGiXTSDK
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "agixtsdk"])
    from agixtsdk import AGiXTSDK


audio = pyaudio.PyAudio()


class AGiXTListen:
    def __init__(
        self,
        server="http://localhost:7437",
        api_key="",
        agent_name="gpt4free",
        whisper_model="",
        wake_functions={},
    ):
        self.sdk = AGiXTSDK(base_uri=server, api_key=api_key)
        self.agent_name = agent_name
        self.wake_functions = (
            wake_functions
            if wake_functions != {}
            else {
                "chat": self.voice_chat,
                "instruct": self.voice_instruct,
            }
        )
        self.conversation_name = datetime.now().strftime("%Y-%m-%d")
        self.w = None
        if whisper_model != "":
            try:
                from whisper_cpp import Whisper
            except ImportError:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "whisper-cpp-pybind"]
                )
                try:
                    from whisper_cpp import Whisper
                except:
                    whisper_model = ""
            if whisper_model != "":
                whisper_model = whisper_model.lower()
                if whisper_model not in [
                    "tiny",
                    "tiny.en",
                    "base",
                    "base.en",
                    "small",
                    "small.en",
                    "medium",
                    "medium.en",
                    "large",
                    "large-v1",
                ]:
                    whisper_model = "base.en"
                os.makedirs(
                    os.path.join(os.getcwd(), "models", "whispercpp"), exist_ok=True
                )
                model_path = os.path.join(
                    os.getcwd(), "models", "whispercpp", f"ggml-{whisper_model}.bin"
                )
                if not os.path.exists(model_path):
                    r = requests.get(
                        f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{whisper_model}.bin",
                        allow_redirects=True,
                    )
                    open(model_path, "wb").write(r.content)
                self.w = Whisper(model_path=model_path)

    def process_audio_data(self, frames, rms_threshold=500):
        audio_data = b"".join(frames)
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        rms = np.sqrt(np.mean(audio_np**2))
        if rms > rms_threshold:
            buffer = BytesIO()
            with wave.open(buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
                wf.setframerate(16000)
                wf.writeframes(b"".join(frames))
            wav_buffer = buffer.getvalue()
            base64_audio = base64.b64encode(wav_buffer).decode()
            thread = threading.Thread(
                target=self.transcribe_audio,
                args=(base64_audio),
            )
            thread.start()

    def transcribe_audio(self, base64_audio):
        if self.w:
            filename = f"{uuid.uuid4().hex}.wav"
            file_path = os.path.join(os.getcwd(), filename)
            if not os.path.exists(file_path):
                raise RuntimeError(f"Failed to load audio: {filename} does not exist.")
            self.w.transcribe(file_path)
            transcribed_text = self.w.output()
            os.remove(os.path.join(os.getcwd(), filename))
        else:
            transcribed_text = self.sdk.execute_command(
                agent_name=self.agent_name,
                command_name="Transcribe WAV Audio",
                command_args={"base64_audio": base64_audio},
                conversation_name="AGiXT Terminal",
            )
            transcribed_text = transcribed_text.replace("[BLANK_AUDIO]", "")
        for wake_word, wake_function in self.wake_functions.items():
            if wake_word.lower() in transcribed_text.lower():
                print("Wake word detected! Executing wake function...")
                if wake_function:
                    response = wake_function(transcribed_text)
                else:
                    response = self.voice_chat(text=transcribed_text)
                if response:
                    tts_response = self.sdk.execute_command(
                        agent_name=self.agent_name,
                        command_name="Translate Text to Speech",
                        command_args={
                            "text": response,
                        },
                        conversation_name=datetime.now().strftime("%Y-%m-%d"),
                    )
                    tts_response = tts_response.replace("#GENERATED_AUDIO:", "")
                    generated_audio = base64.b64decode(tts_response)
                    stream = audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        output=True,
                    )
                    stream.write(generated_audio)
                    stream.stop_stream()
                    stream.close()

    def listen(self):
        print("Listening for wake word...")
        vad = webrtcvad.Vad(1)
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=320,
        )
        frames = []
        silence_frames = 0
        while True:
            data = stream.read(320)
            frames.append(data)
            is_speech = vad.is_speech(data, 16000)
            if not is_speech:
                silence_frames += 1
                if silence_frames > 1 * 16000 / 320:
                    self.process_audio_data(frames)
                    frames = []  # Clear frames after processing
                    silence_frames = 0
            else:
                silence_frames = 0

    # Helper function to instruct the agent to do something.
    # Wake word function takes one input only, the transcribed text.
    def voice_chat(self, text):
        print(f"Sending text to agent: {text}")
        text_response = self.sdk.chat(
            agent_name=self.agent_name,
            user_input=text,
            conversation=self.conversation_name,
            context_results=6,
        )
        return text_response

    def voice_instruct(self, text):
        print(f"Sending text to agent: {text}")
        text_response = self.sdk.instruct(
            agent_name=self.agent_name,
            user_input=text,
            conversation=self.conversation_name,
        )
        return text_response


# AGiXTListen is a class that listens for a wake word and then executes an AGiXT function.
# The default wake function is to use the AGiXT instruct function which will prompt the agent to use available commands before responding.
# Example usage:
# python Listen.py --server http://localhost:7437 --agent_name gpt4free --api_key 1234
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    # Your AGiXT server URL
    parser.add_argument("--server", default="http://localhost:7437")
    # Your AGiXT API key
    parser.add_argument("--api_key", default="")
    # The name of the agent that will be listening
    parser.add_argument("--agent_name", default="gpt4free")
    # Setting a model will force transcription to happen locally instead of over API.
    # Low resource devices like Raspberry Pi Zero W cannot run Whisper and will need to use API.
    # Models: tiny, tiny.en, base, base.en, small, small.en, medium, medium.en, large, large-v1
    parser.add_argument("--whisper_model", default="")
    args = parser.parse_args()
    listener = AGiXTListen(
        server=args.server,
        api_key=args.api_key,
        agent_name=args.agent_name,
        whisper_model=args.whisper_model,
        wake_functions={},
    )
    listener.listen()
