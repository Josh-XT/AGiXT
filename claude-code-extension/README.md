# AGiXT MCP Server for Claude Code

A Model Context Protocol (MCP) server that enables Claude Code to interact with AGiXT agents, chains, conversations, and memory systems.

## Features

- **Agent Management**: Create, configure, and interact with AGiXT agents
- **Chat Completions**: Send messages and get AI-powered responses
- **Chain Execution**: Run AGiXT chains for complex multi-step workflows
- **Memory Management**: Store, query, and manage agent memories
- **Conversation Management**: Create and manage conversation contexts
- **Command Execution**: Execute agent commands and extensions

## Installation

### From Source

```bash
cd claude-code-extension
pip install -e .
```

### Using pip

```bash
pip install agixt-mcp-server
```

## Configuration

### Environment Variables

Create a `.env` file or set the following environment variables:

```env
AGIXT_API_URL=http://localhost:7437
AGIXT_API_KEY=your-api-key-here
AGIXT_AGENT_NAME=default-agent
```

### Claude Code Configuration

Add the following to your Claude Code MCP settings (`~/.config/claude/claude_desktop_config.json` on Linux/Mac or appropriate location on Windows):

```json
{
  "mcpServers": {
    "agixt": {
      "command": "agixt-mcp-server",
      "env": {
        "AGIXT_API_URL": "http://localhost:7437",
        "AGIXT_API_KEY": "your-api-key-here",
        "AGIXT_AGENT_NAME": "gpt4"
      }
    }
  }
}
```

Or if running from source:

```json
{
  "mcpServers": {
    "agixt": {
      "command": "python",
      "args": ["-m", "agixt_mcp_server.server"],
      "cwd": "/path/to/AGiXT/claude-code-extension",
      "env": {
        "AGIXT_API_URL": "http://localhost:7437",
        "AGIXT_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## Available Tools

### Agent Tools

| Tool | Description |
|------|-------------|
| `agixt_list_agents` | List all available AGiXT agents |
| `agixt_get_agent_settings` | Get settings for a specific agent |
| `agixt_create_agent` | Create a new AGiXT agent |
| `agixt_delete_agent` | Delete an existing agent |
| `agixt_get_agent_commands` | List available commands for an agent |

### Chat Tools

| Tool | Description |
|------|-------------|
| `agixt_chat` | Send a message to an AGiXT agent and get a response |
| `agixt_inference` | Run inference with advanced options (memories, prompts, etc.) |

### Chain Tools

| Tool | Description |
|------|-------------|
| `agixt_list_chains` | List all available chains |
| `agixt_get_chain` | Get details of a specific chain |
| `agixt_run_chain` | Execute a chain with arguments |
| `agixt_create_chain` | Create a new chain |

### Memory Tools

| Tool | Description |
|------|-------------|
| `agixt_query_memories` | Query agent memories with semantic search |
| `agixt_add_memory` | Add a new memory to an agent's knowledge base |
| `agixt_learn_url` | Have the agent learn from a URL |
| `agixt_learn_file` | Have the agent learn from file content |

### Conversation Tools

| Tool | Description |
|------|-------------|
| `agixt_list_conversations` | List all conversations |
| `agixt_get_conversation` | Get conversation history |
| `agixt_create_conversation` | Create a new conversation |
| `agixt_delete_conversation` | Delete a conversation |

### Command Tools

| Tool | Description |
|------|-------------|
| `agixt_execute_command` | Execute a specific agent command |
| `agixt_list_commands` | List all available commands for an agent |

## Usage Examples

### Basic Chat

```
Claude: Use the agixt_chat tool to ask the agent "What is the weather like today?"
```

### Running a Chain

```
Claude: Use agixt_run_chain to execute the "Smart Instruct" chain with the input "Create a Python function to sort a list"
```

### Querying Memories

```
Claude: Use agixt_query_memories to find any information about "machine learning" in the agent's memory
```

### Learning from URLs

```
Claude: Use agixt_learn_url to have the agent learn from "https://example.com/documentation"
```

## Development

### Running Tests

```bash
pytest tests/
```

### Building

```bash
pip install build
python -m build
```

## Architecture

The MCP server connects to AGiXT's REST API and exposes its functionality through the Model Context Protocol:

```
Claude Code <-> MCP Server <-> AGiXT API <-> AGiXT Agents
```

The server translates MCP tool calls into AGiXT API requests and returns the results in a format Claude can understand.

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please see the main AGiXT repository for contribution guidelines.
