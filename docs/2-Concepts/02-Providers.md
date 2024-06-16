# Providers

Providers are the hosts of models or services that AGiXT uses to interact with users.

## Logical Language Model (LLM) Providers

We're fully aware that they're called `large language models` and not `logical language models`, but our approach to prompting and chaining uses your agents primary LLM for logical reasoning in the background. This is why we refer to them as `logical language models` in the context of AGiXT.

The agent's LLM provider will be the logical language model. This is generally an intelligent model that can understand and generate human-like text. The LLM provider will be used for generating responses to user input and for understanding the user's intent.

### Current LLM Providers

- OpenAI and Azure OpenAI (GPT-4, etc)
- ezLocalai (Open source models)
- Anthropic (Claude)
- Google (Gemini)
- Hugging Face (Open source models)
- default: gpt4free (Free providers, results may vary.)

## Vision Providers

Vision providers are used to get descriptions of images that are uploaded in messages, then giving that description to the LLM provider to generate a response as well as execute any commands or chains that are defined in the agent's settings.

### Current Vision Providers

- OpenAI (gpt-4-vision, etc)
- ezLocalai (Open source models such as `deepseek-vl-1.3b-chat`)
- Anthropic (Claude)
- Google (Gemini)

## Image Generation Providers

Image generation providers are used to generate images based on the users input. If the `create_image` flag is set to `true` in the message on the `/v1/chat/completions` endpoint, an image will be generated and sent with the agent's response.

### Current Image Generation Providers

- OpenAI (DALL-E)
- default: Hugging Face (Stable Diffusion)

## Text to Speech (TTS) Providers

Text to speech providers are used to generate speech from the agent's response. This can be used to have the agent speak to the user through the chat interface.

### Current TTS Providers

- OpenAI
- ezLocalai (Voice cloning TTS)
- Elevenlabs (Voice cloning TTS over API, listed under `agixt` Provider)
- default: Google (gTTS)

## Speech Transcription Providers

Speech transcription providers are used to transcribe speech from the user to text. This can be used to have the agent understand the user's speech input.

### Current Speech Transcription Providers

- OpenAI (Whisper)
- ezLocalai (Open source models)
- default: faster-whisper

## Speech Translation Providers

Speech translation providers are used to translate speech from any language that the provider understands to English in text. This can be used to have the agent understand the user's speech input in a different language.

### Current Speech Translation Providers

- OpenAI (Whisper)
- ezLocalai (Open source models)
- default: faster-whisper

# Services for Providers

There are multiple provider services for different providers for features like TTS, Audio to Text, Embeddings, and Image Generation.
Each provider now has a `services` property which is a list of services available from that provider. Providers with an embeddings service will have an additional property for `chunk_size` for the embedder.

For example, the OpenAI provider has:

```python
self.chunk_size = 1024

@staticmethod
def services():
    return [
      "llm", # Language model
      "tts", # Text to speech
      "image", # Image generation
      "embeddings", # Embeddings creation
      "transcription", # Audio transcription to text
      "translation", # Audio translation to text in English
  ]
```

