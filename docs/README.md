# Agent-LLM (Large Language Model)

![RELEASE](https://img.shields.io/github/v/release/Josh-XT/Agent-LLM?label=Release%20Version&style=plastic) 
[![STATUS](https://img.shields.io/badge/status-beta-blue?label=Release%20Status&style=plastic)](https://github.com/josh-xt/Agent-LLM) 
[![LICENSE: MIT](https://img.shields.io/github/license/Josh-XT/Agent-LLM?label=License&style=plastic)](https://github.com/Josh-XT/Agent-LLM/blob/main/LICENSE) 
![Docker](https://img.shields.io/github/actions/workflow/status/Josh-XT/Agent-LLM/docker-image.yml?branch=main&label=Docker&style=plastic) [![codestyleBlack](https://img.shields.io/badge/code%20style-black-black?branch=main&label=Code%20Style&style=plastic)](https://black.readthedocs.io/en/stable/the_black_code_style/index.html)

[![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/vfXjyuKZ) 
[![Twitter](https://img.shields.io/badge/Twitter-Follow_@AgentLLM-blue?logo=twitter&style=plastic)](https://twitter.com/AgentLLM) 
[![FacebookGroup](https://img.shields.io/badge/Facebook-Join_Our_Group-blue?logo=facebook&style=plastic)](https://www.facebook.com/groups/agentllm)
[![EMail](https://img.shields.io/badge/E--Mail-Outreach_&_Media-5865f2?logo=gmail&style=plastic)](https://twitter.com/AgentLLM) 

Please use the outreach email for media, sponsorship, or to contact us for other miscellaneous purposes. 

**Do not** send us emails with troubleshooting requests, feature requests or bug reports, please direct those to [GitHub Issues](https://github.com/Josh-XT/Agent-LLM/issues) or [Discord](https://discord.gg/vfXjyuKZ).

Agent-LLM is an Artificial Intelligence Automation Platform designed to power efficient AI instruction management across multiple providers. Our agents are equipped with adaptive memory, and this versatile solution offers a powerful plugin system that supports a wide range of commands, including web browsing. With growing support for numerous AI providers and models, Agent-LLM is constantly evolving to empower diverse applications.

![image](https://user-images.githubusercontent.com/102809327/234344654-a1a4201b-594b-4a00-ac78-279a2e5bbe43.png)

## ⚠️ Run this in Docker or a Virtual Machine!
You're welcome to disregard this message, but if you do and the AI decides that the best course of action for its task is to build a command to format your entire computer, that is on you.  Understand that this is given full unrestricted terminal access by design and that we have no intentions of building any safeguards.  This project intends to stay light weight and versatile for the best possible research outcomes.

## ⚠️ Monitor Your Usage!
Please note that using some AI providers (such as OpenAI's GPT-4 API) can be expensive! Monitor your usage carefully to avoid incurring unexpected costs.  We're **NOT** responsible for your usage under any circumstance.

## ⚠️ Under Development!
This project is under active development and may still have issues. We appreciate your understanding and patience. If you encounter any problems, please first check the open issues. If your issue is not listed, kindly create a new issue detailing the error or problem you experienced. Thank you for your support!

## Table of Contents 📖

- [Agent-LLM (Large Language Model)](#agent-llm-large-language-model)
  - [⚠️ Run this in Docker or a Virtual Machine!](#️-run-this-in-docker-or-a-virtual-machine)
  - [⚠️ Monitor Your Usage!](#️-monitor-your-usage)
  - [⚠️ Under Development!](#️-under-development)
  - [Table of Contents 📖](#table-of-contents-)
  - [Media Coverage ⏯️](#media-coverage-️)
    - [Video](#video)
  - [Key Features 🗝️](#key-features-️)
  - [Web Application Features](#web-application-features)
  - [Quick Start](#quick-start)
    - [Running a Mac?](#running-a-mac)
    - [Not using OpenAI? No problem!](#not-using-openai-no-problem)
  - [Configuration](#configuration)
  - [API Endpoints](#api-endpoints)
  - [Extending Functionality](#extending-functionality)
    - [Commands](#commands)
    - [AI Providers](#ai-providers)
  - [Contributing](#contributing)
  - [Donations and Sponsorships](#donations-and-sponsorships)
  - [Our Team 🧑‍💻](#our-team-)
  - [Acknowledgments](#acknowledgments)
  - [History](#history)

## Media Coverage ⏯️

### Video
- From [World of AI](https://www.youtube.com/@intheworldofai) on YouTube: [Agent LLM: AI Automation Bot for Managing and Implementing AI Through Applications](https://www.youtube.com/watch?v=g0_36Mf2-To)


## Key Features 🗝️

- Adaptive long-term and short-term memory management

- Versatile plugin system with extensible commands for various AI models

- Wide compatibility with multiple AI providers, including:

  - OpenAI GPT-3.5, GPT-4

  - Oobabooga Text Generation Web UI

  - Kobold

  - llama.cpp

  - FastChat

  - Google Bard

  - And More!

- Web browsing and command execution capabilities

- Code evaluation support

- Seamless Docker deployment

- Integration with Hugging Face for audio-to-text conversion

- Interoperability with platforms like Twitter, GitHub, Google, DALL-E, and more

- Text-to-speech options featuring Brian TTS, Mac OS TTS, and ElevenLabs

- Continuously expanding support for new AI providers and services

## Web Application Features

The frontend web application of Agent-LLM provides an intuitive and interactive user interface for users to:

- Manage agents: View the list of available agents, add new agents, delete agents, and switch between agents.
- Set objectives: Input objectives for the selected agent to accomplish.
- Start tasks: Initiate the task manager to execute tasks based on the set objective.
- Instruct agents: Interact with agents by sending instructions and receiving responses in a chat-like interface.
- Available commands: View the list of available commands and click on a command to insert it into the objective or instruction input boxes.
- Dark mode: Toggle between light and dark themes for the frontend.
- Built using NextJS and Material-UI
- Communicates with the backend through API endpoints

## Quick Start

1. Obtain an OpenAI API key from [OpenAI](https://platform.openai.com) and add it to your `.env` file.
2. Set the `OPENAI_API_KEY` in your `.env` file using the provided [.env.example](https://github.com/Josh-XT/Agent-LLM/blob/main/.env.example) as a template.

```
wget https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/docker-compose.yml
wget https://raw.githubusercontent.com/Josh-XT/Agent-LLM/main/.env.example
mv .env.example .env
```

3. Run the following Docker command in the folder with your `.env` file:

```
docker compose up -d
```

4. Access the web interface at http://localhost

### Running a Mac?

You'll need to run `docker compose` to build if the command above does not work.

```
docker compose -f docker-compose-mac.yml up -d
```

### Not using OpenAI? No problem!
We are constantly trying to expand our AI provider support.  Take a look at our Jupyter Notebooks for Quick starts for these:

**Reminder:** [⚠️ Run this in Docker or a Virtual Machine!](#️-run-this-in-docker-or-a-virtual-machine)

1. [OpenAI](https://github.com/Josh-XT/Agent-LLM/blob/main/notebooks/openai.ipynb)
2. [llamacpp](https://github.com/Josh-XT/Agent-LLM/blob/main/notebooks/llamacpp.ipynb)
3. [Oobabooga Text Generation Web UI](https://github.com/Josh-XT/Agent-LLM/blob/main/notebooks/oobabooga.ipynb)
4. [ChatGPT](https://github.com/Josh-XT/Agent-LLM/blob/main/notebooks/chatgpt.ipynb)
5. [Google Bard](https://github.com/Josh-XT/Agent-LLM/blob/main/notebooks/bard.ipynb)

For more detailed setup and configuration instructions, refer to the sections below.

## Configuration

Agent-LLM utilizes a `.env` configuration file to store AI language model settings, API keys, and other options. Use the supplied `.env.example` as a template to create your personalized `.env` file. Configuration settings include:

- **INSTANCE CONFIG**: Set the agent name, objective, and initial task.
- **AI_PROVIDER**: Choose between OpenAI, llama.cpp, or Oobabooga for your AI provider.
- **AI_PROVIDER_URI**: Set the URI for custom AI providers such as Oobabooga Text Generation Web UI (default is http://127.0.0.1:7860).
- **MODEL_PATH**: Set the path to the AI model if using llama.cpp or other custom providers.
- **COMMANDS_ENABLED**: Enable or disable command extensions.
- **MEMORY SETTINGS**: Configure short-term and long-term memory settings.
- **AI_MODEL**: Specify the AI model to be used (e.g., gpt-3.5-turbo, gpt-4, text-davinci-003, Vicuna, etc.).
- **AI_TEMPERATURE**: Set the AI temperature (leave default if unsure).
- **MAX_TOKENS**: Set the maximum number of tokens for AI responses (default is 2000).
- **WORKING_DIRECTORY**: Set the agent's working directory.
- **EXTENSIONS_SETTINGS**: Configure settings for OpenAI, Hugging Face, Selenium, Twitter, and GitHub.
- **VOICE_OPTIONS**: Choose between Brian TTS, Mac OS TTS, or ElevenLabs for text-to-speech.

For a detailed explanation of each setting, refer to the `.env.example` file provided in the repository.

## API Endpoints

Agent-LLM provides several API endpoints for managing agents, managing tasks, and managing chains.

To learn more about the API endpoints and their usage, visit the API documentation at http://localhost:7437/docs (Swagger) or http://localhost:7437/redoc (Redoc).

## Extending Functionality

### Commands

To introduce new commands, generate a new Python file in the `commands` folder and define a class inheriting from the `Commands` class. Implement the desired functionality as methods within the class and incorporate them into the `commands` dictionary.

### AI Providers

To switch AI providers, adjust the `AI_PROVIDER` setting in the `.env` file. The application is compatible with OpenAI, Oobabooga Text Generation Web UI, and llama.cpp. To support additional providers, create a new Python file in the `provider` folder and implement the required functionality.

**Coming Soon: Any providers defined in the `.env` file will be usable on different agents in the application and will not need to be manually switched.**

## Contributing

We welcome contributions to Agent-LLM! If you're interested in contributing, please check out our [contributions guide](https://github.com/Josh-XT/Agent-LLM/tree/main/.github/CONTRIBUTING.md) the [open issues](https://github.com/Josh-XT/Agent-LLM/issues) and [pull requests](https://github.com/Josh-XT/Agent-LLM/pulls), submit a [pull request](https://github.com/Josh-XT/Agent-LLM/pulls/new), or [suggest new features](https://github.com/Josh-XT/Agent-LLM/issues/new). To stay updated on the project's progress, [![FollowOnTwitter](https://img.shields.io/twitter/follow/AgentLLM?style=social)](https://twitter.com/AgentLLM), [![FollowOnTwitterJosh_XT](https://img.shields.io/twitter/follow/Josh_XT?style=social)](https://twitter.com/Josh_XT) and [![FollowOnTwitterJamesonRGrieve](https://img.shields.io/twitter/follow/JamesonRGrieve?style=social)](https://twitter.com/JamesonRGrieve), [![Join our Discord](https://img.shields.io/discord/1097720481970397356?label=JoinOurDiscord&logo=discord&logoColor=white&color=5865f2)](https://discord.gg/Na8M7mTayp).

## Donations and Sponsorships
We appreciate any support for Agent-LLM's development, including donations, sponsorships, and any other kind of assistance. If you would like to support us, please contact us through our [![e-mail](https://img.shields.io/badge/OUTREACH-e--mail-red)](mailto:contact@agent-llm.com), [![Discord Server](https://img.shields.io/discord/1097720481970397356?label=DiscordServer&logo=discord&logoColor=white&color=5865f2)](https://discord.gg/Na8M7mTayp) or[![FollowOnTwitter](https://img.shields.io/twitter/follow/AgentLLM?style=social)](https://twitter.com/AgentLLM).

We're always looking for ways to improve Agent-LLM and make it more useful for our users. Your support will help us continue to develop and enhance the application. Thank you for considering to support us!

## Our Team 🧑‍💻
| Josh (@Josh-XT)                    | James (@JamesonRGrieve) | 
|-----------------------------------|-----------------------------------|
| [<img src="https://www.iconfinder.com/icons/4202098/download/png/512" height="50">](https://github.com/Josh-XT)[<img src="https://www.iconfinder.com/icons/5296514/download/png/512" height="50">](https://twitter.com/Josh_XT) [<img src="https://www.iconfinder.com/icons/5296501/download/png/512" height="50">](https://www.linkedin.com/in/joshxt/) | [<img src="https://www.iconfinder.com/icons/4202098/download/png/512" height="50">](https://github.com/JamesonRGrieve)[<img src="https://www.iconfinder.com/icons/5296514/download/png/512" height="50">](https://twitter.com/JamesonRGrieve) [<img src="https://www.iconfinder.com/icons/5296501/download/png/512" height="50">](https://www.linkedin.com/in/jamesonrgrieve/)                |

## Acknowledgments

This project was inspired by and utilizes code from the following repositories:

- [babyagi](https://github.com/yoheinakajima/babyagi)
- [Auto-GPT](https://github.com/Significant-Gravitas/Auto-GPT)

Please consider exploring and contributing to these projects as well.

## History
![Star History Chart](https://api.star-history.com/svg?repos=Josh-XT/Agent-LLM&type=Dat)