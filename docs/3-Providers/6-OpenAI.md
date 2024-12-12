# OpenAI

- [OpenAI](https://openai.com)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs. We're NOT responsible for your usage under any circumstance.**

## Quick Start Guide

- Instructions for setting up an OpenAI API key can be found [here](https://platform.openai.com/docs/quickstart).

### Update your agent settings

1. Set `AI_PROVIDER` to `openai`.
2. Set `OPENAI_API_KEY` to your OpenAI API key.
3. Set `OPENAI_MODEL` to `gpt-4o` or your preferred OpenAI model.
4. Set `OPENAI_MAX_TOKENS` to the maximum number of input tokens. `gpt-4o` allows up to `120000` input tokens.
5. Set `OPENAI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
6. Set `OPENAI_TOP_P` to a value between 0 and 1. The higher the value, the more diverse the output.
7. Set `OPENAI_WAIT_BETWEEN_REQUESTS` to the number of seconds to wait between requests. Default is `1`.
8. Set `OPENAI_WAIT_AFTER_FAILURE` to the number of seconds to wait after a failed request. Default is `3`.
9. Set `OPENAI_VOICE` to the voice name you want if using OpenAI as the TTS provider. Default is `alloy`.
10. Set `OPENAI_TRANSCRIPTION_MODEL` to the transcription model you want if using OpenAI as the transcription provider. Default is `whisper-1`
