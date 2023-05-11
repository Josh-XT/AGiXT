# Agent-LLM

## AI Provider: llama.cpp

- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `model-prompts` specific to the model that you're using. You can also create one and add your own prompts._
### Update your agent settings
1. Make sure your model is placed in the folder `models/` 
1. Create a new agent
1. Set `AI_PROVIDER` to `llamacpp`.
1. Set `MODEL_PATH` to the path of your llama.cpp model (for docker containers `models/` is mapped to `/model`)
