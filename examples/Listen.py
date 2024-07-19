import datetime
from io import BytesIO
import subprocess
import threading
import requests
import logging
import wave
import time
import sys
import os
import signal
import traceback

try:
    import pyaudio
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyaudio"])
    import pyaudio

try:
    from agixtsdk import AGiXTSDK
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "agixtsdk"])
    from agixtsdk import AGiXTSDK

try:
    from faster_whisper import WhisperModel
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "faster-whisper"])
    from faster_whisper import WhisperModel

try:
    import webrtcvad
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "webrtcvad"])
    import webrtcvad

try:
    from pocketsphinx import Pocketsphinx, get_model_path
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pocketsphinx"])
    from pocketsphinx import Pocketsphinx, get_model_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="agixt_listen.log",
)


class AGiXTListen:
    def __init__(
        self,
        server="http://localhost:7437",
        api_key="",
        agent_name="gpt4free",
        conversation_name="",
        whisper_model="base.en",
        wake_word="hey assistant",
    ):
        self.sdk = AGiXTSDK(base_uri=server, api_key=api_key)
        self.agent_name = agent_name
        self.wake_word = wake_word.lower()
        self.wake_functions = {"chat": self.default_voice_chat}
        self.conversation_name = conversation_name or datetime.datetime.now().strftime(
            "%Y-%m-%d"
        )
        self.conversation_history = self.sdk.get_conversation(
            agent_name=self.agent_name,
            conversation=self.conversation_name,
            limit=20,
            page=1,
        )
        self.TRANSCRIPTION_MODEL = whisper_model
        self.audio = pyaudio.PyAudio()
        self.w = WhisperModel(
            self.TRANSCRIPTION_MODEL, download_root="models", device="cpu"
        )
        self.is_recording = False
        self.input_recording_thread = None
        self.output_recording_thread = None
        self.wake_word_thread = None
        self.conversation_check_thread = None
        self.vad = webrtcvad.Vad(3)  # Aggressiveness is 3 (highest)
        self.ps = Pocketsphinx(
            hmm=get_model_path("en-us"),
            lm=False,
            keyphrase=self.wake_word,
            kws_threshold=1e-20,
        )
        self.is_speaking_activity = False

    def transcribe_audio(self, audio_path, translate=False):
        try:
            segments, _ = self.w.transcribe(
                audio_path,
                task="transcribe" if not translate else "translate",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            return " ".join(segment.text for segment in segments)
        except Exception as e:
            logging.error(f"Error in transcribe_audio: {str(e)}")
            logging.debug(traceback.format_exc())
            return ""

    def text_to_speech(self, text):
        try:
            tts_url = self.sdk.text_to_speech(
                agent_name=self.agent_name,
                text=text,
            )
            response = requests.get(tts_url)
            generated_audio = response.content
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                output=True,
            )
            stream.write(generated_audio)
            stream.stop_stream()
            stream.close()
        except Exception as e:
            logging.error(f"Error in text-to-speech conversion: {str(e)}")
            logging.debug(traceback.format_exc())

    def continuous_record_and_transcribe(self, is_input):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        RECORD_SECONDS = 60  # 60-second chunks for continuous recording
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=is_input,
            output=not is_input,
            frames_per_buffer=CHUNK,
        )
        audio_type = "input" if is_input else "output"
        logging.info(
            f"Starting continuous recording and transcription for {audio_type} audio..."
        )
        try:
            while self.is_recording:
                frames = []
                start_time = datetime.datetime.now()
                for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                    if not self.is_recording:
                        break
                    if is_input:
                        data = stream.read(CHUNK)
                        frames.append(data)
                    else:
                        if not self.is_speaking_activity:
                            data = stream.write(b"\x00" * CHUNK)
                            frames.append(data if data is not None else b"\x00" * CHUNK)
                        else:
                            # Skip recording when speaking activity messages
                            stream.write(b"\x00" * CHUNK)
                if frames:
                    self.process_audio_chunk(frames, is_input, start_time)
        except Exception as e:
            logging.error(f"Error in continuous recording and transcription: {str(e)}")
            logging.debug(traceback.format_exc())
        finally:
            stream.stop_stream()
            stream.close()

    def process_audio_chunk(self, frames, is_input, start_time):
        audio_data = b"".join(frames)
        audio_type = "input" if is_input else "output"
        date_folder = start_time.strftime("%Y-%m-%d")
        os.makedirs(date_folder, exist_ok=True)
        filename = f"{date_folder}/{audio_type}_{start_time.strftime('%H-%M-%S')}.wav"
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(audio_data)
        transcription = self.transcribe_audio(filename)
        if len(transcription) > 10:
            memory_text = f"Content of {audio_type} voice transcription from {start_time}:\n{transcription}"
            self.sdk.learn_text(
                agent_name=self.agent_name,
                user_input=transcription,
                text=memory_text,
                collection_number=self.conversation_name,
            )
            logging.info(
                f"Saved {audio_type} transcription to agent memories: {filename}"
            )

    def default_voice_chat(self, text):
        logging.info(f"Sending text to agent: {text}")
        return self.sdk.chat(
            agent_name=self.agent_name,
            user_input=text,
            conversation=self.conversation_name,
            context_results=6,
        )

    def process_wake_word(self):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        RECORD_SECONDS = 5
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        frames = []
        for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK)
            frames.append(data)
        stream.stop_stream()
        stream.close()
        audio_data = b"".join(frames)
        transcription = self.transcribe_audio(BytesIO(audio_data))
        for wake_word, wake_function in self.wake_functions.items():
            if wake_word.lower() in transcription.lower():
                response = wake_function(transcription)
                if response:
                    self.text_to_speech(response)
                break
        else:
            response = self.default_voice_chat(transcription)
            if response:
                self.text_to_speech(response)

    def listen_for_wake_word(self):
        CHUNK = 480  # 30ms at 16kHz
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        logging.info(f"Listening for wake word: '{self.wake_word}'")
        while self.is_recording:
            frame = stream.read(CHUNK)
            is_speech = self.vad.is_speech(frame, RATE)

            if is_speech:
                self.ps.start_utt()
                self.ps.process_raw(frame, False, False)
                if self.ps.hyp():
                    logging.info(f"Wake word detected: {self.wake_word}")
                    self.process_wake_word()
                self.ps.end_utt()
        stream.stop_stream()
        stream.close()

    def check_conversation_updates(self):
        while self.is_recording:
            time.sleep(2)  # Check every 2 seconds
            new_history = self.sdk.get_conversation(
                agent_name=self.agent_name,
                conversation=self.conversation_name,
                limit=20,
                page=1,
            )
            new_entries = [
                entry for entry in new_history if entry not in self.conversation_history
            ]
            for entry in new_entries:
                if entry.startswith("[ACTIVITY]"):
                    activity_message = entry.split("[ACTIVITY]")[1].strip()
                    logging.info(f"Received activity message: {activity_message}")
                    self.speak_activity(activity_message)
            self.conversation_history = new_history

    def speak_activity(self, message):
        self.is_speaking_activity = True
        self.text_to_speech(message)
        self.is_speaking_activity = False

    def start_recording(self):
        self.is_recording = True
        self.input_recording_thread = threading.Thread(
            target=self.continuous_record_and_transcribe, args=(True,)
        )
        self.output_recording_thread = threading.Thread(
            target=self.continuous_record_and_transcribe, args=(False,)
        )
        self.wake_word_thread = threading.Thread(target=self.listen_for_wake_word)
        self.conversation_check_thread = threading.Thread(
            target=self.check_conversation_updates
        )
        self.input_recording_thread.start()
        self.output_recording_thread.start()
        self.wake_word_thread.start()
        self.conversation_check_thread.start()

    def stop_recording(self):
        self.is_recording = False
        if self.input_recording_thread:
            self.input_recording_thread.join()
        if self.output_recording_thread:
            self.output_recording_thread.join()
        if self.wake_word_thread:
            self.wake_word_thread.join()
        if self.conversation_check_thread:
            self.conversation_check_thread.join()

    def voice_chat(self, text):
        logging.info(f"Sending text to agent: {text}")
        return self.sdk.chat(
            agent_name=self.agent_name,
            user_input=text,
            conversation=self.conversation_name,
            context_results=10,
            conversation_results=10,
        )

    def graceful_shutdown(self, signum, frame):
        logging.info("Received shutdown signal. Stopping recording...")
        self.stop_recording()
        logging.info("Recording stopped. Exiting...")
        sys.exit(0)

    def listen(self):
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)
        self.start_recording()
        try:
            while True:
                time.sleep(1)
        except Exception as e:
            logging.error(f"Unexpected error in listen method: {str(e)}")
            logging.debug(traceback.format_exc())
        finally:
            self.stop_recording()
            logging.info("Recording stopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="AGiXT Voice Assistant with Continuous Recording"
    )
    parser.add_argument(
        "--server", default="http://localhost:7437", help="AGiXT server URL"
    )
    parser.add_argument("--api_key", default="", help="AGiXT API key")
    parser.add_argument("--agent_name", default="gpt4free", help="Name of the agent")
    parser.add_argument(
        "--conversation_name", default="", help="Name of the conversation"
    )
    parser.add_argument(
        "--whisper_model", default="base.en", help="Whisper model for transcription"
    )
    parser.add_argument(
        "--wake_word",
        default="hey assistant",
        help="Wake word to trigger the assistant",
    )
    args = parser.parse_args()
    try:
        listener = AGiXTListen(
            server=args.server,
            api_key=args.api_key,
            agent_name=args.agent_name,
            conversation_name=args.conversation_name,
            whisper_model=args.whisper_model,
            wake_word=args.wake_word,
        )
        listener.listen()
    except Exception as e:
        logging.error(f"Error initializing or running AGiXTListen: {str(e)}")
        logging.debug(traceback.format_exc())
