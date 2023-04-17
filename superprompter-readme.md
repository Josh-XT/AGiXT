# SuperPrompter

SuperPrompter is a Python library for easily generating natural language responses to a given task using AI models. It supports multiple AI providers and models, allowing you to choose the one that best suits your needs.
## Features
- Supports multiple AI providers, including OpenAI and LlamaCpp.
- Can process a folder of files or a website to generate responses to a given task.
- Generates natural language responses using state-of-the-art AI models.
- Stores results in a Chroma database for later retrieval.
## Installation

SuperPrompter requires Python 3.6 or later. You can install it using pip:

```bash

pip install superprompter
```



You will also need to set up an environment file with your instance settings. Here is an example env file:

```makefile

# INSTANCE CONFIG
AGENT_NAME=My-Agent-Name

# AI_PROVIDER can currently be openai, llamacpp (local only), or oobabooga (local only)
AI_PROVIDER=openai

# AI Model can either be gpt-3.5-turbo, gpt-4, text-davinci-003, vicuna, etc
# This determines what prompts are given to the AI and determines which model is used for certain providers.
AI_MODEL=gpt-3.5-turbo

# Temperature for AI, leave default if you don't know what this is
AI_TEMPERATURE=0.5

# Extensions settings

# OpenAI settings for running OpenAI AI_PROVIDER
OPENAI_API_KEY=my-openai-api-key
```


## Usage

Here's an example of how to use SuperPrompter:

```python

from superprompter import SuperPrompter

# Set the task you want to perform
task = "Perform the task with the given context."

# Specify the path to a folder containing files or a website to scrape
folder_path = "/path/to/your/folder"
url = "https://example.com"

# Create a new instance of SuperPrompter and generate a response
sp = SuperPrompter(task, folder_path, url)
print("Response:", sp.response)
```



When you create a new instance of `SuperPrompter`, you specify the task you want to perform and either a folder containing files or a website to scrape. SuperPrompter then generates a natural language response using an AI model and stores the result in a Chroma database. You can retrieve the response using the `response` property of the `SuperPrompter` instance.
## Contributing

We welcome contributions! If you have an idea for a new feature or a bugfix, please open an issue or submit a pull request.