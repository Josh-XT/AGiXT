# Custom OpenAI Style Provider
- Listed as `custom` in the provider list.
- [AGiXT](https://github.com/Josh-XT/AGiXT)

This provider enables you to use OpenAI proxies as well as custom endpoints that utilize the same syntax as OpenAI's API.

## Quick Start Guide
### Update your agent settings
1. Set `AI_PROVIDER` to `custom`.
2. Set `API_URI` to the URI of your endpoint. For example, `https://api.openai.com/v1/engines/davinci/completions`.
3. Set `API_KEY` to the API key for your endpoint if applicable, leave empty if not.
4. Set `AI_MODEL` to `gpt-3.5-turbo-16k` if that is the model you would prefer to use.
5. Set `AI_TEMPERATURE` to a value between 0 and 1. The higher the value, the more creative the output.
6. Set `AP_TOP_P` to a value between 0 and 1, generally keeping this closer to 1 is better.
7. Set `MAX_TOKENS` to the maximum number of tokens to generate. The higher the value, the longer the output.  The maximum for `gpt-3.5-turbo` is 4000, `gpt-4` is 8000, `gpt-3.5-turbo-16k` is 16000.
