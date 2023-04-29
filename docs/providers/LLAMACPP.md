# Agent-LLM

## AI Provider: llama.cpp

- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Quick Start Guide

1. Find a compatible model with llama.cpp on Huggingface then download it to a models folder.
2. Clone the [Agent-LLM](https://github.com/Josh-XT/Agent-LLM) GitHub repository.



```
git clone https://github.com/Josh-XT/Agent-LLM
cd "Agent-LLM"
pip install -r "requirements.txt"
```

3. Create your `.env` below. Replace your `MODEL_PATH` with the path to your model.

_Note: AI_MODEL should stay `default` unless there is a folder in `model-prompts` specific to the model that you're using. You can also create one and add your own prompts._



```
AI_PROVIDER=llamacpp
MODEL_PATH=PATH/TO/YOUR/LLAMACPP/MODEL
AI_MODEL=default
AI_TEMPERATURE=0.2
MAX_TOKENS=2000
```

4. Start the back end application for Agent-LLM.



```
python app.py
```

5. Navigate to the `frontend` folder to install dependencies and start the `NextJS` front end for Agent-LLM.



```
cd frontend
npm install
npm run dev
```

## Accessing Agent-LLM

Web Interface: http://localhost

Redoc: http://localhost:7437/redoc

Swagger: http://localhost:7437/docs

