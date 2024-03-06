# Oobabooga Text Generation Web UI
- [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Getting Started
If you're running with the option `Run AGiXT and Text Generation Web UI with Docker (NVIDIA Only)`, you can access the Text Generation Web UI at http://localhost:7860/?__theme=dark to download and and configure your models. The `AI_PROVIDER_URI` will be `http://text-generation-webui:5000` for your AGiXT agents.

### Create Agent 
1. Create a new agent
2. Set `AI_PROVIDER` to `oobabooga`.
3. Set `AI_PROVIDER_URI` to the URI of your Oobabooga server.
4. Set `PROMPT_PREFIX` and `PROMPT_SUFFIX` if your model requires it.  For example, for models like Vicuna, you will want to enter the `PROMPT_PREFIX` to `User: ` and `PROMPT_SUFFIX` to `\nAssistant: `.
5. Review and set any of the other settings as you see fit from the agent settings page.
