# Agent-LLM

Agent-LLM is an Artificial Intelligence Automation Platform designed for efficient AI instruction management across multiple providers. Equipped with adaptive memory, this versatile solution offers a powerful plugin system that supports a wide range of commands, including web browsing. With growing support for numerous AI providers and models, Agent-LLM is constantly evolving to cater to diverse applications.

[<img src="https://assets-global.website-files.com/6257adef93867e50d84d30e2/636e0a6a49cf127bf92de1e2_icon_clyde_blurple_RGB.png" height="70" style="margin: 0 10px">](https://discord.gg/vfXjyuKZ)[<img src="https://img.freepik.com/free-icon/twitter_318-674515.jpg" height="70" style="margin: 0 10px">](https://twitter.com/Josh_XT)[<img src="https://qph.cf2.quoracdn.net/main-qimg-729a22aba98d1235fdce4883accaf81e" height="70" style="margin: 0 10px">](https://github.com/Josh-XT/Agent-LLM)

⚠️ **Please note that using some AI providers, such as OpenAI's API, can be expensive. Monitor your usage carefully to avoid incurring unexpected costs.  We're NOT responsible for your usage under any circumstance.**

![image](https://user-images.githubusercontent.com/102809327/233758245-94535c01-d4e8-4f9c-9b1c-244873361c85.png)

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
    - [Agent Management](#agent-management)
    - [Task Management](#task-management)
    - [Chain Management](#chain-management)
  - [Extending Functionality](#extending-functionality)
    - [Commands](#commands)
    - [AI Providers](#ai-providers)
    - [Building Prompts for Plugin System](#building-prompts-for-plugin-system)
  - [Project Structure](#project-structure)
  - [Acknowledgments](#acknowledgments)
  - [Contributing](#contributing)
  - [Donations and Sponsorships](#donations-and-sponsorships)
  - [Usage](#usage)

## Key Features

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

- Integration with Huggingface for audio-to-text conversion

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

The frontend is built using React and Material-UI and communicates with the backend through API endpoints.

## Quick Start

1. Obtain an OpenAI API key from [OpenAI](https://platform.openai.com).
2. Set the `OPENAI_API_KEY` in your `.env` file using the provided [.env.example](https://github.com/Josh-XT/Agent-LLM/blob/main/.env.example) as a template.
3. Run the following Docker command in the folder with your `.env` file:

```
docker compose up -d --build
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
docker run -it --pull always -p 80:3000 --env-file=.env ghcr.io/josh-xt/agent-llm-frontend:main
docker run -it --pull always -p 5000:5000 --env-file=.env ghcr.io/josh-xt/agent-llm-backend:main
```

Access the web interface at http://localhost

### Local Setup (Alternative)

To run Agent-LLM without Docker:


1. Set up and run the frontend:
   1. Head to the `frontend` folder.
   2. Execute the following command to install the necessary dependencies:
   ```
   npm install
   npm run build
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

Agent-LLM provides several API endpoints for managing agents, managing tasks, and managing chains. The following are the available API endpoints:

### Agent Management

1. **Get Agents**: `/api/agent` (GET)

   Retrieves a list of all available agents.
   
   Output: `{"agents": ["agent1", "agent2", "agent3"]}`

2. **Add Agent**: `/api/agent` (POST)

   Adds a new agent with the given agent name.

   Output: `{"message": "Agent 'agent1' added"}`

3. **Get Agent Config**: `/api/agent/<string:agent_name>` (GET)

   Retrieves the configuration of an agent with the given agent name.

   Output: `{"agent_config": {"agent_name": "agent1", "agent_type": "task", "commands": {"command1": "true", "command2": "false"}}}`

4. **Rename Agent**: `/api/agent/<string:agent_name>` (PUT)

   Renames an existing agent to a new name.

   Output: `{"message": "Agent 'agent1' renamed to 'agent2'"}`

5. **Delete Agent**: `/api/agent/<string:agent_name>` (DELETE)

   Deletes an existing agent with the given agent name.

   Output: `{"message": "Agent 'agent1' deleted"}`

6. **Get Commands**: `/api/agent/<string:agent_name>/command` (GET)

   Retrieves a list of available commands for an agent.

   Output: `{"commands": [ {"friendly_name": "Friendly Name", "name": "command1", "enabled": True}, {"friendly_name": "Friendly Name 2", "name": "command2", "enabled": False }]}`

7. **Toggle Command**: `/api/agent/<string:agent_name>/command` (PUT)

   Toggles a specific command for an agent.

   Output: `{"message": "Command 'command1' enabled for agent 'agent1'"}`

8. **Chat**: `/api/agent/<string:agent_name>/chat` (POST)

   Sends a chat prompt to the agent and receives a response.

   Output: `{"message": "Prompt sent to agent 'agent1'"}`

9. **Get Chat History**: `/api/<string:agent_name>/chat` (GET)

   Retrieves the chat history of an agent with the given agent name.

   Output: `{"chat_history": ["chat1", "chat2", "chat3"]}`

10. **Instruct**: `/api/agent/<string:agent_name>/instruct` (POST)

   Sends an instruction prompt to the agent and receives a response.

   Output: `{"message": "Prompt sent to agent 'agent1'"}`

11. **Wipe Agent Memories**: `/api/agent/<string:agent_name>/memory` (DELETE)

   Wipes the memories of an agent with the given agent name.

   Output: `{"message": "Agent 'agent1' memories wiped"}`

### Task Management

12. **Toggle Task Agent**: `/api/agent/<string:agent_name>/task` (PUT)

   Toggles the task agent with the given agent name on and off.

   Output: `{"message": "Task agent 'agent1' started"}`
   Output: `{"message": "Task agent 'agent1' stopped"}`

13. **Get Task Output**: `/api/agent/<string:agent_name>/task` (GET)

   Retrieves the output of the task agent with the given agent name.

   Output: `{"output": "output"}`

14. **Get Task Status**: `/api/agent/<string:agent_name>/task/status` (GET)

    Retrieves the status of the task agent with the given agent name.

    Output: `{"status": "status"}`

### Chain Management

15. **Get Chains**: `/api/chain` (GET)

    Retrieves all available chains.

    Output: `{chain_name: {step_number: {prompt_type: prompt}}}`

16. **Get Chain**: `/api/chain/<string:chain_name>` (GET)

    Retrieves a specific chain.

    Output: `{step_number: {prompt_type: prompt}}`

17. **Add Chain**: `/api/chain` (POST)

    Adds a new chain.

    Output: `{step_number: {prompt_type: prompt}}`

18. **Add Chain Step**: `/api/chain/<string:chain_name>/step` (POST)

    Adds a step to an existing chain.

    Output: `{step_number: {prompt_type: prompt}}`

19. **Update Step**: `/api/chain/<string:chain_name>/step/<string:step_number>` (PUT)

    Updates a step in an existing chain.

    Output: `{step_number: {prompt_type: prompt}}`

20. **Delete Chain**: `/api/chain/<string:chain_name>` (DELETE)

    Deletes a specific chain.

    Output: `{step_number: {prompt_type: prompt}}`

21. **Delete Chain Step**: `/api/chain/<string:chain_name>/step/<string:step_number>` (DELETE)

    Deletes a step from an existing chain.

    Output: `{step_number: {prompt_type: prompt}}`

22. **Run Chain**: `/api/chain/<string:chain_name>/run` (POST)

    Runs a specific chain for an agent.

    Output: `{step_number: {prompt_type: prompt}}`

To learn more about the API endpoints and their usage, visit the API documentation at http://localhost:5000/docs (swagger) or http://localhost:5000/redoc (Redoc).

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

## Donations and Sponsorships
We appreciate any support for Agent-LLM's development, including donations, sponsorships, and any other kind of assistance. If you would like to support us, please contact us through our [Discord server](https://discord.gg/Na8M7mTayp) or Twitter [@Josh_XT](https://twitter.com/Josh_XT).

We're always looking for ways to improve Agent-LLM and make it more useful for our users. Your support will help us continue to develop and enhance the application. Thank you for considering to support us!

## Usage

Run Agent-LLM using Docker (recommended) or by running the `app.py` script. The application will load the initial task and objective from the configuration file and begin task execution. As tasks are completed, Agent-LLM will generate new tasks, prioritize them, and continue working through the task list.
