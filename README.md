# AI Task Manager - Agent-LLM

AI Task Manager with Agent-LLM is a Python application that uses AI language models to manage tasks and provide solutions. It features both short-term and long-term memory capabilities, allowing it to remember previous interactions and context. The application can browse the web, write its own commands, and more. It supports various AI providers such as OpenAI, Oobabooga Text Generation Web UI, and llama.cpp, making it flexible and adaptable to different use cases.

## Features

- Long-term and short-term memory management
- Easily pluggable commands for extended functionality
- Supports multiple AI providers
- Web browsing capabilities
- Command execution and code evaluation

## Installation and Setup

1. Clone the repository.
2. Install the required Python packages: `pip install -r requirements.txt`.
3. Set up the necessary environment variables in the `.env` file using `.env.example` as a template.
4. Run the `main.py` script to start the AI Task Manager.

## Configuration

The application uses a configuration file `.env` to store settings for the AI language model, various API keys, and other configuration options. Use the provided `.env.example` as a template to set up your own `.env` file.

## Extending Functionality

### Commands

To add new commands, create a new Python file in the `commands` folder and define a class that inherits from the `Commands` class. Implement the desired functionality as methods within the class and add them to the `commands` dictionary.

### AI Providers

To use a different AI provider, modify the `AI_PROVIDER` setting in the `.env` file. The application supports OpenAI, Oobabooga Text Generation Web UI, and llama.cpp. If you want to add support for a new provider, create a new Python file in the `provider` folder and implement the necessary functionality.

## Folder Structure

The project is organized into several folders:

- `commands`: Contains the pluggable command modules for extending the AI Task Manager's functionality.
- `frontend`: Contains the frontend code for the web interface of the AI Task Manager.
- `model-prompts`: Contains the prompt templates for the different AI models used by the AI Task Manager.
- `provider`: Contains the implementations for the supported AI providers.

## Usage

Run the `main.py` script to start the AI Task Manager with Agent-LLM. The application will load the initial task and objective from the configuration file and start executing tasks. As tasks are completed, the AI Task Manager will create new tasks, prioritize them, and continue working through the task list until all tasks are complete.
