# Chutes.ai

- [Chutes.ai](https://chutes.ai/)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide

- Get your Chutes API key at <https://chutes.ai/app>.

### Update your agent settings

1. Set `AI_PROVIDER` to `chutes`.
2. Set `CHUTES_API_KEY` to your API key.
3. Set `CHUTES_MODEL` to your preferred model. Default is `Qwen/Qwen3-235B-A22B-Instruct-2507`.
4. Set `CHUTES_VISION_MODEL` to your vision model. Default is `Qwen/Qwen3-VL-235B-A22B-Instruct`.
5. Set `CHUTES_CODING_MODEL` for code tasks. Default is `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8`.
6. Set `CHUTES_MAX_TOKENS` to the maximum number of tokens. Default is `128000`.
7. Set `CHUTES_TEMPERATURE` to a value between 0 and 1. Default is `0.7`.
8. Set `CHUTES_TOP_P` to a value between 0 and 1. Default is `0.9`.
9. Set `CHUTES_ENDPOINT_URL` to the API endpoint. Default is `https://llm.chutes.ai`.

## Available Models

Chutes.ai provides access to high-performance Qwen models:

- **Qwen3-235B-A22B-Instruct** - Large general-purpose model
- **Qwen3-VL-235B-A22B-Instruct** - Vision-language model
- **Qwen3-Coder-480B-A35B-Instruct-FP8** - Specialized coding model

## Services

Chutes provides the following services:

- `llm` - Language model for text generation
- `vision` - Vision capabilities for image understanding

## Features

- Access to large Qwen models
- High token limits (128K context)
- Fast inference
- Vision model support
- Specialized coding models
