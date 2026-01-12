# Conversations

Conversations in AGiXT are persistent chat sessions that maintain context across interactions with agents.

## Overview

Conversations store the complete history of interactions between you and AI agents. This enables:

- **Context retention**: Agents can reference previous messages in the conversation
- **Multi-agent discussions**: Switch between agents within the same conversation
- **Persistent memory**: Conversations are saved and can be resumed at any time

## Using Conversations

### Via CLI

```bash
# List and select conversations
agixt conversations

# Start a new conversation
agixt conversations -

# Chat in the current conversation
agixt prompt "Your message here"
```

### Via Web Interface

Access conversations at [http://localhost:3437](http://localhost:3437). The web interface provides:

- Conversation list with search
- Real-time chat with agents
- Message history
- Conversation management (rename, delete)

### Via API/SDK

```python
from agixtsdk import AGiXTSDK

agixt = AGiXTSDK(base_uri="http://localhost:7437", api_key="your_key")

# Get all conversations
conversations = agixt.get_conversations(agent_name="XT")

# Start a new conversation
agixt.new_conversation(agent_name="XT", conversation_name="Project Discussion")

# Get conversation history
history = agixt.get_conversation(
    agent_name="XT",
    conversation_name="Project Discussion"
)
```

## Conversation History Injection

Use `{conversation_history}` in prompts to inject recent conversation context. By default, the last 5 interactions are included.

Example prompt:
```
Based on our conversation:
{conversation_history}

Now, {user_input}
```

## Multi-Agent Conversations

Conversations can involve multiple agents. This is useful for:

- **Team simulations**: Different agents with different expertise
- **Handoffs**: Transfer complex tasks between specialized agents
- **Collaborative problem-solving**: Agents can build on each other's responses

Switch agents mid-conversation through the web interface or by specifying a different agent in API calls.

## Conversation Storage

Conversations are stored in the database and include:

- Message content
- Message timestamps
- Agent and user roles
- Associated memories and context

## Tips

- **Start fresh**: Begin a new conversation for unrelated topics to avoid context confusion
- **Name conversations**: Use descriptive names for easy retrieval
- **Context limits**: Long conversations may exceed token limits; start new conversations periodically
- **Privacy**: Conversations may be sent to AI providers; consider local inference for sensitive discussions
