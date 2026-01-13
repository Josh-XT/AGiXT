# OpenRouter

- [OpenRouter](https://openrouter.ai/)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide

- Get your OpenRouter API key at <https://openrouter.ai/keys>.

### Update your agent settings

1. Set `AI_PROVIDER` to `openrouter`.
2. Set `OPENROUTER_API_KEY` to your API key.
3. Set `OPENROUTER_AI_MODEL` to your preferred model. Default is `openai/gpt-4o`.
4. Set `OPENROUTER_CODING_MODEL` for code tasks. Default is `anthropic/claude-sonnet-4`.
5. Set `OPENROUTER_MAX_TOKENS` to the maximum number of tokens. Default is `16384`.
6. Set `OPENROUTER_TEMPERATURE` to a value between 0 and 1. Default is `0.7`.
7. Set `OPENROUTER_TOP_P` to a value between 0 and 1. Default is `0.95`.
8. Set `OPENROUTER_API_URI` to the API endpoint. Default is `https://openrouter.ai/api/v1/`.

## Available Models

OpenRouter provides unified access to models from multiple providers:

### OpenAI Models
- `openai/gpt-4o`
- `openai/gpt-4-turbo`
- `openai/o1-preview`

### Anthropic Models
- `anthropic/claude-sonnet-4`
- `anthropic/claude-3-opus`
- `anthropic/claude-3-haiku`

### Google Models
- `google/gemini-2.0-flash`
- `google/gemini-pro`

### Meta Models
- `meta-llama/llama-3.1-405b`
- `meta-llama/llama-3.1-70b`

### Open Source Models
- `mistralai/mistral-large`
- `qwen/qwen-2.5-72b`

Visit <https://openrouter.ai/models> for the full list of available models.

## Services

OpenRouter provides the following services:

- `llm` - Language model for text generation
- `vision` - Vision capabilities (model dependent)

## Features

- **Unified API**: Access multiple AI providers through one API
- **Model Routing**: Automatic fallback to alternative models
- **Usage Tracking**: Detailed usage analytics
- **Cost Optimization**: Compare pricing across providers
- **OpenAI-compatible**: Drop-in replacement for OpenAI API

## Model Naming Convention

Models are named using the format `provider/model-name`. For example:
- `openai/gpt-4o` - OpenAI's GPT-4o
- `anthropic/claude-sonnet-4` - Anthropic's Claude Sonnet 4
- `google/gemini-2.0-flash` - Google's Gemini 2.0 Flash
