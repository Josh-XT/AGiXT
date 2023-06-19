# Azure OpenAI
- [Azure OpenAI](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/concepts/models)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs. We're NOT responsible for your usage under any circumstance.**

## Quick Start Guide
### Update your agent settings
1. Set `AI_PROVIDER` to `azure`.
2. Set `AZURE_API_KEY` to your Azure OpenAI API key.
3. Set `DEPLOYMENT_ID` to your Azure OpenAI deployment ID for your primary model.
4. Set `EMBEDDER_DEPLOYMENT_ID` to your Azure OpenAI deployment ID for your embedder model.
5. Set `AZURE_OPENAI_ENDPOINT` to your Azure OpenAI endpoint.
6. Choose your `AI_MODEL`.  Enter `gpt-3.5-turbo`, `gpt-4`, `gpt-4-32k`, or any other model you may have access to.
7. Set `AI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
8. Set `MAX_TOKENS` to the maximum number of tokens to generate. The higher the value, the longer the output.  The maximum for `gpt-3.5-turbo` is 4096, `gpt-4` is 8192, `gpt-4-32k` is 32768, `gpt-3.5-turbo-16k` is 16000.

