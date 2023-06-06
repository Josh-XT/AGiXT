# llamacpp
- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [AGiXT](https://github.com/Josh-XT/AGiXT)

## Quick Start Guide
_Note: AI_MODEL should stay `default` unless there is a folder in `prompts` specific to the model that you're using. You can also create one and add your own prompts._

### Update your agent settings
1. Make sure your model is placed in the folder `models/`
2. Create a new agent
3. Set `AI_PROVIDER` to `llamacpp`.
4. Set the following parameters as needed:
    1. `MODEL_PATH`: Set this to the path of your llama.cpp model (for docker containers `models/` is mapped to `/model`)
    2. `MAX_TOKENS`: This should be the maximum number of tokens that the model can generate. Default value is 2000.
    3. `AI_TEMPERATURE`: Controls the randomness of the model's outputs. A higher value produces more random outputs and a lower value produces more deterministic outputs. Default value is 0.7.
    4. `AI_MODEL`: Set this to the type of AI model to use. Default value is 'default'.
    5. `GPU_LAYERS`: Indicate the number of GPU layers to use for processing. Default value is 0.
    6. `BATCH_SIZE`: Specify the batch size to use for processing. Default value is 512.
    7. `THREADS`: This indicates the number of threads to use for processing. If set to 0, the number of threads is automatically determined. Default value is 0.
    8. `STOP_SEQUENCE`: This should be the sequence at which the model will stop generating more tokens. Default value is '</s>'.
