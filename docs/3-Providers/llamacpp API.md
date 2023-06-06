# llamacpp API
- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Install the llama.cpp API server
Change `./models/7B/ggml-model.bin` to the path of your model.
```
pip install llama-cpp-python[server]
export MODEL=./models/7B/ggml-model.bin
python3 -m llama_cpp.server
Navigate to http://localhost:8000/docs to see the OpenAPI documentation.
```

### Update your agent settings
1. Make sure your model is placed in the folder `models/`
2. Create a new agent
3. Set `AI_PROVIDER` to `llamacpp`.
4. Set `AI_PROVIDER_URI` to the URI of your llama.cpp server. For example, if you're running the server locally, set this to `http://localhost:8000`.
5. Set the following parameters as needed:
    1. `MAX_TOKENS`: This should be the maximum number of tokens that the model can generate. Default value is 2000.
    2. `AI_TEMPERATURE`: Controls the randomness of the model's outputs. A higher value produces more random outputs and a lower value produces more deterministic outputs. Default value is 0.7.
    3. `AI_MODEL`: Set this to the type of AI model to use. Default value is 'default'.
    4. `STOP_SEQUENCE`: This should be the sequence at which the model will stop generating more tokens. Default value is '</s>'.
