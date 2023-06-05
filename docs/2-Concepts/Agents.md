# Agents
Agents are a combintation of a single model and a single directive. An agent can be given a task to pursue. In the course of pursuing this task, the agent may request the execution of commands through the AGiXT server. If this occurs, the result of that command will be passed back into the agent and execution will continue until the agent is satisfied that its goal is complete.

## Agent Settings
Agent Settings allow users to manage and configure their agents. This includes adding new agents, updating existing agents, and deleting agents as needed. Users can customize the provider and embedder used by the agent to generate responses. Additionally, users have the option to set custom settings and enable or disable specific agent commands, giving them fine control over the agent's behavior and capabilities.

If the agent settings are not specified, the agent will use the default settings. The default settings are as follows:

| Setting | Value |
| --- | --- |
| `provider` | `gpt4free` |
| `embedder` | `default` |
| `AI_MODEL` | `gpt-4` |
| `AI_TEMPERATURE` | `0.7` |
| `MAX_TOKENS` | `4000` |