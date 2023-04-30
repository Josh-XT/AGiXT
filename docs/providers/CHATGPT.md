# Agent-LLM

## AI Provider: ChatGPT

- [ChatGPT](https://chat.openai.com/)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Disclaimer

We are not responsible if OpenAI bans your ChatGPT account for doing this. This may not be consistent with their rules to use their services in this way. This was developed for experimental purposes and we assume no responsibility for how you use it.

## Quick Start Guide

1. Clone the [Agent-LLM](https://github.com/Josh-XT/Agent-LLM) GitHub repository.



```
git clone https://github.com/Josh-XT/Agent-LLM
cd "Agent-LLM"
pip install -r "requirements.txt"
```

2. Create your `.env` below. Replace your `CHATGPT_USERNAME` and `CHATGPT_PASSWORD` with your login credentials for ChatGPT.



```
AI_PROVIDER=chatgpt
CHATGPT_USERNAME=your@email.com
CHATGPT_PASSWORD=yourpassword
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

