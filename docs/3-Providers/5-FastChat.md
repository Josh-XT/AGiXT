# FastChat
- [FastChat](https://github.com/lm-sys/FastChat)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Update your agent settings

1. Set `AI_MODEL` to `vicuna` for Vicuna.
2. Set `AI_PROVIDER_URI` to `http://localhost:8000`, or the URI of your FastChat server.
3. Set `MODEL_PATH` to the path of your model (for docker containers `models/` is mapped to `/model`)