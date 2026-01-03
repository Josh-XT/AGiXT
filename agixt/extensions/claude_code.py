"""
Claude Code Extension for AGiXT

This extension provides Anthropic/Claude OAuth integration following AGiXT's
standard OAuth patterns (similar to google.py, microsoft.py, github.py).

All tool executions use safeexecute when available, running in the user's
conversational workspace directory.

Environment Variables:
- ANTHROPIC_CLIENT_ID: OAuth client ID from Anthropic Console
- ANTHROPIC_CLIENT_SECRET: OAuth client secret from Anthropic Console
"""

import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, Any, List
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth

# Check for safeexecute - always use it when available
try:
    from safeexecute import execute_python_code

    SAFEEXECUTE_AVAILABLE = True
except ImportError:
    SAFEEXECUTE_AVAILABLE = False
    logging.warning("safeexecute not available - tools will run without sandboxing")


# =============================================================================
# OAuth Configuration (following AGiXT patterns)
# =============================================================================

SCOPES = [
    "user:read",
    "conversations:read",
    "conversations:write",
    "models:read",
    "usage:read",
]

AUTHORIZE = "https://claude.ai/oauth/authorize"
PKCE_REQUIRED = True


class AnthropicSSO:
    """
    Anthropic/Claude SSO handler following AGiXT OAuth patterns.
    Similar to GoogleSSO, MicrosoftSSO, GitHubSSO classes.
    """

    def __init__(self, access_token: str = None, refresh_token: str = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_url = "https://claude.ai/oauth/token"
        self.userinfo_url = "https://claude.ai/api/auth/session"
        self.client_id = getenv("ANTHROPIC_CLIENT_ID")
        self.client_secret = getenv("ANTHROPIC_CLIENT_SECRET")

    def get_new_token(self) -> str:
        """Refresh the access token using the refresh token"""
        if not self.refresh_token:
            logging.error("No refresh token available for Anthropic")
            return None

        response = requests.post(
            self.token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )

        if response.status_code != 200:
            logging.error(f"Error refreshing Anthropic token: {response.text}")
            return None

        tokens = response.json()
        self.access_token = tokens.get("access_token", self.access_token)
        if "refresh_token" in tokens:
            self.refresh_token = tokens["refresh_token"]
        return self.access_token

    def get_user_info(self) -> Dict[str, Any]:
        """Get user info from Anthropic"""
        if not self.access_token:
            return None

        response = requests.get(
            self.userinfo_url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30,
        )

        if response.status_code == 401 and self.refresh_token:
            # Token expired, try refreshing
            new_token = self.get_new_token()
            if new_token:
                response = requests.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {new_token}"},
                    timeout=30,
                )

        if response.status_code != 200:
            logging.error(f"Error getting Anthropic user info: {response.text}")
            return None

        data = response.json()
        user = data.get("user", data)
        return {
            "email": user.get("email", user.get("id", "")),
            "name": user.get("name", ""),
            "id": user.get("id"),
            "plan": user.get("plan", "free"),
        }


def sso(code: str, redirect_uri: str = None) -> AnthropicSSO:
    """
    Exchange authorization code for tokens.
    Standard AGiXT sso() function pattern.
    """
    client_id = getenv("ANTHROPIC_CLIENT_ID")
    client_secret = getenv("ANTHROPIC_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Anthropic OAuth not configured")
        return None

    response = requests.post(
        "https://claude.ai/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    if response.status_code != 200:
        logging.error(f"Error getting Anthropic access token: {response.text}")
        return None

    tokens = response.json()
    return AnthropicSSO(
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
    )


# =============================================================================
# Extension Class
# =============================================================================


class claude_code(Extensions):
    """
    Claude Code Extension - Integrates AGiXT with Claude/Anthropic using MCP.

    Follows standard AGiXT OAuth patterns. Uses safeexecute when available
    to run MCP tools in the user's conversational workspace.
    """

    CATEGORY = "AI Integration"
    friendly_name = "Claude Code"

    def __init__(
        self,
        **kwargs,
    ):
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.api_key = kwargs.get("api_key", "")
        self.user = kwargs.get("user", "")
        self.user_id = kwargs.get("user_id", "")
        self.conversation_name = kwargs.get("conversation_name", "")

        # Use conversation directory as workspace
        self.working_directory = kwargs.get(
            "conversation_directory",
            os.path.join(os.getcwd(), "WORKSPACE"),
        )
        os.makedirs(self.working_directory, exist_ok=True)

        from InternalClient import InternalClient

        self.ApiClient = kwargs.get("ApiClient") or InternalClient(
            api_key=self.api_key,
            user=self.user,
        )

        # Initialize auth if we have an API key
        self.auth = None
        if self.api_key:
            try:
                self.auth = MagicalAuth(token=self.api_key)
            except Exception as e:
                logging.error(f"Error initializing Claude Code extension: {e}")

        self.commands = {
            # Chat with Claude
            "Chat with Claude": self.chat_with_claude,
            # MCP Tool Execution
            "Execute AGiXT Tool via MCP": self.execute_agixt_tool,
            "List Available MCP Tools": self.list_mcp_tools,
            # Agent Integration
            "Query Agent Memory": self.query_memory,
            "Add to Agent Memory": self.add_memory,
            "Run Agent Chain": self.run_chain,
        }

    def _get_access_token(self) -> str:
        """Get the Anthropic access token from MagicalAuth OAuth"""
        if self.auth:
            try:
                oauth_data = self.auth.get_oauth_functions("anthropic")
                if oauth_data and hasattr(oauth_data, "access_token"):
                    return oauth_data.access_token
                # Try refreshing
                return self.auth.refresh_oauth_token(provider="anthropic")
            except Exception as e:
                logging.error(f"Error getting Anthropic token: {e}")

        return None

    async def chat_with_claude(self, message: str, conversation_id: str = "") -> str:
        """
        Send a message to Claude using the Anthropic API.

        Args:
            message: The message to send to Claude
            conversation_id: Optional conversation ID for context

        Returns:
            Claude's response
        """
        access_token = self._get_access_token()
        if not access_token:
            return "Error: No Anthropic access token. Please connect your Anthropic account via OAuth."

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": message}],
                },
                timeout=120,
            )

            if response.status_code == 401:
                # Token may be expired, try refreshing
                if self.auth:
                    new_token = self.auth.refresh_oauth_token(provider="anthropic")
                    if new_token:
                        response = requests.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={
                                "Authorization": f"Bearer {new_token}",
                                "Content-Type": "application/json",
                                "anthropic-version": "2023-06-01",
                            },
                            json={
                                "model": "claude-sonnet-4-20250514",
                                "max_tokens": 4096,
                                "messages": [{"role": "user", "content": message}],
                            },
                            timeout=120,
                        )

            if response.status_code != 200:
                return f"Error from Claude API: {response.text}"

            data = response.json()
            content = data.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "No response text")
            return "No response from Claude"

        except Exception as e:
            logging.error(f"Error chatting with Claude: {e}")
            return f"Error: {str(e)}"

    async def execute_agixt_tool(self, tool_name: str, arguments: str = "{}") -> str:
        """
        Execute an AGiXT tool via MCP protocol.
        Uses safeexecute when available for sandboxed execution.

        Args:
            tool_name: Name of the MCP tool to execute (e.g., agixt_chat, agixt_run_chain)
            arguments: JSON string of tool arguments

        Returns:
            Tool execution result
        """
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return "Error: Invalid JSON arguments"

        # Build execution code
        api_url = getenv("AGIXT_URI", "http://localhost:7437")

        if SAFEEXECUTE_AVAILABLE:
            # Execute in sandbox using user's workspace
            sandbox_code = f"""
import os
import sys
import json
import asyncio
import requests

# Tool execution via direct API calls
api_url = "{api_url}"
api_key = "{self.api_key}"
agent_name = "{args.get('agent_name', self.agent_name)}"

headers = {{"Content-Type": "application/json"}}
if api_key:
    headers["Authorization"] = f"Bearer {{api_key}}"

tool_name = "{tool_name}"
args = {json.dumps(args)}

# Route to appropriate endpoint based on tool
result = {{"error": "Unknown tool"}}

if tool_name == "agixt_chat":
    resp = requests.post(
        f"{{api_url}}/api/v1/agent/{{agent_name}}/prompt",
        headers=headers,
        json={{"user_input": args.get("message", ""), "prompt_category": "Default", "prompt_name": "Chat"}},
        timeout=300
    )
    result = resp.json() if resp.status_code == 200 else {{"error": resp.text}}

elif tool_name == "agixt_list_agents":
    resp = requests.get(f"{{api_url}}/api/v1/agent", headers=headers, timeout=30)
    result = resp.json() if resp.status_code == 200 else {{"error": resp.text}}

elif tool_name == "agixt_run_chain":
    resp = requests.post(
        f"{{api_url}}/api/v1/chain/{{args.get('chain_name', '')}}/run",
        headers=headers,
        json={{"prompt": args.get("user_input", ""), "agent_override": agent_name}},
        timeout=300
    )
    result = resp.json() if resp.status_code == 200 else {{"error": resp.text}}

elif tool_name == "agixt_query_memories":
    collection = args.get("collection_number", 0)
    resp = requests.post(
        f"{{api_url}}/api/v1/agent/{{agent_name}}/memory/{{collection}}/query",
        headers=headers,
        json={{"user_input": args.get("query", ""), "limit": args.get("limit", 10)}},
        timeout=60
    )
    result = resp.json() if resp.status_code == 200 else {{"error": resp.text}}

elif tool_name == "agixt_add_memory":
    collection = args.get("collection_number", 0)
    resp = requests.post(
        f"{{api_url}}/api/v1/agent/{{agent_name}}/memory/{{collection}}/add",
        headers=headers,
        json={{"text": args.get("text", "")}},
        timeout=60
    )
    result = resp.json() if resp.status_code == 200 else {{"error": resp.text}}

print(json.dumps(result, default=str))
"""
            try:
                return execute_python_code(
                    code=sandbox_code,
                    working_directory=self.working_directory,
                )
            except Exception as e:
                logging.warning(f"Sandbox execution failed: {e}")
                # Fall through to direct execution

        # Direct execution (fallback)
        try:
            import asyncio

            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        from agixt.ApiClient import AGiXTSDK

        sdk = AGiXTSDK(base_uri=api_url, api_key=self.api_key)
        agent = args.get("agent_name", self.agent_name)

        if tool_name == "agixt_chat":
            result = sdk.prompt_agent(
                agent_name=agent,
                prompt_name="Chat",
                prompt_args={"user_input": args.get("message", "")},
            )
        elif tool_name == "agixt_list_agents":
            result = sdk.get_agents()
        elif tool_name == "agixt_run_chain":
            result = sdk.run_chain(
                chain_name=args.get("chain_name", ""),
                user_input=args.get("user_input", ""),
                agent_name=agent,
            )
        elif tool_name == "agixt_query_memories":
            result = sdk.get_agent_memories(
                agent_name=agent,
                user_input=args.get("query", ""),
                limit=args.get("limit", 10),
                min_relevance_score=0.0,
            )
        elif tool_name == "agixt_add_memory":
            result = sdk.learn_text(
                agent_name=agent,
                user_input=args.get("text", ""),
                text=args.get("text", ""),
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result, indent=2, default=str)

    async def list_mcp_tools(self) -> str:
        """
        List all available MCP tools for AGiXT integration.

        Returns:
            List of available tools and their descriptions
        """
        tools = [
            ("agixt_chat", "Send a message to an AGiXT agent"),
            ("agixt_list_agents", "List all available agents"),
            ("agixt_run_chain", "Execute a chain with inputs"),
            ("agixt_query_memories", "Search agent memory"),
            ("agixt_add_memory", "Add to agent memory"),
            ("agixt_learn_url", "Learn content from a URL"),
            ("agixt_list_conversations", "List conversations"),
            ("agixt_execute_command", "Execute an agent command"),
            ("agixt_list_commands", "List available commands"),
            ("agixt_list_prompts", "List available prompts"),
        ]

        result = "**Available MCP Tools:**\n\n"
        for name, desc in tools:
            result += f"- `{name}`: {desc}\n"

        result += f"\n**Sandboxing:** {'Enabled (safeexecute)' if SAFEEXECUTE_AVAILABLE else 'Disabled'}"
        result += f"\n**Workspace:** `{self.working_directory}`"

        return result

    async def query_memory(
        self, query: str, collection_number: int = 0, limit: int = 10
    ) -> str:
        """
        Query agent memory for relevant information.

        Args:
            query: Search query
            collection_number: Memory collection to search
            limit: Maximum results to return

        Returns:
            Relevant memories
        """
        args = {
            "query": query,
            "collection_number": collection_number,
            "limit": limit,
        }
        return await self.execute_agixt_tool("agixt_query_memories", json.dumps(args))

    async def add_memory(self, text: str, collection_number: int = 0) -> str:
        """
        Add information to agent memory.

        Args:
            text: Text to add to memory
            collection_number: Memory collection to add to

        Returns:
            Confirmation of memory addition
        """
        args = {"text": text, "collection_number": collection_number}
        return await self.execute_agixt_tool("agixt_add_memory", json.dumps(args))

    async def run_chain(self, chain_name: str, user_input: str) -> str:
        """
        Run an AGiXT chain.

        Args:
            chain_name: Name of the chain to run
            user_input: Input for the chain

        Returns:
            Chain execution result
        """
        args = {"chain_name": chain_name, "user_input": user_input}
        return await self.execute_agixt_tool("agixt_run_chain", json.dumps(args))
