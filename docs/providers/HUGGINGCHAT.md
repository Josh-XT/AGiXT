# Agent-LLM

## AI Provider: Hugging Face Huggingchat

- [Hugging Face Huggingchat](https://huggingface.co/chat/)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Quick Start Guide

1. Clone the [Agent-LLM](https://github.com/Josh-XT/Agent-LLM) GitHub repository.



```
git clone https://github.com/Josh-XT/Agent-LLM
cd "Agent-LLM"
pip install -r "requirements.txt"
```

2. Create your `.env` below.



```
AI_PROVIDER=huggingchat
AI_MODEL=openassistant
AI_TEMPERATURE=0.2
MAX_TOKENS=2048
```

3. Start the back end application for Agent-LLM.



```
python app.py
```

4. Navigate to the `frontend` folder to install dependencies and start the `NextJS` front end for Agent-LLM.



```
cd frontend
npm install
npm run dev
```

## Accessing Agent-LLM

Web Interface: http://localhost

Redoc: http://localhost:7437/redoc

Swagger: http://localhost:7437/docs

