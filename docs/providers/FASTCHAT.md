# Agent-LLM

## AI Provider: FastChat

- [FastChat](https://github.com/lm-sys/FastChat)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Quick Start Guide

1. Clone the [Agent-LLM](https://github.com/Josh-XT/Agent-LLM) GitHub repository.


```
git clone https://github.com/Josh-XT/Agent-LLM
cd "Agent-LLM"
pip install -r "requirements.txt"
```

2. Create your `.env` below. Modify if necessary.  It may be necessary to choose a different model than default if the default prompts are not working well with the model you choose.



```
AI_PROVIDER=fastchat
AI_MODEL=vicuna-13b-v1.1
AI_PROVIDER_URI=http://localhost:8000

```

4. Start the back end application for Agent-LLM.



```
python app.py
```

3. Navigate to the `frontend` folder to install dependencies and start the `NextJS` front end for Agent-LLM.



```
cd frontend
npm install
npm run dev
```

## Accessing Agent-LLM

Web Interface: http://localhost

Redoc: http://localhost:7437/redoc

Swagger: http://localhost:7437/docs

