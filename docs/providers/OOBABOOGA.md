# Agent-LLM

## AI Provider: Oobabooga Text Generation Web UI

- [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `model-prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Update your agent settings
1. Set `AI_PROVIDER` to `oobabooga`.
2. Set `AI_MODEL` to `default` or the name of the model from the `model-prompts` folder.
3. Set `AI_PROVIDER_URI` to `http://localhost:5000`, or the URI of your Oobabooga server.
4. Set `AI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
5. Set `MAX_TOKENS` to the maximum number of tokens to generate. The higher the value, the longer the output.