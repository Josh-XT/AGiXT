# DeepInfra

- [DeepInfra](https://deepinfra.com/)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide

- Get your DeepInfra API key at <https://deepinfra.com/>.

### Update your agent settings

1. Set `AI_PROVIDER` to `deepinfra`.
2. Set `DEEPINFRA_API_KEY` to your API key.
3. Set `DEEPINFRA_MODEL` to your preferred model. Default is `Qwen/Qwen3-235B-A22B-Instruct-2507`.
4. Set `DEEPINFRA_VISION_MODEL` to your vision model. Default is `Qwen/Qwen3-VL-30B-A3B-Instruct`.
5. Set `DEEPINFRA_CODING_MODEL` for code tasks. Default is `Qwen/Qwen3-Coder-480B-A35B-Instruct`.
6. Set `DEEPINFRA_MAX_TOKENS` to the maximum number of tokens. Default is `128000`.
7. Set `DEEPINFRA_TEMPERATURE` to a value between 0 and 1. Default is `0.7`.
8. Set `DEEPINFRA_TOP_P` to a value between 0 and 1. Default is `0.9`.
9. Set `DEEPINFRA_ENDPOINT_URL` to the API endpoint. Default is `https://api.deepinfra.com/v1/openai`.

## Available Models

DeepInfra hosts a wide variety of open-source models including:

- **Qwen models** - Qwen3-235B, Qwen3-VL, Qwen3-Coder
- **Llama models** - Meta's Llama series
- **Mistral models** - Mistral and Mixtral
- **Other open-source models** - Various community models

Visit <https://deepinfra.com/models> for the full list of available models.

## Services

DeepInfra provides the following services:

- `llm` - Language model for text generation
- `vision` - Vision capabilities for image understanding

## Features

- Access to many open-source models
- Pay-per-token pricing
- Fast inference with optimized infrastructure
- OpenAI-compatible API
- Automatic model scaling
