# Claude Code MCP Integration for AGiXT

This module provides two approaches for integrating AGiXT with Claude Code via MCP (Model Context Protocol).

## Quick Start

### Option 1: MCP Hub (Recommended for Teams)

The MCP Hub provides centralized session management with sandboxed execution:

1. Enable the `claude_code_hub` extension for your agent
2. Run "Create MCP Session" to get a session token
3. Add the provided config to Claude Code

### Option 2: Standalone MCP Server

For direct control, configure Claude Code to run the standalone server:

```json
{
  "mcpServers": {
    "agixt": {
      "command": "python",
      "args": ["-m", "agixt.extensions.claude_code_mcp_server"],
      "env": {
        "AGIXT_API_URL": "http://localhost:7437",
        "AGIXT_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Overview

The Claude Code integration exposes AGiXT's capabilities through MCP, allowing Claude Code to:

- Chat with AGiXT agents
- Execute chains and workflows
- Query and add to agent memories
- Manage conversations
- Execute agent commands
- Learn from URLs and documents
- And more...

## Files in This Integration

| File | Purpose |
|------|---------|
| `claude_code_hub.py` | MCP Hub extension with session management & sandboxing |
| `claude_code.py` | Standalone MCP server extension |
| `claude_code_mcp_server.py` | The MCP server implementation |
| `claude_code_mcp_tools.py` | Tool definitions and execution logic |
| `endpoints/mcp_hub.py` | REST API endpoints for hub connections |

## Installation

The extensions are automatically available when AGiXT is running. Dependencies:

```bash
pip install mcp aiohttp
# For sandboxed execution (optional):
pip install safeexecute
```

## MCP Hub Features (claude_code_hub.py)

- **Session-based auth**: Each user gets unique, time-limited tokens
- **Sandboxed execution**: Tools run in isolated Docker containers via `safeexecute`  
- **Audit logging**: All executions tracked in database
- **Multi-tenant**: Proper user isolation
- **Auto-cleanup**: Expired sessions invalidated automatically

### Hub Commands

| Command | Description |
|---------|-------------|
| Create MCP Session | Generate a new session token |
| List MCP Sessions | View all active sessions |
| Revoke MCP Session | Invalidate a session |
| Get MCP Hub Status | Check hub stats |

### Hub Configuration

```python
claude_code_hub(
    MCP_HUB_ENABLED=True,           # Enable/disable
    MCP_SESSION_TIMEOUT_HOURS=24,   # Session expiration
    MCP_MAX_SESSIONS_PER_USER=5,    # Limit per user  
    MCP_SANDBOX_ENABLED=True,       # Use safeexecute
    MCP_LOG_EXECUTIONS=True,        # Track executions
)
```

## Standalone Server Configuration

### Agent Settings

| Setting | Description | Default |
|---------|-------------|---------|
| MCP_SERVER_HOST | Host for the MCP server | localhost |
| MCP_SERVER_PORT | Port for the MCP server | 3100 |

### Claude Code Configuration

Add this to your Claude Desktop/Code configuration file:

**Location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`  
- Linux: `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "agixt": {
      "command": "python",
      "args": ["/path/to/AGiXT/agixt/extensions/claude_code_mcp_server.py"],
      "env": {
        "AGIXT_API_URL": "http://localhost:7437",
        "AGIXT_API_KEY": "your-api-key",
        "AGIXT_AGENT_NAME": "gpt4"
      }
    }
  }
}
```

## Available Commands

### Extension Commands

| Command | Description |
|---------|-------------|
| Start MCP Server | Start the MCP server subprocess |
| Stop MCP Server | Stop the running MCP server |
| Get MCP Server Status | Check if the server is running |
| Get MCP Configuration | Get the Claude Code config JSON |

### MCP Tools (Available to Claude)

**Agent Tools:**
- `agixt_list_agents` - List all available agents
- `agixt_get_agent` - Get agent configuration
- `agixt_create_agent` - Create a new agent
- `agixt_delete_agent` - Delete an agent
- `agixt_get_agent_commands` - List agent commands

**Chat Tools:**
- `agixt_chat` - Send messages to agents
- `agixt_inference` - Advanced inference with prompts

**Chain Tools:**
- `agixt_list_chains` - List available chains
- `agixt_get_chain` - Get chain details
- `agixt_run_chain` - Execute a chain

**Memory Tools:**
- `agixt_query_memories` - Semantic search memories
- `agixt_add_memory` - Add knowledge
- `agixt_learn_url` - Learn from URLs

**Conversation Tools:**
- `agixt_list_conversations` - List conversations
- `agixt_get_conversation` - Get conversation history
- `agixt_delete_conversation` - Delete conversation

**Other Tools:**
- `agixt_execute_command` - Run agent commands
- `agixt_list_prompts` - List prompt templates
- `agixt_get_prompt` - Get prompt content
- `agixt_list_providers` - List AI providers

## Usage Examples

### From Claude Code

Once configured, you can ask Claude to use AGiXT:

```
"Use agixt_chat to ask the agent about machine learning"

"Run the Smart Instruct chain with the input 'Create a Python REST API'"

"Query the agent's memories for information about our project requirements"

"Have the agent learn from this documentation URL: https://example.com/docs"
```

### From AGiXT Agent

You can also use the extension commands directly from an AGiXT agent:

```
"Get the MCP configuration for Claude Code"

"Check the MCP server status"
```

## Requirements

- Python 3.10+
- AGiXT running and accessible
- MCP package: `pip install mcp aiohttp`

## Troubleshooting

### Server won't start

1. Check that MCP is installed: `pip install mcp aiohttp`
2. Verify AGiXT is running and accessible
3. Check the server logs for errors

### Claude can't connect

1. Verify the configuration file path is correct
2. Check that the Python path is correct in the config
3. Ensure environment variables are set correctly
4. Restart Claude Code after configuration changes

### Tools not working

1. Verify your API key is valid
2. Check that the agent exists and is configured
3. Review the AGiXT logs for API errors

## Architecture

```
┌─────────────┐     stdio     ┌──────────────┐     HTTP     ┌─────────┐
│ Claude Code │ ◄───────────► │  MCP Server  │ ◄──────────► │  AGiXT  │
└─────────────┘               └──────────────┘              └─────────┘
                                    │
                              MCP Protocol
                              (JSON-RPC 2.0)
```

The MCP server acts as a bridge between Claude Code and AGiXT:
1. Claude Code discovers available tools via MCP
2. When Claude calls a tool, the MCP server translates it to AGiXT API calls
3. Results are returned to Claude in the MCP format

## License

MIT License - See the main AGiXT repository for details.
