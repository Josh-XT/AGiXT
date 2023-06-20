# Oobabooga Text Generation Web UI
- [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Start provider locally
1. Setup `text-generation-webui` from above
1. Make sure `--api` and `--listen` (when running `AGiXT` in docker) are present
1. `AI_PROVIDER_URI` is now `http://localhost:5000` or `http://172.x.x.x` (docker)

### Create Agent 
1. Create a new agent
2. Set `AI_PROVIDER` to `oobabooga`.
3. Set `AI_PROVIDER_URI` to the URI of your Oobabooga server.
4. Set `PROMPT_PREFIX` and `PROMPT_SUFFIX` if your model requires it.  For example, for models like Vicuna, you will want to enter the `PROMPT_PREFIX` to `User: ` and `PROMPT_SUFFIX` to `\nAssistant: `.
5. Review and set any of the other settings as you see fit from the agent settings page.
