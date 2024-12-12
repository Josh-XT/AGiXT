# Hugging Face

- [Hugging Face](https://huggingface.co/docs/transformers/index)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide

_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Update your agent settings

1. Set `AI_PROVIDER` to `huggingface`.
2. Set `HUGGINGFACE_API_KEY` to your Hugging Face API key.
3. Set `HUGGINGFACE_STABLE_DIFFUSION_MODEL` to the name of the model you want to use. Default is `runwayml/stable-diffusion-v1-5`.
4. Set `HUGGINGFACE_STABLE_DIFFUSION_API_URL` to the API URL of the model you want to use. Default is `https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5`.
5. Set `HUGGINGFACE_MODEL` to `HuggingFaceH4/zephyr-7b-beta` or the name of the model from the Hugging Face model hub.
6. Set `HUGGINGFACE_STOP_TOKEN` to the token that you want to use to stop the model from generating more text. Default is `
7. Set `HUGGINGFACE_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
8. Set `HUGGINGFACE_MAX_TOKENS` to the maximum number of input tokens.
9. Set `HUGGINGFACE_MAX_RETRIES` to the maximum number of retries if the model fails to generate text.
