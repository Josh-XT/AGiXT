# Azure OpenAI
- [Azure OpenAI](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/concepts/models)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs. We're NOT responsible for your usage under any circumstance.**

## Quick Start Guide
### Update your agent settings
1. Set `AI_PROVIDER` to `azure`.
2. Set `AZURE_API_KEY` to your Azure OpenAI API key.
3. Set `DEPLOYMENT_ID` to your Azure OpenAI deployment ID.
4. Set `AI_MODEL` to `gpt-3.5-turbo` for ChatGPT model or choose `gpt-4` or another model you have access to.
5. Set `AI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
6. Set `MAX_TOKENS` to the maximum number of tokens to generate. The higher the value, the longer the output.  The maximum for `gpt-3.5-turbo` is 4000, `gpt-4` is 8000.

