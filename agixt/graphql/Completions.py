from typing import List, Dict, Any, Optional
import strawberry
import uuid
import time
from fastapi import HTTPException, UploadFile
from strawberry.file_uploads import Upload
from Models import (
    ChatCompletions,
    EmbeddingModel,
    TextToSpeech,
    ImageCreation,
    ChatCompletionResponse,
    EmbeddingResponse,
    AudioTranscriptionResponse,
    AudioTranslationResponse,
    TextToSpeechResponse,
    ImageGenerationResponse,
)
from endpoints.Completions import (
    chat_completion as rest_chat_completion,
    embedding as rest_embedding,
    speech_to_text as rest_speech_to_text,
    translate_audio as rest_translate_audio,
    text_to_speech as rest_text_to_speech,
    generate_image as rest_generate_image,
)
from ApiClient import verify_api_key


# Strawberry types for inputs
@strawberry.input
class ChatCompletionsInput:
    model: str
    messages: List[Dict[str, str]]
    temperature: Optional[float] = 0.9
    top_p: Optional[float] = 1.0
    tools: Optional[List[Dict[str, Any]]] = None
    tools_choice: Optional[str] = "auto"
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None
    max_tokens: Optional[int] = 4096
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = "Chat"


@strawberry.input
class EmbeddingInput:
    input: str
    model: str
    user: Optional[str] = None


@strawberry.input
class TextToSpeechInput:
    input: str
    model: Optional[str] = "XT"
    voice: Optional[str] = "default"
    language: Optional[str] = "en"
    user: Optional[str] = None


@strawberry.input
class ImageGenerationInput:
    prompt: str
    model: Optional[str] = "dall-e-3"
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"


# Output types
@strawberry.type
class ChatChoice:
    message: Dict[str, Any]
    finish_reason: Optional[str]
    index: int


@strawberry.type
class ChatCompletionResponseType:
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Dict[str, int]


@strawberry.type
class EmbeddingData:
    embedding: List[float]
    index: int
    object: str


@strawberry.type
class EmbeddingResponseType:
    data: List[EmbeddingData]
    model: str
    object: str
    usage: Dict[str, int]


@strawberry.type
class AudioResponse:
    text: str


@strawberry.type
class TextToSpeechResponseType:
    url: str


@strawberry.type
class ImageData:
    url: str


@strawberry.type
class ImageGenerationResponseType:
    created: int
    data: List[ImageData]


# Helper for auth
async def get_user_and_auth_from_context(info):
    request = info.context["request"]
    try:
        user = await verify_api_key(request)
        auth = request.headers.get("authorization")
        return user, auth
    except HTTPException as e:
        raise Exception(str(e.detail))


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_chat_completion(
        self, info, input: ChatCompletionsInput
    ) -> ChatCompletionResponseType:
        """Create a chat completion"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            result = await rest_chat_completion(
                prompt=ChatCompletions(**input.__dict__), user=user, authorization=auth
            )
            return ChatCompletionResponseType(**result.__dict__)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def create_embedding(
        self, info, input: EmbeddingInput
    ) -> EmbeddingResponseType:
        """Create text embeddings"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            result = await rest_embedding(
                embedding=EmbeddingModel(**input.__dict__),
                user=user,
                authorization=auth,
            )
            return EmbeddingResponseType(**result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def create_speech_transcription(
        self,
        info,
        file: Upload,
        model: str = "base",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: Optional[str] = "json",
        temperature: Optional[float] = 0.0,
    ) -> AudioResponse:
        """Transcribe audio to text"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            # Convert strawberry Upload to FastAPI UploadFile
            contents = await file.read()
            upload_file = UploadFile(
                filename=file.filename, file=contents, content_type=file.content_type
            )
            result = await rest_speech_to_text(
                file=upload_file,
                model=model,
                language=language,
                prompt=prompt,
                response_format=response_format,
                temperature=temperature,
                user=user,
                authorization=auth,
            )
            return AudioResponse(**result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def create_audio_translation(
        self,
        info,
        file: Upload,
        model: str = "base",
        prompt: Optional[str] = None,
        response_format: Optional[str] = "json",
        temperature: Optional[float] = 0.0,
    ) -> AudioResponse:
        """Translate audio to English text"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            contents = await file.read()
            upload_file = UploadFile(
                filename=file.filename, file=contents, content_type=file.content_type
            )
            result = await rest_translate_audio(
                file=upload_file,
                model=model,
                prompt=prompt,
                response_format=response_format,
                temperature=temperature,
                user=user,
                authorization=auth,
            )
            return AudioResponse(**result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def create_speech(
        self, info, input: TextToSpeechInput
    ) -> TextToSpeechResponseType:
        """Convert text to speech"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            result = await rest_text_to_speech(
                tts=TextToSpeech(**input.__dict__), user=user, authorization=auth
            )
            return TextToSpeechResponseType(**result)
        except HTTPException as e:
            raise Exception(str(e.detail))

    @strawberry.mutation
    async def create_image(
        self, info, input: ImageGenerationInput
    ) -> ImageGenerationResponseType:
        """Generate an image from a prompt"""
        try:
            user, auth = await get_user_and_auth_from_context(info)
            result = await rest_generate_image(
                image=ImageCreation(**input.__dict__), user=user, authorization=auth
            )
            return ImageGenerationResponseType(**result)
        except HTTPException as e:
            raise Exception(str(e.detail))


# Create the schema (no queries needed, all operations are mutations)
schema = strawberry.Schema(mutation=Mutation)
