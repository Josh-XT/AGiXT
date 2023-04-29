# Agent-LLM

## AI Provider: Kobold

- [Kobold](https://github.com/KoboldAI/KoboldAI-Client)
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
AI_PROVIDER=kobold
AI_MODEL=default
AI_PROVIDER_URI=http://localhost:5050/api/v1
AI_TEMPERATURE=0.2
MAX_TOKENS=2096

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

