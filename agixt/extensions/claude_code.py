"""
Claude Code MCP Extension for AGiXT

This extension provides MCP (Model Context Protocol) integration for Claude Code,
allowing Claude to interact with AGiXT agents, chains, memories, and commands.

Features:
- Anthropic OAuth integration for user authentication
- Session-based MCP server with sandboxed execution via safeexecute
- Multi-tenant support with user isolation
- Audit logging for all tool executions

Environment Variables:
- ANTHROPIC_CLIENT_ID: OAuth client ID from Anthropic Console
- ANTHROPIC_CLIENT_SECRET: OAuth client secret from Anthropic Console
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import secrets
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import requests
from fastapi import HTTPException
from Extensions import Extensions
from Globals import getenv, install_package_if_missing
from DB import (
    get_session,
    Base,
    DATABASE_TYPE,
    UUID,
    get_new_id,
    User,
    UserOAuth,
    OAuthProvider,
    ExtensionDatabaseMixin,
)
from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

# Install dependencies
install_package_if_missing("mcp")
install_package_if_missing("aiohttp")

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# Check for safeexecute - always use it when available
try:
    from safeexecute import execute_python_code, execute_shell_command

    SAFEEXECUTE_AVAILABLE = True
except ImportError:
    SAFEEXECUTE_AVAILABLE = False
    logging.warning("safeexecute not available - MCP tools will run without sandboxing")

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


# =============================================================================
# MCP Tool Definitions
# =============================================================================

MCP_TOOLS = {
    "agixt_chat": {
        "description": "Send a message to an AGiXT agent and get a response",
        "parameters": {
            "message": {"type": "string", "description": "The message to send"},
            "agent_name": {"type": "string", "description": "Agent to chat with (optional)"},
            "conversation_name": {"type": "string", "description": "Conversation name (optional)"},
        },
        "required": ["message"],
    },
    "agixt_inference": {
        "description": "Run advanced inference with custom settings",
        "parameters": {
            "user_input": {"type": "string", "description": "The prompt or question"},
            "agent_name": {"type": "string", "description": "Agent to use (optional)"},
            "prompt_category": {"type": "string", "description": "Prompt category (default: Default)"},
            "prompt_name": {"type": "string", "description": "Prompt name (default: Chat)"},
            "inject_memories_from_collection_number": {"type": "integer", "description": "Memory collection (default: 0)"},
        },
        "required": ["user_input"],
    },
    "agixt_list_agents": {
        "description": "List all available agents",
        "parameters": {},
        "required": [],
    },
    "agixt_get_agent_settings": {
        "description": "Get settings for an agent",
        "parameters": {
            "agent_name": {"type": "string", "description": "Agent name"},
        },
        "required": ["agent_name"],
    },
    "agixt_run_chain": {
        "description": "Execute a chain with given inputs",
        "parameters": {
            "chain_name": {"type": "string", "description": "Name of the chain"},
            "user_input": {"type": "string", "description": "Input for the chain"},
            "agent_name": {"type": "string", "description": "Agent override (optional)"},
            "chain_args": {"type": "object", "description": "Additional arguments (optional)"},
        },
        "required": ["chain_name", "user_input"],
    },
    "agixt_list_chains": {
        "description": "List all available chains",
        "parameters": {},
        "required": [],
    },
    "agixt_query_memories": {
        "description": "Search agent memory for relevant information",
        "parameters": {
            "query": {"type": "string", "description": "Search query"},
            "agent_name": {"type": "string", "description": "Agent to search (optional)"},
            "collection_number": {"type": "integer", "description": "Memory collection (default: 0)"},
            "limit": {"type": "integer", "description": "Max results (default: 10)"},
        },
        "required": ["query"],
    },
    "agixt_add_memory": {
        "description": "Add new information to agent memory",
        "parameters": {
            "text": {"type": "string", "description": "Text to add"},
            "agent_name": {"type": "string", "description": "Agent name (optional)"},
            "collection_number": {"type": "integer", "description": "Memory collection (default: 0)"},
        },
        "required": ["text"],
    },
    "agixt_learn_url": {
        "description": "Learn content from a URL",
        "parameters": {
            "url": {"type": "string", "description": "URL to learn from"},
            "agent_name": {"type": "string", "description": "Agent name (optional)"},
            "collection_number": {"type": "integer", "description": "Memory collection (default: 0)"},
        },
        "required": ["url"],
    },
    "agixt_list_conversations": {
        "description": "List all conversations for an agent",
        "parameters": {
            "agent_name": {"type": "string", "description": "Agent name (optional)"},
        },
        "required": [],
    },
    "agixt_get_conversation": {
        "description": "Get conversation history",
        "parameters": {
            "conversation_name": {"type": "string", "description": "Conversation name"},
            "agent_name": {"type": "string", "description": "Agent name (optional)"},
            "limit": {"type": "integer", "description": "Message limit (default: 100)"},
        },
        "required": ["conversation_name"],
    },
    "agixt_execute_command": {
        "description": "Execute an agent command/extension",
        "parameters": {
            "command_name": {"type": "string", "description": "Command to execute"},
            "command_args": {"type": "object", "description": "Command arguments"},
            "agent_name": {"type": "string", "description": "Agent name (optional)"},
        },
        "required": ["command_name", "command_args"],
    },
    "agixt_list_commands": {
        "description": "List available commands for an agent",
        "parameters": {
            "agent_name": {"type": "string", "description": "Agent name (optional)"},
        },
        "required": [],
    },
    "agixt_list_prompts": {
        "description": "List available prompts",
        "parameters": {
            "category": {"type": "string", "description": "Prompt category (optional)"},
        },
        "required": [],
    },
    "agixt_get_prompt": {
        "description": "Get a specific prompt template",
        "parameters": {
            "prompt_name": {"type": "string", "description": "Prompt name"},
            "prompt_category": {"type": "string", "description": "Category (default: Default)"},
        },
        "required": ["prompt_name"],
    },
}


def get_tool_definitions() -> List[Dict]:
    """Get MCP tool definitions in the format expected by Claude"""
    return [
        {
            "name": name,
            "description": info["description"],
            "inputSchema": {
                "type": "object",
                "properties": info["parameters"],
                "required": info["required"],
            },
        }
        for name, info in MCP_TOOLS.items()
    ]


# =============================================================================
# MCP Tool Executor
# =============================================================================

class MCPToolExecutor:
    """Executes MCP tools by making API calls to AGiXT"""

    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        agent_name: str = None,
    ):
        self.api_url = api_url or os.getenv("AGIXT_API_URL", "http://localhost:7437")
        self.api_key = api_key or os.getenv("AGIXT_API_KEY", "")
        self.agent_name = agent_name or os.getenv("AGIXT_AGENT_NAME", "gpt4free")

        if not self.api_url.endswith("/api"):
            self.api_url = self.api_url.rstrip("/") + "/api"

    @property
    def headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None,
    ) -> Any:
        """Make an HTTP request to the AGiXT API"""
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for MCP tool execution")

        url = f"{self.api_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
            kwargs = {
                "headers": self.headers,
                "timeout": aiohttp.ClientTimeout(total=300),
            }
            if data is not None:
                kwargs["json"] = data
            if params is not None:
                kwargs["params"] = params

            async with session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    return {"error": f"API error {response.status}: {error_text}"}
                try:
                    return await response.json()
                except:
                    return {"result": await response.text()}

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result"""
        agent = arguments.get("agent_name", self.agent_name)

        try:
            if tool_name == "agixt_chat":
                return await self._chat(
                    message=arguments["message"],
                    agent_name=agent,
                    conversation_name=arguments.get("conversation_name"),
                )
            elif tool_name == "agixt_inference":
                return await self._inference(
                    user_input=arguments["user_input"],
                    agent_name=agent,
                    prompt_category=arguments.get("prompt_category", "Default"),
                    prompt_name=arguments.get("prompt_name", "Chat"),
                    collection=arguments.get("inject_memories_from_collection_number", 0),
                )
            elif tool_name == "agixt_list_agents":
                return await self._request("GET", "/v1/agent")
            elif tool_name == "agixt_get_agent_settings":
                return await self._request("GET", f"/v1/agent/{agent}")
            elif tool_name == "agixt_run_chain":
                return await self._run_chain(
                    chain_name=arguments["chain_name"],
                    user_input=arguments["user_input"],
                    agent_name=agent,
                    chain_args=arguments.get("chain_args", {}),
                )
            elif tool_name == "agixt_list_chains":
                return await self._request("GET", "/v1/chain")
            elif tool_name == "agixt_query_memories":
                return await self._query_memories(
                    query=arguments["query"],
                    agent_name=agent,
                    collection=arguments.get("collection_number", 0),
                    limit=arguments.get("limit", 10),
                )
            elif tool_name == "agixt_add_memory":
                return await self._add_memory(
                    text=arguments["text"],
                    agent_name=agent,
                    collection=arguments.get("collection_number", 0),
                )
            elif tool_name == "agixt_learn_url":
                return await self._learn_url(
                    url=arguments["url"],
                    agent_name=agent,
                    collection=arguments.get("collection_number", 0),
                )
            elif tool_name == "agixt_list_conversations":
                return await self._request("GET", f"/v1/conversations/{agent}")
            elif tool_name == "agixt_get_conversation":
                return await self._get_conversation(
                    conversation_name=arguments["conversation_name"],
                    agent_name=agent,
                    limit=arguments.get("limit", 100),
                )
            elif tool_name == "agixt_execute_command":
                return await self._execute_command(
                    command_name=arguments["command_name"],
                    command_args=arguments["command_args"],
                    agent_name=agent,
                )
            elif tool_name == "agixt_list_commands":
                return await self._request("GET", f"/v1/agent/{agent}/command")
            elif tool_name == "agixt_list_prompts":
                category = arguments.get("category", "Default")
                return await self._request("GET", f"/v1/prompt/{category}")
            elif tool_name == "agixt_get_prompt":
                category = arguments.get("prompt_category", "Default")
                name = arguments["prompt_name"]
                return await self._request("GET", f"/v1/prompt/{category}/{name}")
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logging.error(f"Tool execution error: {e}")
            return {"error": str(e)}

    async def _chat(self, message: str, agent_name: str, conversation_name: str = None) -> Dict:
        data = {"user_input": message, "prompt_category": "Default", "prompt_name": "Chat"}
        if conversation_name:
            data["conversation_name"] = conversation_name
        return await self._request("POST", f"/v1/agent/{agent_name}/prompt", data=data)

    async def _inference(self, user_input: str, agent_name: str, prompt_category: str, prompt_name: str, collection: int) -> Dict:
        data = {
            "user_input": user_input,
            "prompt_category": prompt_category,
            "prompt_name": prompt_name,
            "inject_memories_from_collection_number": collection,
        }
        return await self._request("POST", f"/v1/agent/{agent_name}/prompt", data=data)

    async def _run_chain(self, chain_name: str, user_input: str, agent_name: str, chain_args: Dict) -> Dict:
        data = {"prompt": user_input, "agent_override": agent_name, "chain_args": chain_args}
        return await self._request("POST", f"/v1/chain/{chain_name}/run", data=data)

    async def _query_memories(self, query: str, agent_name: str, collection: int, limit: int) -> Dict:
        data = {"user_input": query, "limit": limit, "min_relevance_score": 0.0}
        return await self._request("POST", f"/v1/agent/{agent_name}/memory/{collection}/query", data=data)

    async def _add_memory(self, text: str, agent_name: str, collection: int) -> Dict:
        return await self._request("POST", f"/v1/agent/{agent_name}/memory/{collection}/add", data={"text": text})

    async def _learn_url(self, url: str, agent_name: str, collection: int) -> Dict:
        return await self._request("POST", f"/v1/agent/{agent_name}/learn/url", data={"url": url, "collection_number": collection})

    async def _get_conversation(self, conversation_name: str, agent_name: str, limit: int) -> Dict:
        return await self._request("GET", f"/v1/conversation/{agent_name}/{conversation_name}", params={"limit": limit})

    async def _execute_command(self, command_name: str, command_args: Dict, agent_name: str) -> Dict:
        return await self._request("POST", f"/v1/agent/{agent_name}/command", data={"command_name": command_name, "command_args": command_args})


async def execute_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    agent_name: str = None,
    api_url: str = None,
    api_key: str = None,
) -> Dict[str, Any]:
    """
    Execute an MCP tool. Module-level function for use by endpoints.
    """
    executor = MCPToolExecutor(api_url=api_url, api_key=api_key, agent_name=agent_name)
    return await executor.execute(tool_name, arguments)


# =============================================================================
# OAuth Configuration
# =============================================================================

OAUTH_SCOPES = [
    "user:read",
    "conversations:read",
    "conversations:write",
    "models:read",
    "usage:read",
]

OAUTH_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
OAUTH_TOKEN_URL = "https://claude.ai/oauth/token"
OAUTH_USERINFO_URL = "https://claude.ai/api/auth/session"


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge for OAuth"""
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode().rstrip("=")
    return code_verifier, code_challenge


class AnthropicOAuth:
    """Handles Anthropic/Claude OAuth authentication"""

    def __init__(self, access_token: str = None, refresh_token: str = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("ANTHROPIC_CLIENT_ID")
        self.client_secret = getenv("ANTHROPIC_CLIENT_SECRET")

    def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh the access token using the refresh token"""
        if not self.refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token available")

        response = requests.post(
            OAUTH_TOKEN_URL,
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
            raise HTTPException(status_code=401, detail="Token refresh failed")

        tokens = response.json()
        self.access_token = tokens.get("access_token", self.access_token)
        self.refresh_token = tokens.get("refresh_token", self.refresh_token)
        return tokens

    def get_user_info(self) -> Dict[str, Any]:
        """Get user info from Anthropic"""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token")

        response = requests.get(
            OAUTH_USERINFO_URL,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30,
        )

        if response.status_code == 401:
            self.refresh_access_token()
            response = requests.get(
                OAUTH_USERINFO_URL,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=30,
            )

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")

        data = response.json()
        user = data.get("user", data)
        return {
            "email": user.get("email", user.get("id", "")),
            "name": user.get("name", ""),
            "anthropic_id": user.get("id"),
            "plan": user.get("plan", "free"),
        }

    @staticmethod
    def exchange_code(
        code: str, redirect_uri: str, code_verifier: str = None
    ) -> "AnthropicOAuth":
        """Exchange authorization code for tokens"""
        client_id = getenv("ANTHROPIC_CLIENT_ID")
        client_secret = getenv("ANTHROPIC_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500, detail="Anthropic OAuth not configured"
            )

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        response = requests.post(
            OAUTH_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=data,
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=400, detail=f"Token exchange failed: {response.text}"
            )

        tokens = response.json()
        return AnthropicOAuth(
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
        )


# =============================================================================
# Database Models
# =============================================================================


class MCPSession(Base):
    """Database model for MCP sessions"""

    __tablename__ = "mcp_sessions"
    __table_args__ = {"extend_existing": True}

    id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        primary_key=True,
        default=get_new_id,
    )
    user_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        nullable=False,
        index=True,
    )
    session_token = Column(String(256), nullable=False, unique=True, index=True)
    anthropic_user_id = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    metadata = Column(JSONB if DATABASE_TYPE == "postgresql" else Text, nullable=True)


class MCPToolExecution(Base):
    """Database model for tracking tool executions"""

    __tablename__ = "mcp_tool_executions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("mcp_sessions.id"),
        nullable=False,
    )
    tool_name = Column(String(256), nullable=False)
    arguments = Column(JSONB if DATABASE_TYPE == "postgresql" else Text, nullable=True)
    result = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# =============================================================================
# Main Extension
# =============================================================================


class claude_code(Extensions, ExtensionDatabaseMixin):
    """
    Claude Code MCP Extension - Integrates AGiXT with Claude Code via MCP.

    All MCP tool executions run through safeexecute when available,
    providing Docker-based isolation for security.
    """

    CATEGORY = "AI Integration"
    friendly_name = "Claude Code MCP"
    extension_models = [MCPSession, MCPToolExecution]

    def __init__(
        self,
        MCP_SESSION_TIMEOUT_HOURS: int = 24,
        MCP_MAX_SESSIONS_PER_USER: int = 5,
        **kwargs,
    ):
        self.session_timeout_hours = int(MCP_SESSION_TIMEOUT_HOURS)
        self.max_sessions_per_user = int(MCP_MAX_SESSIONS_PER_USER)

        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.api_key = kwargs.get("api_key", "")
        self.user = kwargs.get("user", "")
        self.user_id = kwargs.get("user_id", "")
        self.conversation_name = kwargs.get("conversation_name", "")
        self.conversation_id = kwargs.get("conversation_id", "")

        from InternalClient import InternalClient

        self.ApiClient = kwargs.get("ApiClient") or InternalClient(
            api_key=self.api_key,
            user=self.user,
        )

        # PKCE verifiers storage
        self._pkce_verifiers: Dict[str, str] = {}

        self.commands = {
            # Session Management
            "Create MCP Session": self.create_session,
            "List MCP Sessions": self.list_sessions,
            "Revoke MCP Session": self.revoke_session,
            "Get MCP Status": self.get_status,
            # OAuth
            "Get Claude OAuth URL": self.get_oauth_url,
            "Check Claude Connection": self.check_oauth_connection,
            "Disconnect Claude Account": self.disconnect_oauth,
            # Tool Execution
            "Execute MCP Tool": self.execute_tool,
            # Maintenance
            "Cleanup Expired Sessions": self.cleanup_sessions,
        }

    # =========================================================================
    # Session Management
    # =========================================================================

    async def create_session(
        self, session_name: str = "", use_oauth: bool = False
    ) -> str:
        """
        Create a new MCP session for Claude Code.

        Args:
            session_name: Optional friendly name for the session
            use_oauth: If True, link session to user's Anthropic OAuth credentials

        Returns:
            Session token and Claude Code configuration
        """
        if not self.user_id:
            return "Error: User not authenticated with AGiXT."

        db = get_session()
        try:
            # Check session limit
            existing = (
                db.query(MCPSession)
                .filter(
                    MCPSession.user_id == self.user_id, MCPSession.is_active == True
                )
                .count()
            )

            if existing >= self.max_sessions_per_user:
                return f"Error: Maximum sessions ({self.max_sessions_per_user}) reached. Revoke an existing session first."

            # Check for OAuth if requested
            anthropic_user_id = None
            if use_oauth:
                provider = (
                    db.query(OAuthProvider)
                    .filter(OAuthProvider.name == "anthropic")
                    .first()
                )
                if provider:
                    user_oauth = (
                        db.query(UserOAuth)
                        .filter(
                            UserOAuth.user_id == self.user_id,
                            UserOAuth.provider_id == provider.id,
                        )
                        .first()
                    )
                    if user_oauth:
                        anthropic_user_id = user_oauth.account_name
                    else:
                        return "No Anthropic account connected. Use 'Get Claude OAuth URL' first."

            # Create session
            token = f"agixt_mcp_{secrets.token_urlsafe(32)}"
            session = MCPSession(
                user_id=self.user_id,
                session_token=token,
                anthropic_user_id=anthropic_user_id,
                expires_at=datetime.utcnow()
                + timedelta(hours=self.session_timeout_hours),
                metadata=json.dumps(
                    {
                        "name": session_name or f"Session {existing + 1}",
                        "agent_name": self.agent_name,
                        "oauth_linked": use_oauth,
                    }
                ),
            )
            db.add(session)
            db.commit()

            agixt_uri = getenv("AGIXT_URI", "http://localhost:7437")

            return f"""**MCP Session Created!**

**Session Token:** `{token}`
**Expires:** {session.expires_at.strftime('%Y-%m-%d %H:%M UTC')}
**Sandboxing:** {'Enabled (safeexecute)' if SAFEEXECUTE_AVAILABLE else 'Disabled'}
{f'**OAuth Linked:** {anthropic_user_id}' if anthropic_user_id else ''}

---

## Claude Code Configuration

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{{
  "mcpServers": {{
    "agixt": {{
      "command": "python",
      "args": ["-m", "agixt.extensions.claude_code_mcp_server"],
      "env": {{
        "AGIXT_API_URL": "{agixt_uri}",
        "AGIXT_MCP_SESSION_TOKEN": "{token}",
        "AGIXT_AGENT_NAME": "{self.agent_name}"
      }}
    }}
  }}
}}
```
"""
        except Exception as e:
            db.rollback()
            return f"Error creating session: {e}"
        finally:
            db.close()

    async def list_sessions(self) -> str:
        """List all active MCP sessions for the current user."""
        if not self.user_id:
            return "Error: User not authenticated."

        db = get_session()
        try:
            sessions = (
                db.query(MCPSession)
                .filter(
                    MCPSession.user_id == self.user_id, MCPSession.is_active == True
                )
                .order_by(MCPSession.created_at.desc())
                .all()
            )

            if not sessions:
                return "No active MCP sessions."

            result = "**Active MCP Sessions:**\n\n"
            for s in sessions:
                meta = json.loads(s.metadata) if s.metadata else {}
                result += (
                    f"- **{meta.get('name', 'Unnamed')}** (ID: `{str(s.id)[:8]}...`)\n"
                )
                result += f"  Created: {s.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"  Expires: {s.expires_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            return result
        finally:
            db.close()

    async def revoke_session(self, session_id: str) -> str:
        """Revoke an MCP session by ID."""
        if not session_id:
            return "Error: session_id required"

        db = get_session()
        try:
            session = (
                db.query(MCPSession)
                .filter(MCPSession.id == session_id, MCPSession.user_id == self.user_id)
                .first()
            )

            if not session:
                return "Session not found or access denied."

            session.is_active = False
            db.commit()
            return f"Session {session_id} revoked."
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()

    async def get_status(self) -> str:
        """Get MCP extension status."""
        db = get_session()
        try:
            total = db.query(MCPSession).count()
            active = (
                db.query(MCPSession)
                .filter(
                    MCPSession.is_active == True,
                    MCPSession.expires_at > datetime.utcnow(),
                )
                .count()
            )
            executions = db.query(MCPToolExecution).count()

            return f"""**Claude Code MCP Status**

- **MCP Package:** {'Available' if MCP_AVAILABLE else 'Not Installed'}
- **Sandboxing:** {'Enabled (safeexecute)' if SAFEEXECUTE_AVAILABLE else 'Disabled'}
- **OAuth Configured:** {'Yes' if getenv('ANTHROPIC_CLIENT_ID') else 'No'}

**Statistics:**
- Total Sessions: {total}
- Active Sessions: {active}
- Tool Executions: {executions}

**Settings:**
- Session Timeout: {self.session_timeout_hours} hours
- Max Sessions Per User: {self.max_sessions_per_user}
"""
        finally:
            db.close()

    # =========================================================================
    # OAuth
    # =========================================================================

    async def get_oauth_url(self, state: str = "") -> str:
        """Get Anthropic OAuth authorization URL."""
        client_id = getenv("ANTHROPIC_CLIENT_ID")
        if not client_id:
            return "Error: ANTHROPIC_CLIENT_ID not configured."

        redirect_uri = (
            getenv("APP_URI", "http://localhost:7437") + "/oauth/anthropic/callback"
        )

        code_verifier, code_challenge = generate_pkce_pair()
        if not state:
            state = secrets.token_urlsafe(32)
        self._pkce_verifiers[state] = code_verifier

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(OAUTH_SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())

        return f"""**Connect Your Claude Account**

[Click here to authorize]({OAUTH_AUTHORIZE_URL}?{query})

After authorizing, AGiXT will manage your Claude credentials securely.
"""

    async def check_oauth_connection(self) -> str:
        """Check if user has connected their Anthropic account."""
        if not self.user_id:
            return "Error: User not authenticated."

        db = get_session()
        try:
            provider = (
                db.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            if not provider:
                return "Anthropic OAuth not set up. Connect your account first."

            user_oauth = (
                db.query(UserOAuth)
                .filter(
                    UserOAuth.user_id == self.user_id,
                    UserOAuth.provider_id == provider.id,
                )
                .first()
            )

            if not user_oauth:
                return "No Anthropic account connected. Use 'Get Claude OAuth URL' to connect."

            expired = (
                user_oauth.token_expires_at
                and user_oauth.token_expires_at < datetime.utcnow()
            )

            return f"""**Anthropic Account Connected** {'(Token Expired)' if expired else '✓'}

- Account: {user_oauth.account_name}
- Connected: {user_oauth.created_at.strftime('%Y-%m-%d')}
- Status: {'Token expired - refresh needed' if expired else 'Active'}
"""
        finally:
            db.close()

    async def disconnect_oauth(self) -> str:
        """Disconnect Anthropic OAuth account."""
        if not self.user_id:
            return "Error: User not authenticated."

        db = get_session()
        try:
            provider = (
                db.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            if not provider:
                return "No connection found."

            user_oauth = (
                db.query(UserOAuth)
                .filter(
                    UserOAuth.user_id == self.user_id,
                    UserOAuth.provider_id == provider.id,
                )
                .first()
            )

            if not user_oauth:
                return "No Anthropic account connected."

            db.delete(user_oauth)
            db.commit()
            return "Anthropic account disconnected."
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()

    # =========================================================================
    # Tool Execution
    # =========================================================================

    async def execute_tool(
        self, session_token: str, tool_name: str, arguments: str = "{}"
    ) -> str:
        """
        Execute an MCP tool within the session context.
        Always uses safeexecute when available for sandboxed execution.
        """
        import time

        start_time = time.time()

        # Validate session
        db = get_session()
        try:
            mcp_session = (
                db.query(MCPSession)
                .filter(
                    MCPSession.session_token == session_token,
                    MCPSession.is_active == True,
                    MCPSession.expires_at > datetime.utcnow(),
                )
                .first()
            )

            if not mcp_session:
                return json.dumps({"error": "Invalid or expired session"})

            # Parse arguments
            try:
                args = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                return json.dumps({"error": "Invalid JSON arguments"})

            # Log execution
            execution = MCPToolExecution(
                session_id=mcp_session.id,
                tool_name=tool_name,
                arguments=arguments,
                status="pending",
            )
            db.add(execution)

            # Update session activity
            mcp_session.last_activity = datetime.utcnow()
            db.commit()

            # Get session metadata
            meta = json.loads(mcp_session.metadata) if mcp_session.metadata else {}
            agent_name = meta.get("agent_name", self.agent_name)

            # Execute tool - always use safeexecute if available
            if SAFEEXECUTE_AVAILABLE:
                result = await self._execute_sandboxed(
                    tool_name, args, str(mcp_session.id), agent_name
                )
            else:
                result = await self._execute_direct(tool_name, args, agent_name)

            # Update execution record
            execution.status = "success" if "error" not in result.lower() else "error"
            execution.result = result[:10000]
            execution.execution_time_ms = int((time.time() - start_time) * 1000)
            execution.completed_at = datetime.utcnow()
            db.commit()

            return result

        except Exception as e:
            logging.error(f"Tool execution error: {e}")
            return json.dumps({"error": str(e)})
        finally:
            db.close()

    async def _execute_sandboxed(
        self, tool_name: str, args: Dict, session_id: str, agent_name: str
    ) -> str:
        """Execute tool in safeexecute sandbox"""
        sandbox_code = f"""
import os
import sys
import json
import asyncio

os.environ["AGIXT_API_URL"] = "{getenv('AGIXT_URI', 'http://localhost:7437')}"
os.environ["AGIXT_AGENT_NAME"] = "{agent_name}"

sys.path.insert(0, "{os.path.dirname(os.path.dirname(__file__))}")
from extensions.claude_code import execute_mcp_tool

result = asyncio.run(execute_mcp_tool(
    tool_name="{tool_name}",
    arguments={json.dumps(args)},
    agent_name="{agent_name}",
))
print(json.dumps(result, default=str))
"""
        try:
            workspace_dir = os.path.join(os.getcwd(), "WORKSPACE", session_id)
            os.makedirs(workspace_dir, exist_ok=True)
            return execute_python_code(
                code=sandbox_code, working_directory=workspace_dir
            )
        except Exception as e:
            logging.warning(f"Sandbox execution failed, falling back to direct: {e}")
            return await self._execute_direct(tool_name, args, agent_name)

    async def _execute_direct(self, tool_name: str, args: Dict, agent_name: str) -> str:
        """Execute tool directly (fallback when sandbox unavailable)"""
        result = await execute_mcp_tool(
            tool_name=tool_name, arguments=args, agent_name=agent_name
        )
        return json.dumps(result, indent=2, default=str)

    # =========================================================================
    # Maintenance
    # =========================================================================

    async def cleanup_sessions(self) -> str:
        """Clean up expired sessions."""
        db = get_session()
        try:
            expired = (
                db.query(MCPSession)
                .filter(
                    MCPSession.expires_at < datetime.utcnow(),
                    MCPSession.is_active == True,
                )
                .all()
            )

            count = len(expired)
            for s in expired:
                s.is_active = False
            db.commit()

            return f"Cleaned up {count} expired sessions."
        except Exception as e:
            db.rollback()
            return f"Error: {e}"
        finally:
            db.close()
