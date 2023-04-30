# Agent-LLM

## AI Provider: OpenAI

- [OpenAI](https://openai.com)
- [Agent-LLM](https://github.com/Josh-XT/Agent-LLM)

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs. We're NOT responsible for your usage under any circumstance.**

## Quick Start Guide

1. If you don't already have an OpenAI API key, go to https://platform.openai.com/signup to get one. If you already have one, proceed to the next step.
2. Download the `docker-compose` file from the [Agent-LLM](https://github.com/Josh-XT/Agent-LLM) GitHub Repository.
3. Download the `.env.example` file so that you'll have a view of the settings available if desired.



```
wget https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docker-compose.yml
wget https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/.env.example
```

4. Create your `.env` below. Replace your `YOUR_API_KEY` with your OpenAI API Key or this will not work.



```
# Define variables.
AI_PROVIDER=openai
OPENAI_API_KEY=YOUR_API_KEY
AI_MODEL=gpt-3.5-turbo
AI_TEMPERATURE=0.2
MAX_TOKENS=4000
```


```
docker-compose up -d
```

## Accessing Agent-LLM

Web Interface: http://localhost

Redoc: http://localhost:7437/redoc

Swagger: http://localhost:7437/docs

