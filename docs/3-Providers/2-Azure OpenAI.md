# Azure OpenAI

- [Azure OpenAI](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/concepts/models)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs. We're NOT responsible for your usage under any circumstance.**

## Quick Start Guide

- Instructions for setting up an Azure OpenAI Deployment can be found [here](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource?pivots=web-portal).

### Update your agent settings

1. Set `AI_PROVIDER` to `azure`.
2. Set `AZURE_API_KEY` to your Azure OpenAI API key.
3. Set `AZURE_OPENAI_ENDPOINT` to your Azure OpenAI endpoint.
4. Set `AZURE_DEPLOYMENT_NAME` to your Azure OpenAI deployment ID for your primary model.
5. Set `AZURE_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
6. Set `AZURE_MAX_TOKENS` to the maximum number of input tokens. `gpt-4o` allows up to `120000` input tokens.
