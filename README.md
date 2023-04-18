# Agent-LLM

Agent-LLM is a versatile Python application that leverages AI language models for task management and problem-solving. Boasting both short-term and long-term memory capabilities, it recalls previous interactions and context. The application can browse the web, write its own commands, and more. Supporting various AI providers like OpenAI, Oobabooga Text Generation Web UI, and llama.cpp, Agent-LLM is both flexible and adaptable to diverse use cases.

## Key Features

- Efficient management of long-term and short-term memory
- Easily pluggable commands for extended functionality
- Compatibility with multiple AI providers
- Web browsing capabilities
- Command execution and code evaluation
- Customizable plugin system with prompts for various AI models
- Docker support for seamless deployment

## Installation and Setup

1. Clone the repository.
2. Install the required Python packages: `pip install -r requirements.txt`.
3. Configure the necessary environment variables in the `.env` file using `.env.example` as a template.
4. Launch Agent-LLM using Docker Compose (recommended) or by running the `main.py` script.

### Docker Setup (Recommended)

To launch the project using Docker Compose:

1. Install Docker and Docker Compose on your system.
2. Access the project's root folder.
3. Execute `docker-compose up` to build and activate the containers for both the Flask backend server and the frontend React application.

Access the web interface at http://localhost:3000
View the API documentation at http://localhost:5000

### Local Setup (Alternative)

To run Agent-LLM without Docker:

1. Launch the `main.py` script to initiate Agent-LLM.
2. Set up and run the frontend:
   1. Head to the `frontend` folder.
   2. Execute `npm install` to install the necessary dependencies.
   3. In a separate terminal, navigate to the project's root folder and run `python app.py` to activate the Flask backend server.
   4. Return to the `frontend` folder and run `npm start` to initiate the frontend React application.

## Configuration

Agent-LLM utilizes a `.env` configuration file to store AI language model settings, API keys, and other options. Use the supplied `.env.example` as a template to create your personalized `.env` file.

## Extending Functionality

### Commands

To introduce new commands, generate a new Python file in the `commands` folder and define a class inheriting from the `Commands` class. Implement the desired functionality as methods within the class and incorporate them into the `commands` dictionary.

### AI Providers

To switch AI providers, adjust the `AI_PROVIDER` setting in the `.env` file. The application is compatible with OpenAI, Oobabooga Text Generation Web UI, and llama.cpp. To support additional providers, create a new Python file in the `provider` folder and implement the required functionality.

### Building Prompts for Plugin System

Agent-LLM employs a plugin system with customizable prompts for instructing various AI models. These prompts are stored in the `model-prompts` folder and are categorized by model name. Each model has four prompt types:

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

Run Agent-LLM using Docker Compose (recommended) or by running the `main.py` script. The application will load the initial task and objective from the configuration file and begin task execution. As tasks are completed, Agent-LLM will generate new tasks, prioritize them, and continue working through the task list.
