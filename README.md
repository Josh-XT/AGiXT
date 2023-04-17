`README.md`
# AI Task Manager - Agent-LLM

AI Task Manager with Agent-LLM is a Python application that uses AI language models to manage tasks and provide solutions. It features both short-term and long-term memory capabilities, allowing it to remember previous interactions and context. The application can browse the web, write its own commands, and more. It supports various AI providers such as OpenAI, Oobabooga Text Generation Web UI, and llama.cpp, making it flexible and adaptable to different use cases.

## Features

- Long-term and short-term memory management
- Easily pluggable commands for extended functionality
- Supports multiple AI providers
- Web browsing capabilities
- Command execution and code evaluation
- Plugin System with customizable prompts for various AI models
- Docker support for easy deployment

## Installation and Setup

1. Clone the repository.
2. Install the required Python packages: `pip install -r requirements.txt`.
3. Set up the necessary environment variables in the `.env` file using `.env.example` as a template.
4. Run the `main.py` script to start the AI Task Manager.

## Web Interface Setup

To set up and run the frontend:

1. Navigate to the `frontend` folder.
2. Run `npm install` to install the required dependencies.
3. In a separate terminal, navigate to the root folder of the project and run `python app.py` to start the Flask backend server.
4. Go back to the `frontend` folder and run `npm start` to start the frontend React application.

### Docker Setup

Alternatively, you can use Docker Compose to start the project:

1. Install Docker and Docker Compose on your system.
2. Navigate to the root folder of the project.
3. Run `docker-compose up` to build and start the containers for the Flask backend server and the frontend React application.

The web interface is accessible at http://localhost:3000
The API documentation is accessible at http://localhost:5000


## Configuration

The application uses a configuration file `.env` to store settings for the AI language model, various API keys, and other configuration options. Use the provided `.env.example` as a template to set up your own `.env` file.

## Extending Functionality

### Commands

To add new commands, create a new Python file in the `commands` folder and define a class that inherits from the `Commands` class. Implement the desired functionality as methods within the class and add them to the `commands` dictionary.

### AI Providers

To use a different AI provider, modify the `AI_PROVIDER` setting in the `.env` file. The application supports OpenAI, Oobabooga Text Generation Web UI, and llama.cpp. If you want to add support for a new provider, create a new Python file in the `provider` folder and implement the necessary functionality.

### Building Prompts for Plugin System

AI Task Manager uses a Plugin System with customizable prompts for various AI models to instruct AI agents. The prompts are located in the `model-prompts` folder and are organized by the model name. Each model has four types of prompts:

1. model-prompts/{model}/execute.txt
2. model-prompts/{model}/priority.txt
3. model-prompts/{model}/system.txt
4. model-prompts/{model}/task.txt

For detailed information on the format and usage of these prompts, refer to the [PROMPTS.md](PROMPTS.md) file.

## Folder Structure

The project is organized into several folders:

- `commands`: Contains the pluggable command modules for extending the AI Task Manager's functionality.
- `frontend`: Contains the frontend code for the web interface of the AI Task Manager.
- `model-prompts`: Contains the prompt templates for the different AI models used by the AI Task Manager.
- `provider`: Contains the implementations for the supported AI providers.

## Acknowledgments

This project was inspired by and uses code from the following repositories:

- [babyagi](https://github.com/yoheinakajima/babyagi)
- [Auto-GPT](https://github.com/Significant-Gravitas/Auto-GPT)

Please consider checking them out and contributing to those projects as well.

## Contributing

We welcome contributions to the AI Task Manager with Agent-LLM! If you're interested in contributing, please check out the open issues, submit pull requests, or suggest new features. To stay updated on the project's progress, follow [@Josh_XT](https://twitter.com/Josh_XT) on Twitter.

## Usage

Run the `main.py` script to start the AI Task Manager with Agent-LLM. The application will load the initial task and objective from the configuration file and start executing tasks. As tasks are completed, the AI Task Manager will create new tasks, prioritize them, and continue working through the task list.