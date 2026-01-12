# Agents

Agents are AI personas that combine a language model provider with specific settings and capabilities. Each agent can be customized with different providers, commands, and behaviors.

## Agent Settings

Agent Settings allow users to manage and configure their agents. This includes adding new agents, updating existing agents, and deleting agents as needed. Users can customize the provider and embedder used by the agent to generate responses. Additionally, users have the option to set custom settings and enable or disable specific agent commands, giving them fine control over the agent's behavior and capabilities.

### Default Settings

| Setting | Default | Description |
| --- | --- | --- |
| `provider` | `ezlocalai` | The AI provider used by the agent to generate responses |
| `embedder` | `default` | The embedder used for memory operations |
| `AI_MODEL` | Varies by provider | The model used for generating responses |
| `AI_TEMPERATURE` | `0.7` | Controls randomness in responses (0-1) |
| `AI_TOP_P` | `1` | Controls diversity of responses |
| `MAX_TOKENS` | `4000` | Maximum response length |
| `helper_agent_name` | `XT` | Helper agent for assistance requests |
| `WEBSEARCH_TIMEOUT` | `0` | Timeout for web searches (0 = no timeout) |
| `WAIT_BETWEEN_REQUESTS` | `1` | Seconds to wait between LLM requests |
| `WAIT_AFTER_FAILURE` | `3` | Seconds to wait after a failed request |
| `stream` | `False` | Enable streaming responses |
| `WORKING_DIRECTORY` | `./WORKSPACE` | Agent's file system workspace |
| `WORKING_DIRECTORY_RESTRICTED` | `True` | Restrict file access to workspace |

## Creating an Agent

### Via Web Interface

1. Navigate to the AGiXT web interface at [http://localhost:3437](http://localhost:3437)
2. Go to Agent Management
3. Click "Create Agent"
4. Configure the provider, model, and settings
5. Enable desired commands

### Via Python SDK

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_key")

# Create a new agent
agixt.add_agent(
    agent_name="MyAgent",
    settings={
        "provider": "openai",
        "AI_MODEL": "gpt-4",
        "AI_TEMPERATURE": "0.7",
        "MAX_TOKENS": "4000",
    }
)
```

## Agent Commands

Commands are extension functions that agents can execute. Enable commands sparingly—only give agents the commands they need for their specific tasks.

```python
# Enable specific commands
agixt.update_agent_commands(
    agent_name="MyAgent",
    commands={
        "Web Search": True,
        "Read File": True,
        "Write to File": False,  # Disable if not needed
    }
)
```

## Best Practices

1. **Use specific providers**: Choose the right provider for your use case (ezLocalai for local, OpenAI/Anthropic for cloud)
2. **Limit commands**: Only enable commands the agent actually needs
3. **Set appropriate timeouts**: Configure timeouts based on expected response times
4. **Monitor token usage**: Watch token consumption, especially with cloud providers
