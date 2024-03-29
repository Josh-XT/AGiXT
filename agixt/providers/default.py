from providers.gpt4free import Gpt4freeProvider
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from AudioToText import AudioToText


class DefaultProvider:
    def __init__(
        self,
        AI_MODEL: str = "mixtral-8x7b",
        MAX_TOKENS: int = 16000,
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        TRANSCRIPTION_MODEL: str = "base",
        VOICE: str = "Brian",
        **kwargs
    ):
        self.AI_MODEL = AI_MODEL if AI_MODEL else "mixtral-8x7b"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 16000
        self.VOICE = VOICE if VOICE else "Brian"
        self.TRANSCRIPTION_MODEL = (
            TRANSCRIPTION_MODEL if TRANSCRIPTION_MODEL else "base"
        )
        self.chunk_size = 256

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        return await Gpt4freeProvider(
            AI_MODEL=self.AI_MODEL,
            MAX_TOKENS=self.MAX_TOKENS,
            AI_TEMPERATURE=self.AI_TEMPERATURE,
            AI_TOP_P=self.AI_TOP_P,
            VOICE=self.VOICE,
        ).inference(prompt=prompt, tokens=tokens, images=images)

    async def text_to_speech(self, text: str):
        return await Gpt4freeProvider(VOICE=self.VOICE).text_to_speech(text=text)

    async def embeddings(self, text: str):
        embedder = ONNXMiniLM_L6_V2()
        return embedder.__call__(input=[text])[0]

    async def transcribe_audio(self, audio_path: str):
        return await AudioToText(model=self.TRANSCRIPTION_MODEL).transcribe_audio(
            file=audio_path
        )

    async def translate_audio(self, audio_path: str):
        return await AudioToText(model=self.TRANSCRIPTION_MODEL).transcribe_audio(
            file=audio_path, translate=True
        )

    # Would be nice to add a generate_image method here, but I don't have a good default that doesn't require configuration yet.
