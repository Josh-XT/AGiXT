# Agent-LLM

Agent-LLM is a versatile Python application that leverages AI language models for task management and problem-solving. Boasting both short-term and long-term memory capabilities, it recalls previous interactions and context. The application can browse the web, write its own commands, and more. Supporting various AI providers like [OpenAI GPT-3.5, GPT-4, ChatGPT](https://openai.com/), [Google Bard](https://bard.google.com), [Microsoft Bing](https://bing.com), [Oobabooga Text Generation Web UI](https://github.com/oobabooga/text-generation-webui), and [llama.cpp](https://github.com/ggerganov/llama.cpp), Agent-LLM is both flexible and adaptable to diverse use cases. The list of providers will continue to grow.

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs.  We're NOT responsible for your usage under any circumstance.**

![image](https://user-images.githubusercontent.com/102809327/233168030-58c263f8-c1f4-4426-acaf-e1c4a662cc4e.png)


⚠️ **This project is under active development and may still have issues.** We appreciate your understanding and patience. If you encounter any problems, please first check the open issues. If your issue is not listed, kindly create a new issue detailing the error or problem you experienced. Thank you for your support!

## Table of Contents

- [Agent-LLM](#agent-llm)
  - [Table of Contents](#table-of-contents)
  - [Key Features](#key-features)
  - [Web Application Features](#web-application-features)
  - [Quick Start](#quick-start)
  - [Development Environment Installation and Setup](#development-environment-installation-and-setup)
  - [Configuration](#configuration)
    - [Docker Setup (Recommended)](#docker-setup-recommended)
    - [Local Setup (Alternative)](#local-setup-alternative)
  - [API Endpoints](#api-endpoints)
  - [Extending Functionality](#extending-functionality)
    - [Commands](#commands)
    - [AI Providers](#ai-providers)
    - [Building Prompts for Plugin System](#building-prompts-for-plugin-system)
  - [Project Structure](#project-structure)
  - [Acknowledgments](#acknowledgments)
  - [Contributing](#contributing)
  - [Usage](#usage)

## Key Features

- Efficient management of long-term and short-term memory

- Easily pluggable commands for extended functionality

- Compatibility with multiple AI providers

  - OpenAI GPT-3.5, GPT-4, ChatGPT

  - Google Bard

  - Microsoft Bing

  - Oobabooga Text Generation Web UI

  - llama.cpp

- Web browsing capabilities

- Command execution and code evaluation

- Customizable plugin system with prompts for various AI models

- Docker support for seamless deployment

- Integration with Huggingface for audio-to-text conversion

- Support for interacting with Twitter, GitHub, Google, DALL-E, and more growing fast.

- Voice options for text-to-speech, including Brian TTS, Mac OS TTS, and ElevenLabs

## Web Application Features

The frontend web application of Agent-LLM provides an intuitive and interactive user interface for users to:

- Manage agents: View the list of available agents, add new agents, delete agents, and switch between agents.
- Set objectives: Input objectives for the selected agent to accomplish.
- Start tasks: Initiate the task manager to execute tasks based on the set objective.
- Instruct agents: Interact with agents by sending instructions and receiving responses in a chat-like interface.
- Available commands: View the list of available commands and click on a command to insert it into the objective or instruction input boxes.
- Dark mode: Toggle between light and dark themes for the frontend.

The frontend is built using React and Material-UI and communicates with the backend through API endpoints.

## Quick Start

1. Obtain an OpenAI API key from [OpenAI](https://platform.openai.com).
2. Set the `OPENAI_API_KEY` in your `.env` file using the provided [.env.example](https://github.com/Josh-XT/Agent-LLM/blob/main/.env.example) as a template.
3. Run the following Docker command in the folder with your `.env` file:

```
docker run -it --pull always -p 80:5000 --env-file=.env ghcr.io/josh-xt/agent-llm:main
```

4. Access the web interface at http://localhost

For more detailed setup and configuration instructions, refer to the sections below.

## Development Environment Installation and Setup

1. Clone the repository.
```
git clone https://github.com/Josh-XT/Agent-LLM
```
2. Install the required Python packages:
```
pip install -r requirements.txt
```
3. Configure the necessary environment variables in the `.env` file using `.env.example` as a template.
4. Launch Agent-LLM using Docker (recommended) or by following the steps in the "Local Setup (Alternative)" section to set up the frontend and run the `app.py` script.

## Configuration

Agent-LLM utilizes a `.env` configuration file to store AI language model settings, API keys, and other options. Use the supplied `.env.example` as a template to create your personalized `.env` file. Configuration settings include:

- **INSTANCE CONFIG**: Set the agent name, objective, and initial task.
- **AI_PROVIDER**: Choose between OpenAI, llama.cpp, or Oobabooga for your AI provider.
- **AI_PROVIDER_URI**: Set the URI for custom AI providers such as Oobabooga Text Generation Web UI (default is http://127.0.0.1:7860).
- **MODEL_PATH**: Set the path to the AI model if using llama.cpp or other custom providers.
- **BING_CONVERSATION_STYLE**: Set the conversation style if using Microsoft Bing (options are creative, balanced, and precise).
- **CHATGPT_USERNAME** and **CHATGPT_PASSWORD**: Set the ChatGPT username and password.
- **COMMANDS_ENABLED**: Enable or disable command extensions.
- **MEMORY SETTINGS**: Configure short-term and long-term memory settings.
- **AI_MODEL**: Specify the AI model to be used (e.g., gpt-3.5-turbo, gpt-4, text-davinci-003, vicuna, etc.).
- **AI_TEMPERATURE**: Set the AI temperature (leave default if unsure).
- **MAX_TOKENS**: Set the maximum number of tokens for AI responses (default is 2000).
- **WORKING_DIRECTORY**: Set the agent's working directory.
- **EXTENSIONS_SETTINGS**: Configure settings for OpenAI, Huggingface, Selenium, Twitter, and GitHub.
- **VOICE_OPTIONS**: Choose between Brian TTS, Mac OS TTS, or ElevenLabs for text-to-speech.

For a detailed explanation of each setting, refer to the `.env.example` file provided in the repository.

### Docker Setup (Recommended)

To launch the project using Docker:

1. Install Docker on your system.
2. Access the project's root folder.
3. Execute the following command to build and activate the containers for both the Flask backend server and the frontend React application:
```
docker run -it --pull always -p 80:5000 --env-file=.env ghcr.io/josh-xt/agent-llm:main
```

Access the web interface at http://localhost

### Local Setup (Alternative)

To run Agent-LLM without Docker:


1. Set up and run the frontend:
   1. Head to the `frontend` folder.
   2. Execute the following command to install the necessary dependencies:
   ```
   npm install
   ```
   3. In a separate terminal, navigate to the project's root folder and run the following command to activate the Flask backend server:
   ```
   python app.py
   ```
   4. Return to the `frontend` folder and run the following command to initiate the frontend React application:
   ```
   npm start
   ```

## API Endpoints

Agent-LLM provides several API endpoints for managing agents, setting objectives, managing tasks, and more. The following are the available API endpoints:

1. **Add Agent**: `/api/add_agent/<string:agent_name>` (POST)

   Adds a new agent with the given agent name.

2. **Delete Agent**: `/api/delete_agent/<string:agent_name>` (DELETE)

   Deletes an existing agent with the given agent name.

3. **Get Agents**: `/api/get_agents` (GET)

   Retrieves a list of all available agents.

4. **Get Chat History**: `/api/get_chat_history/<string:agent_name>` (GET)

   Retrieves the chat history of an agent with the given agent name.

5. **Instruct**: `/api/instruct/<string:agent_name>` (POST)

   Sends an instruction prompt to the agent and receives a response.

6. **Get Commands**: `/api/get_commands/<string:agent_name>` (GET)

   Retrieves a list of available commands.

7. **Get Available Commands**: `/api/get_available_commands/<string:agent_name>` (GET)

   Retrieves a list of enabled commands for a specific agent.

8. **Enable Command**: `/api/enable_command/<string:agent_name>/<string:command_name>` (POST)

   Enables a specific command for an agent.

9. **Disable Command**: `/api/disable_command/<string:agent_name>/<string:command_name>` (POST)

   Disables a specific command for an agent.

10. **Disable All Commands**: `/api/disable_all_commands/<string:agent_name>` (POST)

    Disables all commands for an agent.

11. **Enable All Commands**: `/api/enable_all_commands/<string:agent_name>` (POST)

    Enables all commands for an agent.

12. **Start Task Agent**: `/api/task/start/<string:agent_name>` (POST)

    Starts the task agent with the given agent name and objective.

13. **Stop Task Agent**: `/api/task/stop/<string:agent_name>` (POST)

    Stops the task agent with the given agent name.

14. **Get Task Output**: `/api/task/output/<string:agent_name>` (GET)

    Retrieves the output of the task agent with the given agent name.

15. **Get Task Status**: `/api/task/status/<string:agent_name>` (GET)

    Retrieves the status of the task agent with the given agent name.

To learn more about the API endpoints and their usage, visit the API documentation at http://localhost:5000/api/docs when running the application locally, or http://localhost/api/docs if running with Docker.

## Extending Functionality

### Commands

To introduce new commands, generate a new Python file in the `commands` folder and define a class inheriting from the `Commands` class. Implement the desired functionality as methods within the class and incorporate them into the `commands` dictionary.

### AI Providers

To switch AI providers, adjust the `AI_PROVIDER` setting in the `.env` file. The application is compatible with OpenAI, Oobabooga Text Generation Web UI, and llama.cpp. To support additional providers, create a new Python file in the `provider` folder and implement the required functionality.

### Building Prompts for Plugin System

Agent-LLM employs a plugin system with customizable prompts for instructing various AI models. These prompts are stored in the `model-prompts` folder and are categorized by model name. Each model has five prompt types:

1. model-prompts/{model}/execute.txt
2. model-prompts/{model}/priority.txt
3. model-prompts/{model}/system.txt
4. model-prompts/{model}/task.txt
5. model-prompts/{model}/script.txt

For a comprehensive explanation of prompt formats and usage, refer to the [PROMPTS.md](PROMPTS.md) file.

## Project Structure

The project is organized into several folders:

- `commands`: Stores pluggable command modules for enhancing Agent-LLM's functionality.
- `frontend`: Contains frontend code for Agent-LLM's web interface.
- `model-prompts`: Houses prompt templates for the various AI models used by Agent-LLM.
- `provider`: Holds the implementations for the supported AI providers.

## Acknowledgments

This project was inspired by and utilizes code from the following repositories:

- [babyagi](https://github.com/yoheinakajima/babyagi)
- [Auto-GPT](https://github.com/Significant-Gravitas/Auto-GPT)

Please consider exploring and contributing to these projects as well.

## Contributing

We welcome contributions to Agent-LLM! If you're interested in contributing, please check out the open issues, submit pull requests, or suggest new features. To stay updated on the project's progress, follow [@Josh_XT](https://twitter.com/Josh_XT) on Twitter.

## Usage

Run Agent-LLM using Docker (recommended) or by running the `app.py` script. The application will load the initial task and objective from the configuration file and begin task execution. As tasks are completed, Agent-LLM will generate new tasks, prioritize them, and continue working through the task list.
