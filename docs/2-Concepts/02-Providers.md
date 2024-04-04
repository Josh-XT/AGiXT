# Providers

Providers are the hosts of models or services that AGiXT uses to interact with users.

## Logical Language Model (LLM) Providers

The agent's LLM provider will be the logical language model. This is generally an intelligent model that can understand and generate human-like text. The LLM provider will be used for generating responses to user input and for understanding the user's intent.

### Current LLM Providers

- OpenAI and Azure OpenAI (GPT-4, etc)
- ezLocalai (Open source models)
- Anthropic (Claude)
- Google (Gemini)
- Hugging Face (Open source models)
- gpt4free (Free providers, results may vary.)

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
- Hugging Face (Stable Diffusion)

## Text to Speech (TTS) Providers

Text to speech providers are used to generate speech from the agent's response. This can be used to have the agent speak to the user through the chat interface.

### Current TTS Providers

- OpenAI
- ezLocalai (Voice cloning TTS)
- Google (gTTS, set as default)
- Elevenlabs (Voice cloning TTS over API, listed under `agixt` Provider)

## Speech Transcription Providers

Speech transcription providers are used to transcribe speech from the user to text. This can be used to have the agent understand the user's speech input.

### Current Speech Transcription Providers

- OpenAI (Whisper)
- ezLocalai (Open source models)
- default (faster-whisper)

## Speech Translation Providers

Speech translation providers are used to translate speech from any language that the provider understands to English in text. This can be used to have the agent understand the user's speech input in a different language.

### Current Speech Translation Providers

- OpenAI (Whisper)
- ezLocalai (Open source models)
- default (faster-whisper)
