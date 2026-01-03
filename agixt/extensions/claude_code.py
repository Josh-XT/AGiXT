"""
Claude Code MCP Server Extension for AGiXT

This extension provides an MCP (Model Context Protocol) server that allows
Claude Code to interact with AGiXT agents, chains, conversations, and memories.

The MCP server runs as a subprocess and communicates via stdio, exposing AGiXT's
capabilities as MCP tools that Claude can use.

Required environment variables:
- MCP_SERVER_PORT: Port for the MCP server (default: 3100)

Required packages (install if missing):
- pip install mcp aiohttp
"""

import os
import sys
import json
import asyncio
import logging
import threading
import subprocess
from typing import Optional, Dict, Any, List
from Extensions import Extensions
from Globals import getenv, install_package_if_missing

# Install dependencies if missing
install_package_if_missing("mcp")
install_package_if_missing("aiohttp")

# Check if mcp package is available
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logging.warning(
        "MCP package not installed. Install with: pip install mcp aiohttp"
    )


class claude_code(Extensions):
    """
    The Claude Code extension provides an MCP (Model Context Protocol) server
    that enables Claude Code to interact with AGiXT. This allows Claude to use
    AGiXT agents, execute chains, manage memories, and more through a standardized
    protocol interface.
    
    When enabled, this extension starts an MCP server that exposes AGiXT functionality
    as tools that Claude Code can discover and use.
    """

    CATEGORY = "AI Integration"
    friendly_name = "Claude Code MCP Server"

    def __init__(
        self,
        MCP_SERVER_HOST: str = "localhost",
        MCP_SERVER_PORT: int = 3100,
        **kwargs,
    ):
        self.MCP_SERVER_HOST = MCP_SERVER_HOST
        self.MCP_SERVER_PORT = int(MCP_SERVER_PORT)
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.api_key = kwargs.get("api_key", "")
        self.user = kwargs.get("user", "")
        self.conversation_name = kwargs.get("conversation_name", "")
        self.conversation_id = kwargs.get("conversation_id", "")
        
        # Import ApiClient for internal operations
        from InternalClient import InternalClient
        self.ApiClient = kwargs.get("ApiClient") or InternalClient(
            api_key=self.api_key,
            user=self.user,
        )
        
        self.commands = {
            "Start MCP Server": self.start_mcp_server,
            "Stop MCP Server": self.stop_mcp_server,
            "Get MCP Server Status": self.get_mcp_server_status,
            "Get MCP Configuration": self.get_mcp_configuration,
        }
        
        self._server_process: Optional[subprocess.Popen] = None
        self._server_thread: Optional[threading.Thread] = None

    async def start_mcp_server(self) -> str:
        """
        Start the MCP server for Claude Code integration.
        
        Returns:
            str: Status message with connection information
        """
        if not MCP_AVAILABLE:
            return "Error: MCP package not installed. Install with: pip install mcp"
        
        if self._server_process and self._server_process.poll() is None:
            return f"MCP server is already running on port {self.MCP_SERVER_PORT}"
        
        try:
            # Start the MCP server as a subprocess
            server_script = os.path.join(os.path.dirname(__file__), "claude_code_mcp_server.py")
            
            env = os.environ.copy()
            env["AGIXT_API_KEY"] = self.api_key
            env["AGIXT_AGENT_NAME"] = self.agent_name
            env["AGIXT_USER"] = self.user
            env["MCP_SERVER_PORT"] = str(self.MCP_SERVER_PORT)
            
            self._server_process = subprocess.Popen(
                [sys.executable, server_script],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            return f"""MCP Server started successfully!

To connect Claude Code, add this to your Claude configuration:

```json
{{
  "mcpServers": {{
    "agixt": {{
      "command": "python",
      "args": ["{server_script}"],
      "env": {{
        "AGIXT_API_URL": "{getenv('AGIXT_URI')}",
        "AGIXT_API_KEY": "{self.api_key}",
        "AGIXT_AGENT_NAME": "{self.agent_name}"
      }}
    }}
  }}
}}
```

Server PID: {self._server_process.pid}
"""
        except Exception as e:
            return f"Error starting MCP server: {str(e)}"

    async def stop_mcp_server(self) -> str:
        """
        Stop the running MCP server.
        
        Returns:
            str: Status message
        """
        if not self._server_process:
            return "MCP server is not running"
        
        if self._server_process.poll() is not None:
            return "MCP server has already stopped"
        
        try:
            self._server_process.terminate()
            self._server_process.wait(timeout=5)
            self._server_process = None
            return "MCP server stopped successfully"
        except subprocess.TimeoutExpired:
            self._server_process.kill()
            self._server_process = None
            return "MCP server forcefully stopped"
        except Exception as e:
            return f"Error stopping MCP server: {str(e)}"

    async def get_mcp_server_status(self) -> str:
        """
        Get the current status of the MCP server.
        
        Returns:
            str: Server status information
        """
        if not self._server_process:
            return "MCP server is not running"
        
        poll_result = self._server_process.poll()
        if poll_result is None:
            return f"MCP server is running (PID: {self._server_process.pid})"
        else:
            return f"MCP server has stopped (exit code: {poll_result})"

    async def get_mcp_configuration(self) -> str:
        """
        Get the MCP configuration for Claude Code.
        
        Returns:
            str: JSON configuration for Claude Code
        """
        server_script = os.path.join(os.path.dirname(__file__), "claude_code_mcp_server.py")
        
        config = {
            "mcpServers": {
                "agixt": {
                    "command": "python",
                    "args": [server_script],
                    "env": {
                        "AGIXT_API_URL": getenv("AGIXT_URI"),
                        "AGIXT_API_KEY": "<your-api-key>",
                        "AGIXT_AGENT_NAME": self.agent_name,
                    }
                }
            }
        }
        
        return f"""Claude Code MCP Configuration:

Add this to your Claude Desktop/Code configuration file:
- macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
- Windows: %APPDATA%\\Claude\\claude_desktop_config.json
- Linux: ~/.config/claude/claude_desktop_config.json

```json
{json.dumps(config, indent=2)}
```

Available Tools:
- agixt_chat: Chat with AGiXT agents
- agixt_inference: Advanced inference with prompts
- agixt_list_agents: List available agents
- agixt_list_chains: List available chains
- agixt_run_chain: Execute automation chains
- agixt_query_memories: Search agent memories
- agixt_add_memory: Add knowledge to agents
- agixt_learn_url: Learn from URLs
- agixt_execute_command: Run agent commands
- And more...

For the full list of tools, see the extension documentation.
"""
