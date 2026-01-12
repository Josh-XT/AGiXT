# DeepSeek

- [DeepSeek](https://platform.deepseek.com/)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide

- Get your DeepSeek API key at <https://platform.deepseek.com/>.

### Update your agent settings

1. Set `AI_PROVIDER` to `deepseek`.
2. Set `DEEPSEEK_API_KEY` to your API key.
3. Set `DEEPSEEK_MODEL` to `deepseek-chat` or your preferred DeepSeek model.
4. Set `DEEPSEEK_MAX_TOKENS` to the maximum number of tokens. Default is `64000`.
5. Set `DEEPSEEK_TEMPERATURE` to a value between 0 and 1. Default is `0.1`.
6. Set `DEEPSEEK_TOP_P` to a value between 0 and 1. Default is `0.95`.
7. Set `DEEPSEEK_API_URI` to the API endpoint. Default is `https://api.deepseek.com/`.

## Available Models

- `deepseek-chat` - General purpose chat model
- `deepseek-coder` - Optimized for code generation
- `deepseek-reasoner` - Enhanced reasoning capabilities

## Services

DeepSeek provides the following services:

- `llm` - Language model for text generation
- `vision` - Vision capabilities for image understanding

## Features

- High-quality language model inference
- Vision model support for image analysis
- Competitive pricing
- Fast inference speeds
