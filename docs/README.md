# AGiXT
![RELEASE](https://img.shields.io/github/v/release/Josh-XT/AGiXT?label=Release%20Version&style=plastic) 
[![STATUS](https://img.shields.io/badge/status-beta-blue?label=Release%20Status&style=plastic)](https://github.com/josh-xt/AGiXT) 
[![LICENSE: MIT](https://img.shields.io/github/license/Josh-XT/AGiXT?label=License&style=plastic)](https://github.com/Josh-XT/AGiXT/blob/main/LICENSE) 
![DOCKER](https://img.shields.io/github/actions/workflow/status/Josh-XT/AGiXT/publish-docker.yml?branch=main&label=Docker&style=plastic) [![CODESTYLE](https://img.shields.io/badge/code%20style-Black-black?branch=main&label=Code%20Style&style=plastic)](https://black.readthedocs.io/en/stable/the_black_code_style/index.html)

[![GitHub](https://img.shields.io/badge/GitHub-Frontend_Repository-grey?logo=github&style=plastic)](https://github.com/JamesonRGrieve/Agent-LLM-Frontend)

[![Contribute](https://img.shields.io/github/issues/Josh-XT/AGiXT/help%20wanted?color=purple&label=Quick%20Contribute%20Backend&logo=github&style=plastic)](https://github.com/Josh-XT/AGiXT/labels/help%20wanted) 
[![Contribute](https://img.shields.io/github/issues/JamesonRGrieve/Agent-LLM-Frontend/help%20wanted?color=purple&label=Quick%20Contribute%20Frontend&logo=github&style=plastic)](https://github.com/JamesonRGrieve/Agent-LLM-Frontend/labels/help%20wanted) 
[![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD) 
[![Twitter](https://img.shields.io/badge/Twitter-Follow_@AGi_XT-blue?logo=twitter&style=plastic)](https://twitter.com/AGi_XT) 
[![EMail](https://img.shields.io/badge/E--Mail-Outreach_&_Media-5865f2?logo=gmail&style=plastic)](https://twitter.com/AGi_XT) 

![Logo](images/AGiXT.svg)

AGiXT is a dynamic Artificial Intelligence Automation Platform engineered to orchestrate efficient AI instruction management and task execution across a multitude of providers. Our solution infuses adaptive memory handling with a broad spectrum of commands to enhance AI's understanding and responsiveness, leading to improved task completion. The platform's smart features, like Smart Instruct and Smart Chat, seamlessly integrate web search, planning strategies, and conversation continuity, transforming the interaction between users and AI. By leveraging a powerful plugin system that includes web browsing and command execution, AGiXT stands as a versatile bridge between AI models and users. With an expanding roster of AI providers, code evaluation capabilities, comprehensive chain management, and platform interoperability, AGiXT is consistently evolving to drive a multitude of applications, affirming its place at the forefront of AI technology.

Embracing the spirit of extremity in every facet of life, we introduce AGiXT. This advanced AI Automation Platform is our bold step towards the realization of Artificial General Intelligence (AGI). Seamlessly orchestrating instruction management and executing complex tasks across diverse AI providers, AGiXT combines adaptive memory, smart features, and a versatile plugin system to maximize AI potential. With our unwavering commitment to innovation, we're dedicated to pushing the boundaries of AI and bringing AGI closer to reality.

## Table of Contents 📖

- [AGiXT](#agixt)
  - [Table of Contents 📖](#table-of-contents-)
  - [⚠️ Disclaimers!](#️-disclaimers)
    - [Monitor Your Usage!](#monitor-your-usage)
    - [Under Development!](#under-development)
  - [Key Features 🗝️](#key-features-️)
  - [Quickstart with Docker](#quickstart-with-docker)
    - [Windows Docker Desktop (streamlit only example)](#windows-docker-desktop-streamlit-only-example)
    - [Alternative Docker Compose Profiles](#alternative-docker-compose-profiles)
    - [Development using docker](#development-using-docker)
  - [Local Development](#local-development)
    - [API Endpoints](#api-endpoints)
  - [Configuration](#configuration)
  - [Documentation](#documentation)
  - [Contributing](#contributing)
  - [Donations and Sponsorships](#donations-and-sponsorships)
  - [Our Team 🧑‍💻](#our-team-)
  - [Acknowledgments](#acknowledgments)
  - [History](#history)

## ⚠️ Disclaimers!
### Monitor Your Usage!
Please note that using some AI providers (such as OpenAI's GPT-4 API) can be expensive! Monitor your usage carefully to avoid incurring unexpected costs.  We're **NOT** responsible for your usage under any circumstance.

### Under Development!
This project is under active development and may still have issues. We appreciate your understanding and patience. If you encounter any problems, please first check the open issues. If your issue is not listed, kindly create a new issue detailing the error or problem you experienced. Thank you for your support!

## Key Features 🗝️

- **Context and Token Management**: Adaptive handling of long-term and short-term memory for an optimized AI performance, allowing the software to process information more efficiently and accurately.
- **Smart Instruct**: An advanced feature enabling AI to comprehend, plan, and execute tasks effectively. The system leverages web search, planning strategies, and executes instructions while ensuring output accuracy.
- **Interactive Chat & Smart Chat**: User-friendly chat interface for dynamic conversational tasks. The Smart Chat feature integrates AI with web research to deliver accurate and contextually relevant responses.
- **Task Execution & Smart Task Management**: Efficient management and execution of complex tasks broken down into sub-tasks. The Smart Task feature employs AI-driven agents to dynamically handle tasks, optimizing efficiency and avoiding redundancy.
- **Chain Management**: Sophisticated handling of chains or a series of linked commands, enabling the automation of complex workflows and processes.
- **Web Browsing & Command Execution**: Advanced capabilities to browse the web and execute commands for a more interactive AI experience, opening a wide range of possibilities for AI assistance.
- **Multi-Provider Compatibility**: Seamless integration with leading AI providers such as OpenAI GPT series, Hugging Face Huggingchat, GPT4All, GPT4Free, Oobabooga Text Generation Web UI, Kobold, llama.cpp, FastChat, Google Bard, Bing, and more. 
- **Versatile Plugin System & Code Evaluation**: Extensible command support for various AI models along with robust support for code evaluation, providing assistance in programming tasks.
- **Docker Deployment**: Simplified setup and maintenance through Docker deployment.
- **Audio-to-Text & Text-to-Speech Options**: Integration with Hugging Face for seamless audio-to-text transcription, and multiple TTS choices, featuring Brian TTS, Mac OS TTS, and ElevenLabs.
- **Platform Interoperability & AI Agent Management**: Streamlined creation, renaming, deletion, and updating of AI agent settings along with easy interaction with popular platforms like Twitter, GitHub, Google, DALL-E, and more.
- **Custom Prompts & Command Control**: Granular control over agent abilities through enabling or disabling specific commands, and easy creation, editing, and deletion of custom prompts to standardize user inputs.
- **RESTful API**: FastAPI-powered RESTful API for seamless integration with external applications and services.
- **Expanding AI Support**: Continually updated to include new AI providers and services, ensuring the software stays at the forefront of AI technology.

## Quickstart with Docker
Clone the repository and run the AGiXT Streamlit Web App.
```
git clone https://github.com/Josh-XT/AGiXT
docker compose --profile streamlit up
```

- Web Interface http://localhost:8501
### Windows Docker Desktop (streamlit only example)
- Container Name: AGiXT
- Host Port: 8501:8501/tcp

### Alternative Docker Compose Profiles

Run all available services, this includes the FastAPI back end (Port 7437) and NextJS front end (Port 3000).
```
docker compose --profile all up
```

### Development using docker
```
git clone https://github.com/Josh-XT/AGiXT
docker compose --profile all -f docker-compose.yml -f docker-compose.dev.yaml up
```

## Local Development

Clone the repository for the AGiXT back end and start it.

#### Install poetry
`pip install poetry==1.5.0`
Check if poetry is available via
`poetry --version`
or
`python3 -m poetry --version`
Adapt the following commands accordingly.

#### Setup AGiXT
```
git clone https://github.com/Josh-XT/AGiXT && cd AGiXT
pip install poetry==1.5.0
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
poetry install --with gpt4free
playwright install
cd agixt
```

#### Run Streamlit 
`poetry run streamlit run Main.py`

#### Run REST
`poetry run uvicorn app:app --port 7437`


Access the web interface at http://localhost:8501

### API Endpoints

AGiXT provides several API endpoints for managing agents, prompts and chains.

If you're not running with Docker, the back end can be run with:
```
python agixt/app.py
```

To learn more about the API endpoints and their usage, visit the API documentation at 
- [Swagger](http://localhost:7437)
- [Redoc](http://localhost:7437/redoc)

This documentation is hosted locally and the frontend must be running for these links to work.
## Configuration

Each AGiXT Agent has its own settings for interfacing with AI providers, and other configuration options. These settings can be set and modified through the web interface.
## Documentation

Not enough information? Check out the [documentation](https://josh-xt.github.io/AGiXT) for more details.

## Contributing

[![Contribute](https://img.shields.io/github/issues/Josh-XT/AGiXT/help%20wanted?color=purple&label=Quick%20Contribute&logo=github&style=plastic)](https://github.com/Josh-XT/AGiXT/labels/help%20wanted) 

We welcome contributions to AGiXT! If you're interested in contributing, please check out our [contributions guide](https://github.com/Josh-XT/AGiXT/tree/main/.github/CONTRIBUTING.md) the [open issues on the backend](https://github.com/Josh-XT/AGiXT/issues), [open issues on the frontend](https://github.com/JamesonRGrieve/Agent-LLM-Frontend/issues) and [pull requests](https://github.com/Josh-XT/AGiXT/pulls), submit a [pull request](https://github.com/Josh-XT/AGiXT/pulls/new), or [suggest new features](https://github.com/Josh-XT/AGiXT/issues/new). To stay updated on the project's progress, [![Twitter](https://img.shields.io/badge/Twitter-Follow_@AGi_XT-blue?logo=twitter&style=plastic)](https://twitter.com/AGi_XT), [![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh_XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT) and [![Twitter](https://img.shields.io/badge/Twitter-Follow_@JamesonRGrieve-blue?logo=twitter&style=plastic)](https://twitter.com/JamesonRGrieve). Also feel free to join our [![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD).

## Donations and Sponsorships
We appreciate any support for AGiXT's development, including donations, sponsorships, and any other kind of assistance. If you would like to support us, please contact us through our [![EMail](https://img.shields.io/badge/E--Mail-Outreach_&_Media-5865f2?logo=gmail&style=plastic)](https://twitter.com/AGi_XT) , [![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD) or [![Twitter](https://img.shields.io/badge/Twitter-Follow_@AGi_XT-blue?logo=twitter&style=plastic)](https://twitter.com/AGi_XT).

We're always looking for ways to improve AGiXT and make it more useful for our users. Your support will help us continue to develop and enhance the application. Thank you for considering to support us!

## Our Team 🧑‍💻
| Josh (@Josh-XT)                    | James (@JamesonRGrieve) | 
|-----------------------------------|-----------------------------------|
|[![GitHub](https://img.shields.io/badge/GitHub-Follow_@Josh--XT-white?logo=github&style=plastic)](https://github.com/Josh-XT)|[![GitHub](https://img.shields.io/badge/GitHub-Follow_@JamesonRGrieve-white?logo=github&style=plastic)](https://github.com/JamesonRGrieve)|
|[![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh__XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT)|[![Twitter](https://img.shields.io/badge/Twitter-Follow_@JamesonRGrieve-blue?logo=twitter&style=plastic)](https://twitter.com/JamesonRGrieve)|
|[![LinkedIn](https://img.shields.io/badge/LinkedIn-Follow_@JoshXT-blue?logo=linkedin&style=plastic)](https://www.linkedin.com/in/joshxt/)|[![LinkedIn](https://img.shields.io/badge/LinkedIn-Follow_@JamesonRGrieve-blue?logo=linkedin&style=plastic)](https://www.linkedin.com/in/jamesonrgrieve/)|

## Acknowledgments

This project was inspired by and is built using code from the following open-source repositories:

- [![BabyAGI](https://img.shields.io/badge/GitHub-babyagi-white?logo=github&style=plastic) ![BabyAGI](https://img.shields.io/github/stars/yoheinakajima/babyagi?style=social)](https://github.com/yoheinakajima/babyagi)
- [![Auto-GPT](https://img.shields.io/badge/GitHub-Auto--GPT-white?logo=github&style=plastic) ![Auto-GPT](https://img.shields.io/github/stars/Significant-Gravitas/Auto-GPT?style=social)](https://github.com/Significant-Gravitas/Auto-GPT)

Please consider exploring and contributing to these projects if you like what we are doing.

## History
![Star History Chart](https://api.star-history.com/svg?repos=Josh-XT/AGiXT&type=Dat)
