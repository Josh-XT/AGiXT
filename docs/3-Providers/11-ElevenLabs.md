# ElevenLabs

- [ElevenLabs](https://elevenlabs.io/)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

⚠️ **Note: ElevenLabs is a Text-to-Speech (TTS) provider only. It does not provide language model capabilities.**

## Quick Start Guide

- Get your ElevenLabs API key at <https://elevenlabs.io/>.

### Update your agent settings

1. Set `AI_PROVIDER` to `elevenlabs`.
2. Set `ELEVENLABS_API_KEY` to your API key.
3. Set `ELEVENLABS_VOICE` to your preferred voice ID. Default is `ErXwobaYiN019PkySvjV` (Antoni).

## Services

ElevenLabs provides:

- `tts` - Text-to-speech audio generation

## Available Voices

ElevenLabs offers many pre-made voices and supports custom voice cloning. Some popular voice IDs:

- `ErXwobaYiN019PkySvjV` - Antoni (default)
- `EXAVITQu4vr4xnSDxMaL` - Bella
- `MF3mGyEYCl7XYWbV9V6O` - Elli
- `TxGEqnHWrfWFTfGW9XjX` - Josh
- `VR6AewLTigWG4xSOukaG` - Arnold
- `pNInz6obpgDQGcFmaJgB` - Adam

Visit the [ElevenLabs Voice Library](https://elevenlabs.io/voice-library) for more voices.

## Features

- **High-Quality TTS**: Natural-sounding voice synthesis
- **Voice Cloning**: Create custom voices from audio samples
- **Multiple Languages**: Support for many languages
- **Emotion Control**: Adjust voice style and emotion
- **Low Latency**: Fast audio generation

## Usage Notes

ElevenLabs is typically used as a secondary provider for TTS alongside a primary LLM provider:

```
Primary Provider (LLM): openai, anthropic, etc.
TTS Provider: elevenlabs
```

The agent will use the primary provider for text generation and ElevenLabs for converting responses to speech.
