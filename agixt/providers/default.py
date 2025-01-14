from providers.gpt4free import Gpt4freeProvider
from providers.google import GoogleProvider
from onnxruntime import InferenceSession
from tokenizers import Tokenizer
from typing import List, cast, Union, Sequence
import numpy.typing as npt
from faster_whisper import WhisperModel
import os
import logging
import numpy as np

# Default provider uses:
# llm: gpt4free
# tts: google
# transcription: faster-whisper
# translation: faster-whisper
Vector = Union[Sequence[float], Sequence[int]]
Embedding = Vector
Embeddings = List[Embedding]
Document = str
Documents = List[Document]


class ONNXMiniLM_L6_V2:
    def __init__(self) -> None:
        self.tokenizer = None
        self.model = None

    def _normalize(self, v: npt.NDArray) -> npt.NDArray:
        norm = np.linalg.norm(v, axis=1)
        norm[norm == 0] = 1e-12
        return v / norm[:, np.newaxis]

    def _forward(self, documents: List[str], batch_size: int = 32) -> npt.NDArray:
        self.tokenizer = cast(Tokenizer, self.tokenizer)  # type: ignore
        self.model = cast(InferenceSession, self.model)  # type: ignore
        all_embeddings = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            encoded = [self.tokenizer.encode(d) for d in batch]
            input_ids = np.array([e.ids for e in encoded])
            attention_mask = np.array([e.attention_mask for e in encoded])
            onnx_input = {
                "input_ids": np.array(input_ids, dtype=np.int64),
                "attention_mask": np.array(attention_mask, dtype=np.int64),
                "token_type_ids": np.array(
                    [np.zeros(len(e), dtype=np.int64) for e in input_ids],
                    dtype=np.int64,
                ),
            }
            model_output = self.model.run(None, onnx_input)
            last_hidden_state = model_output[0]
            # Perform mean pooling with attention weighting
            input_mask_expanded = np.broadcast_to(
                np.expand_dims(attention_mask, -1), last_hidden_state.shape
            )
            embeddings = np.sum(last_hidden_state * input_mask_expanded, 1) / np.clip(
                input_mask_expanded.sum(1), a_min=1e-9, a_max=None
            )
            embeddings = self._normalize(embeddings).astype(np.float32)
            all_embeddings.append(embeddings)
        return np.concatenate(all_embeddings)

    def _init_model_and_tokenizer(self) -> None:
        if self.model is None and self.tokenizer is None:
            self.tokenizer = Tokenizer.from_file(
                os.path.join(os.getcwd(), "onnx", "tokenizer.json")
            )
            self.tokenizer.enable_truncation(max_length=256)
            self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=256)
            self.model = InferenceSession(
                os.path.join(os.getcwd(), "onnx", "model.onnx")
            )

    def __call__(self, texts: Documents) -> Embeddings:
        self._init_model_and_tokenizer()
        res = cast(Embeddings, self._forward(texts).tolist())
        return res


class DefaultProvider:
    """
    The default provider uses free or built-in services for various tasks like LLM, TTS, transcription, translation, and embeddings.
    """

    def __init__(
        self,
        DEFAULT_MODEL: str = "mixtral-8x7b",
        DEFAULT_MAX_TOKENS: int = 16000,
        **kwargs,
    ):
        self.friendly_name = "Default"
        self.AI_MODEL = DEFAULT_MODEL if DEFAULT_MODEL else "mixtral-8x7b"
        self.AI_TEMPERATURE = 0.7
        self.AI_TOP_P = 0.7
        self.MAX_TOKENS = DEFAULT_MAX_TOKENS if DEFAULT_MAX_TOKENS else 16000
        self.TRANSCRIPTION_MODEL = (
            "base"
            if "TRANSCRIPTION_MODEL" not in kwargs
            else kwargs["TRANSCRIPTION_MODEL"]
        )
        self.embedder = ONNXMiniLM_L6_V2()
        self.chunk_size = 256

    @staticmethod
    def services():
        return [
            "llm",
            "embeddings",
            "tts",
            "transcription",
            "translation",
        ]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        return await Gpt4freeProvider(
            AI_MODEL=self.AI_MODEL,
            VOICE=self.VOICE,
        ).inference(prompt=prompt, tokens=tokens, images=images)

    async def text_to_speech(self, text: str):
        return await GoogleProvider().text_to_speech(text=text)

    def embeddings(self, input) -> np.ndarray:
        return self.embedder.__call__(input=[input])[0]

    async def transcribe_audio(
        self,
        audio_path,
        translate=False,
    ):
        self.w = WhisperModel(
            self.TRANSCRIPTION_MODEL,
            download_root="models",
            device="cpu",
            compute_type="int8",
        )
        segments, _ = self.w.transcribe(
            audio_path,
            task="transcribe" if not translate else "translate",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        segments = list(segments)
        user_input = ""
        for segment in segments:
            user_input += segment.text
        logging.info(f"[STT] Transcribed User Input: {user_input}")
        return user_input

    async def translate_audio(self, audio_path: str):
        return await self.transcribe_audio(
            audio_path=audio_path,
            translate=True,
        )
