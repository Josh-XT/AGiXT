# Oobabooga Text Generation Web UI Server

1. Follow setup instructions from [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui)
3. Set the `AI_MODEL` in your `.env` file to `vicuna` if using `vicuna` as your LLM. Set it to whichever LLM you're using if prompts are available.
   - You can view which models have prompts available in the `provider/oobabooga` folder.
4. Run Oobabooga Text Generation Web UI server with the following command in order to work with this.
    ``python3 server.py --model YOUR-MODEL --listen --no-stream``