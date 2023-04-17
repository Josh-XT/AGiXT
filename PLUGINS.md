# Agent-LLM: Adding Plugins

This document explains how to add plugins for the AI module, vector DB module, and embedding module in the Agent-LLM project.
## Table of Contents 
- [AI Module](https://chat.openai.com/?model=gpt-4#ai-module) 
- [Vector DB Module](https://chat.openai.com/?model=gpt-4#vector-db-module) 
- [Embedding Module](https://chat.openai.com/?model=gpt-4#embedding-module)
## AI Module

To add a new AI module plugin, follow these steps: 
1. **Create a new directory** : Create a new directory under the `provider` directory with the name of your new AI provider. For example, `provider/my_new_ai_provider`. 
2. ** file** : In the newly created directory, create an `__init__.py` file. This file should contain the `AIProvider` class for your new AI module. 
3. ** class** : Implement the `AIProvider` class in the `__init__.py` file. The class should have the following methods: 
- `__init__(self, model: str, temperature: float, max_tokens: int)`: Initializes the AI provider with the provided configuration. 
- `instruct(self, prompt: str, model: str, temperature: float, max_tokens: int) -> str`: Sends a prompt to the AI and returns its response. 
4. **Add prompt files** : Create a `vicuna` subdirectory in your AI provider's directory. In this subdirectory, create the following prompt files: 
- `execute.txt`: Contains the prompt for executing a task. 
- `priority.txt`: Contains the prompt for prioritizing tasks. 
- `task.txt`: Contains the prompt for creating new tasks. 
5. **Update environment variables** : In the `.env` file or any environment configuration file, update the `AI_PROVIDER` variable to match the name of your new AI provider.
## Vector DB Module

To add a new vector DB module plugin, follow these steps: 
1. **Create a new directory** : Create a new directory under the `vectordb` directory with the name of your new vector DB provider. For example, `vectordb/my_new_vector_db`. 
2. ** file** : In the newly created directory, create an `__init__.py` file. This file should contain the `VectorDB` class for your new vector DB module. 
3. ** class** : Implement the `VectorDB` class in the `__init__.py` file. The class should have the following methods: 
- `__init__(self)`: Initializes the vector database provider. 
- `results(self, query_embedding: np.ndarray, top_results_num: int) -> str`: Retrieves the top relevant results for a given query embedding. 
- `store_results(self, result_id: str, vector: np.ndarray, result: str, task: Dict)`: Stores the result and its vector representation in the vector database. 
4. **Update environment variables** : In the `.env` file or any environment configuration file, update the `VECTORDB_PROVIDER` variable to match the name of your new vector DB provider.
## Embedding Module

To add a new embedding module plugin, follow these steps: 
1. **Create a new directory** : Create a new directory under the `embedding` directory with the name of your new embedding method. For example, `embedding/my_new_embedding`. 
2. ** file** : In the newly created directory, create an `__init__.py` file. This file should contain the `Embedding` class for your new embedding module. 
3. ** class** : Implement the `Embedding` class in the `__init__.py` file. The class should have the following methods: 
- `__init__(self, model: str)`: Initializes the embedding provider with the provided configuration. 
- `embed_text(self, text: str) -> np.ndarray`: Converts a given text into a fixed-size vector representation. 
4. **Add any necessary files** : If your embedding method requires additional files, such as pre-trained models or configuration files, make sure to include them in your new embedding directory. 
5. **Update environment variables** : In the `.env` file or any environment configuration file, update the `EMBEDDING_PROVIDER` variable to match the name of your new embedding provider.

After following the steps for each module, your custom plugins will be integrated into the Agent-LLM project. Ensure that your environment variables are updated to use the new providers, and you should be able to utilize your custom AI, vector DB, and embedding modules.