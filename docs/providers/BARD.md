# Agent-LLM

## AI Provider: Google Bard

- [Google Bard](https://bard.google.com)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

## Disclaimer

We are not responsible if Google bans your account for doing this. This may not be consistent with their rules to use their services in this way. This was developed for experimental purposes and we assume no responsibility for how you use it.

## Quick Start Guide

1. Clone the [Agent-LLM](https://github.com/Josh-XT/Agent-LLM) GitHub repository.



```
git clone https://github.com/Josh-XT/Agent-LLM
cd "Agent-LLM"
pip install -r "requirements.txt"
```

2. Open Google Chrome and navigate to https://bard.google.com/
3. Press F12 for console
4. Go to Application → Cookies → `__Secure-1PSID`. Copy the value of that cookie. That is your bard token.
5. Create your `.env` below. Update `BARD_TOKEN` with the value of `__Secure-1PSID` from step 4.



```
AI_PROVIDER=bard
BARD_TOKEN=YOUR_BARD_TOKEN
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

