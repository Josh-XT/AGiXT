# GPT4ALL
- [GPT4All](https://github.com/nomic-ai/gpt4all)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
**INTEL MAC NOT SUPPORTED BY GPT4ALL**

_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._
### Update your agent settings
1. Set `AI_PROVIDER` to `gpt4all` or `gpugpt4all` if wanting to run with GPU.
2. Set `MODEL_NAME` to the name of the model such as `gpt4all-lora-quantized`.
3. Set `AI_MODEL` to `default` or the name of the model from the `prompts` folder.
4. Set `AI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
5. Set `MAX_TOKENS` to the maximum number of tokens to generate. The higher the value, the longer the output.