from faster_whisper import WhisperModel

WhisperModel("base", download_root="models", device="cpu", compute_type="int8")
