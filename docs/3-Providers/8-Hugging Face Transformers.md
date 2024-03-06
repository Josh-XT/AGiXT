# Hugging Face Transformers
- [Hugging Face Transformers](https://huggingface.co/docs/transformers/index)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._
### Update your agent settings
1. Set `AI_PROVIDER` to `transformer`.
2. Set `MODEL_PATH` to the path of your llama.cpp model (for docker containers `models/` is mapped to `/model`)
3. Set `AI_MODEL` to `default` or the name of the model from the `prompts` folder.
4. Set `AI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
5. Set `MAX_TOKENS` to the maximum number of tokens to generate. The higher the value, the longer the output.