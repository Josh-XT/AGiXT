from datetime import datetime, timedelta
from io import BytesIO
import subprocess
import threading
import requests
import logging
import wave
import time
import sys
import os


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
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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
        wake_functions=None,
    ):
        self.sdk = AGiXTSDK(base_uri=server, api_key=api_key)
        self.agent_name = agent_name
        self.wake_word = wake_word.lower()
        self.wake_functions = wake_functions or {"chat": self.default_voice_chat}
        if not conversation_name:
            self.conversation_name = datetime.now().strftime("%Y-%m-%d")
        else:
            self.conversation_name = conversation_name
        self.TRANSCRIPTION_MODEL = whisper_model
        self.audio = pyaudio.PyAudio()
        self.w = WhisperModel(
            self.TRANSCRIPTION_MODEL, download_root="models", device="cpu"
        )
        self.is_recording = False
        self.input_recording_thread = None
        self.output_recording_thread = None
        self.wake_word_thread = None
        self.vad = webrtcvad.Vad(3)  # Aggressiveness is 3 (highest)
        self.ps = Pocketsphinx(
            hmm=get_model_path("en-us"),
            lm=False,
            keyphrase=self.wake_word,
            kws_threshold=1e-20,
        )

    def transcribe_audio(self, audio_path, translate=False):
        segments, _ = self.w.transcribe(
            audio_path,
            task="transcribe" if not translate else "translate",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        return " ".join(segment.text for segment in segments)

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
            logging.error(f"Error in text-to-speech conversion: {e}")

    def continuous_record_and_transcribe(self, is_input):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        RECORD_SECONDS = 60  # Record in 1-minute chunks
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
        while self.is_recording:
            frames = []
            start_time = datetime.now()
            for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                if not self.is_recording:
                    break
                data = stream.read(CHUNK) if is_input else stream.write(b"\x00" * CHUNK)
                if is_input:
                    frames.append(data)
                else:
                    frames.append(data if data is not None else b"\x00" * CHUNK)
            end_time = datetime.now()
            if frames:  # Only process if we have recorded some audio
                audio_data = b"".join(frames)
                date_folder = start_time.strftime("%Y-%m-%d")
                os.makedirs(date_folder, exist_ok=True)
                filename = f"{date_folder}/{audio_type}_{start_time.strftime('%H-%M-%S')}-{end_time.strftime('%H-%M-%S')}.wav"
                with wave.open(filename, "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(self.audio.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(audio_data)
                transcription = self.transcribe_audio(filename)
                # save to agent memories if length of the transcription is greater than 10
                if len(transcription) > 10:
                    memory_text = f"Content of {audio_type} voice transcription from {start_time} to {end_time}:\n{transcription}"
                    self.sdk.learn_text(
                        agent_name=self.agent_name,
                        user_input=transcription,
                        text=memory_text,
                        collection_number=self.conversation_name,
                    )
                    logging.info(
                        f"Saved {audio_type} transcription to agent memories: {filename}"
                    )
        stream.stop_stream()
        stream.close()

    def default_voice_chat(self, text):
        logging.info(f"Sending text to agent: {text}")
        return self.sdk.chat(
            agent_name=self.agent_name,
            user_input=text,
            conversation=self.conversation_name,
            context_results=6,
        )

    def process_wake_word(self):
        # Capture a few seconds of audio after wake word detection
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
        # Process the transcription with the appropriate wake function
        for wake_word, wake_function in self.wake_functions.items():
            if wake_word.lower() in transcription.lower():
                response = wake_function(transcription)
                if response:
                    self.text_to_speech(response)
                break
        else:
            # If no wake word is found, use the default chat function
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

    def get_transcription_for_timerange(self, start_time, end_time, audio_type="both"):
        start_datetime = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end_datetime = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        transcriptions = []
        current_date = start_datetime.date()
        while current_date <= end_datetime.date():
            date_folder = current_date.strftime("%Y-%m-%d")
            if os.path.exists(date_folder):
                for filename in os.listdir(date_folder):
                    if filename.endswith(".txt"):
                        file_start_str = filename.split("_")[-1].split("-")[0]
                        file_end_str = (
                            filename.split("_")[-1].split("-")[1].split(".")[0]
                        )
                        file_start = datetime.strptime(
                            f"{current_date} {file_start_str}", "%Y-%m-%d %H:%M:%S"
                        )
                        file_end = datetime.strptime(
                            f"{current_date} {file_end_str}", "%Y-%m-%d %H:%M:%S"
                        )
                        if file_start <= end_datetime and file_end >= start_datetime:
                            if (
                                audio_type == "both"
                                or (
                                    audio_type == "input"
                                    and filename.startswith("input")
                                )
                                or (
                                    audio_type == "output"
                                    and filename.startswith("output")
                                )
                            ):
                                with open(
                                    os.path.join(date_folder, filename), "r"
                                ) as f:
                                    transcriptions.append(f.read())
            current_date += timedelta(days=1)
        return "\n".join(transcriptions)

    def start_recording(self):
        self.is_recording = True
        self.input_recording_thread = threading.Thread(
            target=self.continuous_record_and_transcribe, args=(True,)
        )
        self.output_recording_thread = threading.Thread(
            target=self.continuous_record_and_transcribe, args=(False,)
        )
        self.wake_word_thread = threading.Thread(target=self.listen_for_wake_word)
        self.input_recording_thread.start()
        self.output_recording_thread.start()
        self.wake_word_thread.start()

    def stop_recording(self):
        self.is_recording = False
        if self.input_recording_thread:
            self.input_recording_thread.join()
        if self.output_recording_thread:
            self.output_recording_thread.join()
        if self.wake_word_thread:
            self.wake_word_thread.join()

    def voice_chat(self, text):
        logging.info(f"Sending text to agent: {text}")
        return self.sdk.chat(
            agent_name=self.agent_name,
            user_input=text,
            conversation=self.conversation_name,
            context_results=10,
            conversation_results=10,
        )

    def listen(self):
        self.start_recording()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Stopping the recording...")
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
    parser.add_argument("--conversation_name", help="Name of the conversation")
    parser.add_argument(
        "--whisper_model", default="base.en", help="Whisper model for transcription"
    )
    parser.add_argument(
        "--wake_word",
        default="hey assistant",
        help="Wake word to trigger the assistant",
    )
    parser.add_argument(
        "--start_time",
        help="Start time for transcription retrieval (YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument(
        "--end_time", help="End time for transcription retrieval (YYYY-MM-DD HH:MM:SS)"
    )
    parser.add_argument(
        "--audio_type",
        choices=["input", "output", "both"],
        default="both",
        help="Type of audio to retrieve transcriptions for",
    )
    args = parser.parse_args()
    listener = AGiXTListen(
        server=args.server,
        api_key=args.api_key,
        agent_name=args.agent_name,
        whisper_model=args.whisper_model,
        wake_word=args.wake_word,
    )
    if args.start_time and args.end_time:
        transcriptions = listener.get_transcription_for_timerange(
            args.start_time, args.end_time, args.audio_type
        )
        print(f"Transcriptions for the specified time range ({args.audio_type}):")
        print(transcriptions)
    else:
        try:
            listener.start_recording()
        except KeyboardInterrupt:
            logging.info("Stopping the recording...")
        finally:
            listener.stop_recording()
            logging.info("Recording stopped.")
