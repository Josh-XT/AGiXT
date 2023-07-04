# AGiXT
[![RELEASE](https://img.shields.io/github/v/release/Josh-XT/AGiXT?label=Release%20Version&style=plastic)](https://github.com/josh-xt/AGiXT) 
[![LICENSE: MIT](https://img.shields.io/github/license/Josh-XT/AGiXT?label=License&style=plastic)](https://github.com/Josh-XT/AGiXT/blob/main/LICENSE) 
![DOCKER](https://img.shields.io/github/actions/workflow/status/Josh-XT/AGiXT/publish-docker.yml?branch=main&label=Docker&style=plastic) [![CODESTYLE](https://img.shields.io/badge/code%20style-Black-black?branch=main&label=Code%20Style&style=plastic)](https://black.readthedocs.io/en/stable/the_black_code_style/index.html) [![Contribute](https://img.shields.io/github/issues/Josh-XT/AGiXT/help%20wanted?color=purple&label=Quick%20Contribute&logo=github&style=plastic)](https://github.com/Josh-XT/AGiXT/labels/help%20wanted) 

[![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD) 
[![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh_XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT) 

[![Logo](https://josh-xt.github.io/AGiXT/images/AGiXT-gradient-flat.svg)](https://josh-xt.github.io/AGiXT/)

AGiXT is a dynamic Artificial Intelligence Automation Platform engineered to orchestrate efficient AI instruction management and task execution across a multitude of providers. Our solution infuses adaptive memory handling with a broad spectrum of commands to enhance AI's understanding and responsiveness, leading to improved task completion. The platform's smart features, like Smart Instruct and Smart Chat, seamlessly integrate web search, planning strategies, and conversation continuity, transforming the interaction between users and AI. By leveraging a powerful plugin system that includes web browsing and command execution, AGiXT stands as a versatile bridge between AI models and users. With an expanding roster of AI providers, code evaluation capabilities, comprehensive chain management, and platform interoperability, AGiXT is consistently evolving to drive a multitude of applications, affirming its place at the forefront of AI technology.

Embracing the spirit of extremity in every facet of life, we introduce AGiXT. This advanced AI Automation Platform is our bold step towards the realization of Artificial General Intelligence (AGI). Seamlessly orchestrating instruction management and executing complex tasks across diverse AI providers, AGiXT combines adaptive memory, smart features, and a versatile plugin system to maximize AI potential. With our unwavering commitment to innovation, we're dedicated to pushing the boundaries of AI and bringing AGI closer to reality.

## Table of Contents 📖

- [AGiXT](#agixt)
  - [Table of Contents 📖](#table-of-contents-)
  - [⚠️ Disclaimers!](#️-disclaimers)
    - [Monitor Your Usage!](#monitor-your-usage)
    - [Under Development!](#under-development)
  - [Key Features 🗝️](#key-features-️)
  - [Quick Start Guide](#quick-start-guide)
    - [Downloading the docker-compose file](#downloading-the-docker-compose-file)
    - [Editing the environment file](#editing-the-environment-file)
    - [Running AGiXT](#running-agixt)
    - [Updating AGiXT](#updating-agixt)
  - [Configuration](#configuration)
  - [Documentation](#documentation)
  - [Contributing](#contributing)
  - [Donations and Sponsorships](#donations-and-sponsorships)
  - [Our Team 🧑‍💻](#our-team-)
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

## Quick Start Guide

To get started quickly, you can use the Docker deployment. You will need [docker and docker-compose](https://docs.docker.com/compose/install/) installed on your system. 

Note: If you run locally without docker, it is unsupported.  Any issues you encounter will be closed without comment. Docker is the only way we can say "it works on my machine" and have it mean anything.

### Downloading the docker-compose file
Open a terminal and run the following commands to download the docker-compose file and the example environment file:

```
mkdir AGiXT
cd AGiXT
wget https://raw.githubusercontent.com/Josh-XT/AGiXT/main/docker-compose.yml
wget https://raw.githubusercontent.com/Josh-XT/AGiXT/main/.env.example
```

### Editing the environment file
Open the `.env.example` file in a text editor, you will want to at least change the `POSTGRES_PASSWORD` if nothing else.

- `POSTGRES_SERVER` is the name of the database server, this should be `db` if you are using the docker-compose file as-is.
- `POSTGRES_DB` is the name of the database, this should be `postgres` if you are using the docker-compose file as-is.
- `POSTGRES_PORT` is the port that the database is listening on, this should be `5432` if you are using the docker-compose file as-is.
- `POSTGRES_USER` is the username to connect to the database with, this should be `postgres` if you are using the docker-compose file as-is.
- `POSTGRES_PASSWORD` **is the password to connect to the database with, this should be changed from the example file.**
- `UVICORN_WORKERS` is the number of workers to run the web server with, this is `6` by default, adjust this to your system's capabilities.
- `AGIXT_HUB` is the name of the AGiXT hub, this should be `AGiXT/hub` if you want to use the [Open Source AGiXT hub.](https://github.com/AGiXT/hub) If you want to use your own fork of AGiXT hub, change this to your username and the name of your fork.
- `AGIXT_URI` is the URI of the AGiXT hub, this should be `http://agixt:7437` if you are using the docker-compose file as-is. If hosting the AGiXT server separately, change this to the URI of your AGiXT server, otherwise leave it as-is.
- `GITHUB_USER` is your GitHub username, this is only required if using your own AGiXT hub to pull your repository data.
- `GITHUB_TOKEN` is your GitHub personal access token, this is only required if using your own AGiXT hub to pull your repository data.

### Running AGiXT
Once you have edited the `.env.example` file, save it as `.env` and run the following command to start AGiXT:
```
docker-compose up -d
```

Follow the prompts to install the required dependencies.  Any time you want to run AGiXT in the future, just run `docker-compose up -d` again from the `AGiXT` directory.

- Access the web interface at http://localhost:8501
- Access the AGiXT API documentation at http://localhost:7437

### Updating AGiXT
To update AGiXT, run the following commands from your `AGiXT` directory:
```
docker-compose down
docker-compose pull
docker-compose up -d
```

## Configuration

Each AGiXT Agent has its own settings for interfacing with AI providers, and other configuration options. These settings can be set and modified through the web interface.
## Documentation

Need more information? Check out the [documentation](https://josh-xt.github.io/AGiXT) for more details to get a better understanding of the concepts and features of AGiXT.

## Contributing

[![Contribute](https://img.shields.io/github/issues/Josh-XT/AGiXT/help%20wanted?color=purple&label=Quick%20Contribute&logo=github&style=plastic)](https://github.com/Josh-XT/AGiXT/labels/help%20wanted) 

We welcome contributions to AGiXT! If you're interested in contributing, please check out our [contributions guide](https://github.com/Josh-XT/AGiXT/tree/main/.github/CONTRIBUTING.md) the [open issues on the backend](https://github.com/Josh-XT/AGiXT/issues), [open issues on the frontend](https://github.com/JamesonRGrieve/Agent-LLM-Frontend/issues) and [pull requests](https://github.com/Josh-XT/AGiXT/pulls), submit a [pull request](https://github.com/Josh-XT/AGiXT/pulls/new), or [suggest new features](https://github.com/Josh-XT/AGiXT/issues/new). To stay updated on the project's progress, [![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh_XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT) and [![Twitter](https://img.shields.io/badge/Twitter-Follow_@JamesonRGrieve-blue?logo=twitter&style=plastic)](https://twitter.com/JamesonRGrieve). Also feel free to join our [![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD).

## Donations and Sponsorships
We appreciate any support for AGiXT's development, including donations, sponsorships, and any other kind of assistance. If you would like to support us, please contact us through our [![Discord](https://img.shields.io/discord/1097720481970397356?label=Discord&logo=discord&logoColor=white&style=plastic&color=5865f2)](https://discord.gg/d3TkHRZcjD) or [![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh_XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT).

We're always looking for ways to improve AGiXT and make it more useful for our users. Your support will help us continue to develop and enhance the application. Thank you for considering to support us!

## Our Team 🧑‍💻
| Josh (@Josh-XT)                    | James (@JamesonRGrieve) | 
|-----------------------------------|-----------------------------------|
|[![GitHub](https://img.shields.io/badge/GitHub-Follow_@Josh--XT-white?logo=github&style=plastic)](https://github.com/Josh-XT)|[![GitHub](https://img.shields.io/badge/GitHub-Follow_@JamesonRGrieve-white?logo=github&style=plastic)](https://github.com/JamesonRGrieve)|
|[![Twitter](https://img.shields.io/badge/Twitter-Follow_@Josh__XT-blue?logo=twitter&style=plastic)](https://twitter.com/Josh_XT)|[![Twitter](https://img.shields.io/badge/Twitter-Follow_@JamesonRGrieve-blue?logo=twitter&style=plastic)](https://twitter.com/JamesonRGrieve)|
|[![LinkedIn](https://img.shields.io/badge/LinkedIn-Follow_@JoshXT-blue?logo=linkedin&style=plastic)](https://www.linkedin.com/in/joshxt/)|[![LinkedIn](https://img.shields.io/badge/LinkedIn-Follow_@JamesonRGrieve-blue?logo=linkedin&style=plastic)](https://www.linkedin.com/in/jamesonrgrieve/)|

## History
![Star History Chart](https://api.star-history.com/svg?repos=Josh-XT/AGiXT&type=Dat)
