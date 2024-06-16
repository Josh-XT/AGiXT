# Agents

Agents are a combintation of a single model and a single directive. An agent can be given a task to pursue. In the course of pursuing this task, the agent may request the execution of commands through the AGiXT server. If this occurs, the result of that command will be passed back into the agent and execution will continue until the agent is satisfied that its goal is complete.

## Agent Settings

Agent Settings allow users to manage and configure their agents. This includes adding new agents, updating existing agents, and deleting agents as needed. Users can customize the provider and embedder used by the agent to generate responses. Additionally, users have the option to set custom settings and enable or disable specific agent commands, giving them fine control over the agent's behavior and capabilities.

If the agent settings are not specified, the agent will use the default settings. The default settings are as follows:

| Setting | Value | Description |
| --- | --- | --- |
| `provider` | `gpt4free` | The large language model provider used by the agent to generate responses. |
| `embedder` | `default` | The embedder used by the agent to generate embeddings. |
| `AI_MODEL` | `gpt-3.5-turbo` | The large language model used by the agent with the selected provider to generate responses. |
| `AI_TEMPERATURE` | `0.7` | The temperature used by the agent to generate responses. |
| `AI_TOP_P` | `1` | The top p value used by the agent to generate responses. |
| `MAX_TOKENS` | `4000` | The maximum number of tokens used by the agent to generate responses. |
| `helper_agent_name` | `gpt4free` | The name of the helper agent used by the agent if it chooses to ask for help when enabled. |
| `WEBSEARCH_TIMEOUT` | `0` | Timeout for websearches to create a deadline to stop trying. |
| `WAIT_BETWEEN_REQUESTS` | `1` | The number of seconds to wait between requests to the LLM provider. |
| `WAIT_AFTER_FAILURE` | `3` | The number of seconds to wait after a failure to try again to make a request to the LLM provider. |
| `stream` | `False` | Whether or not to stream the response from the LLM provider. |
| `WORKING_DIRECTORY` | `./WORKSPACE` | The working directory to use for the agent. |
| `WORKING_DIRECTORY_RESTRICTED` | `True` | Whether or not to restrict the working directory to the agent's working directory. |
