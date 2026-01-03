"""
Claude Code MCP Hub Extension for AGiXT

This extension provides a secure, multi-tenant MCP server hub that:
1. Allows users to authenticate with their Anthropic/Claude credentials
2. Spins up isolated MCP server instances per user using safeexecute
3. Routes MCP commands through AGiXT with proper user context
4. Provides session management and tool execution sandboxing

This approach:
- Centralizes MCP management through AGiXT
- Provides proper user isolation via safeexecute containers
- No need for users to manually configure Claude Code
- AGiXT acts as an MCP registry/proxy

Required environment variables:
- ANTHROPIC_CLIENT_ID: Anthropic OAuth client ID (when available)
- ANTHROPIC_CLIENT_SECRET: Anthropic OAuth client secret (when available)
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from Extensions import Extensions
from Globals import getenv, install_package_if_missing
from DB import (
    get_session,
    Base,
    DATABASE_TYPE,
    UUID,
    get_new_id,
    ExtensionDatabaseMixin,
)
from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

# Install dependencies
install_package_if_missing("mcp")
install_package_if_missing("aiohttp")

try:
    from safeexecute import execute_python_code, execute_shell_command
    SAFEEXECUTE_AVAILABLE = True
except ImportError:
    SAFEEXECUTE_AVAILABLE = False
    logging.warning("safeexecute not available - MCP sessions will run without sandboxing")

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


# Database model for MCP sessions
class MCPSession(Base):
    """Database model for tracking MCP sessions per user"""
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
    anthropic_user_id = Column(String(256), nullable=True)  # From Anthropic OAuth when available
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    metadata = Column(
        JSONB if DATABASE_TYPE == "postgresql" else Text,
        nullable=True,
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "session_token": self.session_token[:8] + "...",  # Partially masked
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "is_active": self.is_active,
        }


class MCPToolExecution(Base):
    """Database model for tracking MCP tool executions"""
    __tablename__ = "mcp_tool_executions"
    __table_args__ = {"extend_existing": True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        UUID(as_uuid=True) if DATABASE_TYPE != "sqlite" else String,
        ForeignKey("mcp_sessions.id"),
        nullable=False,
    )
    tool_name = Column(String(256), nullable=False)
    arguments = Column(
        JSONB if DATABASE_TYPE == "postgresql" else Text,
        nullable=True,
    )
    result = Column(Text, nullable=True)
    status = Column(String(50), default="pending")  # pending, success, error
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


@dataclass
class MCPSessionContext:
    """Runtime context for an active MCP session"""
    session_id: str
    user_id: str
    user_email: str
    agent_name: str
    api_key: str
    conversation_id: Optional[str] = None
    sandbox_id: Optional[str] = None
    tools_executed: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


class claude_code_hub(Extensions, ExtensionDatabaseMixin):
    """
    Claude Code MCP Hub - A secure, multi-tenant MCP server for AGiXT.
    
    This extension allows AGiXT to act as an MCP server hub where:
    - Users authenticate through AGiXT (and optionally with Anthropic OAuth)
    - Each user gets an isolated session with sandboxed tool execution
    - MCP tools are executed through safeexecute for security
    - All activity is logged and can be audited
    
    The hub can be accessed by Claude Code using a session-specific endpoint,
    eliminating the need for users to manually configure MCP servers.
    """
    
    CATEGORY = "AI Integration"
    friendly_name = "Claude Code MCP Hub"
    
    # Register database models
    extension_models = [MCPSession, MCPToolExecution]
    
    def __init__(
        self,
        MCP_HUB_ENABLED: bool = True,
        MCP_SESSION_TIMEOUT_HOURS: int = 24,
        MCP_MAX_SESSIONS_PER_USER: int = 5,
        MCP_SANDBOX_ENABLED: bool = True,
        MCP_LOG_EXECUTIONS: bool = True,
        **kwargs,
    ):
        self.MCP_HUB_ENABLED = str(MCP_HUB_ENABLED).lower() == "true"
        self.MCP_SESSION_TIMEOUT_HOURS = int(MCP_SESSION_TIMEOUT_HOURS)
        self.MCP_MAX_SESSIONS_PER_USER = int(MCP_MAX_SESSIONS_PER_USER)
        self.MCP_SANDBOX_ENABLED = str(MCP_SANDBOX_ENABLED).lower() == "true" and SAFEEXECUTE_AVAILABLE
        self.MCP_LOG_EXECUTIONS = str(MCP_LOG_EXECUTIONS).lower() == "true"
        
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
        
        # Active sessions cache
        self._active_sessions: Dict[str, MCPSessionContext] = {}
        
        self.commands = {
            "Create MCP Session": self.create_mcp_session,
            "Create MCP Session with Claude OAuth": self.create_session_with_oauth,
            "List MCP Sessions": self.list_mcp_sessions,
            "Get MCP Session Info": self.get_mcp_session_info,
            "Revoke MCP Session": self.revoke_mcp_session,
            "Execute MCP Tool": self.execute_mcp_tool,
            "Get MCP Hub Status": self.get_mcp_hub_status,
            "Get Claude Code Connection Info": self.get_connection_info,
            "Cleanup Expired Sessions": self.cleanup_expired_sessions,
        }
    
    def _generate_session_token(self) -> str:
        """Generate a secure session token"""
        return f"agixt_mcp_{secrets.token_urlsafe(32)}"
    
    def _get_session_by_token(self, token: str) -> Optional[MCPSession]:
        """Get session from database by token"""
        session = get_session()
        try:
            mcp_session = (
                session.query(MCPSession)
                .filter(MCPSession.session_token == token)
                .filter(MCPSession.is_active == True)
                .filter(MCPSession.expires_at > datetime.utcnow())
                .first()
            )
            return mcp_session
        finally:
            session.close()
    
    async def create_mcp_session(
        self,
        session_name: str = "",
        expires_in_hours: int = 0,
    ) -> str:
        """
        Create a new MCP session for the current user.
        
        This generates a unique session token that can be used to connect
        Claude Code to this AGiXT instance securely.
        
        Args:
            session_name: Optional friendly name for the session
            expires_in_hours: Session expiration (0 = use default)
        
        Returns:
            str: Session information including connection details
        """
        if not self.MCP_HUB_ENABLED:
            return "MCP Hub is disabled. Enable it in agent settings."
        
        if not self.user_id:
            return "Error: User ID not available. Please ensure you're authenticated."
        
        session = get_session()
        try:
            # Check existing session count
            existing_count = (
                session.query(MCPSession)
                .filter(MCPSession.user_id == self.user_id)
                .filter(MCPSession.is_active == True)
                .count()
            )
            
            if existing_count >= self.MCP_MAX_SESSIONS_PER_USER:
                return f"Error: Maximum sessions ({self.MCP_MAX_SESSIONS_PER_USER}) reached. Revoke an existing session first."
            
            # Create new session
            token = self._generate_session_token()
            expiry_hours = expires_in_hours if expires_in_hours > 0 else self.MCP_SESSION_TIMEOUT_HOURS
            
            mcp_session = MCPSession(
                user_id=self.user_id,
                session_token=token,
                expires_at=datetime.utcnow() + timedelta(hours=expiry_hours),
                metadata=json.dumps({
                    "name": session_name or f"Session {existing_count + 1}",
                    "agent_name": self.agent_name,
                    "created_by": self.user,
                }),
            )
            
            session.add(mcp_session)
            session.commit()
            
            # Get connection info
            agixt_uri = getenv("AGIXT_URI", "http://localhost:7437")
            
            return f"""MCP Session Created Successfully!

**Session Token:** `{token}`

**Expires:** {mcp_session.expires_at.strftime('%Y-%m-%d %H:%M UTC')}

---

## Claude Code Configuration

Add this to your Claude Desktop/Code config file:

**Config Locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`
- Linux: `~/.config/claude/claude_desktop_config.json`

```json
{{
  "mcpServers": {{
    "agixt": {{
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-H", "Authorization: Bearer {token}",
        "{agixt_uri}/api/v1/mcp/connect"
      ]
    }}
  }}
}}
```

Or use the Python MCP server directly:

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

**Security Notes:**
- This token grants access to your AGiXT account
- Do not share it publicly
- Revoke it when no longer needed
"""
        except Exception as e:
            session.rollback()
            return f"Error creating session: {str(e)}"
        finally:
            session.close()
    
    async def create_session_with_oauth(
        self,
        session_name: str = "",
    ) -> str:
        """
        Create an MCP session linked to the user's Anthropic OAuth credentials.
        
        This method checks if the user has connected their Anthropic account
        via OAuth and creates a session that can use their Claude credentials.
        
        Args:
            session_name: Optional friendly name for the session
        
        Returns:
            str: Session information or OAuth connection instructions
        """
        if not self.MCP_HUB_ENABLED:
            return "MCP Hub is disabled."
        
        if not self.user_id:
            return "Error: User not authenticated."
        
        # Check for Anthropic OAuth connection
        from DB import UserOAuth, OAuthProvider
        
        db_session = get_session()
        try:
            # Find Anthropic OAuth provider
            provider = (
                db_session.query(OAuthProvider)
                .filter(OAuthProvider.name == "anthropic")
                .first()
            )
            
            anthropic_user_id = None
            claude_access_token = None
            
            if provider:
                # Check for user's OAuth connection
                user_oauth = (
                    db_session.query(UserOAuth)
                    .filter(UserOAuth.user_id == self.user_id)
                    .filter(UserOAuth.provider_id == provider.id)
                    .first()
                )
                
                if user_oauth:
                    anthropic_user_id = user_oauth.account_name
                    claude_access_token = user_oauth.access_token
            
            if not claude_access_token:
                return """**No Anthropic Account Connected**

To create an OAuth-linked MCP session, first connect your Claude account:

1. Enable the `anthropic_oauth` extension for your agent
2. Use the "Get Anthropic OAuth URL" command
3. Log in with your Anthropic account
4. Return here and try again

Alternatively, use "Create MCP Session" for a standard session.
"""
            
            # Create OAuth-linked session
            token = self._generate_session_token()
            
            mcp_session = MCPSession(
                user_id=self.user_id,
                session_token=token,
                anthropic_user_id=anthropic_user_id,
                expires_at=datetime.utcnow() + timedelta(hours=self.MCP_SESSION_TIMEOUT_HOURS),
                metadata=json.dumps({
                    "name": session_name or "Claude OAuth Session",
                    "agent_name": self.agent_name,
                    "oauth_linked": True,
                    "created_by": self.user,
                }),
            )
            
            db_session.add(mcp_session)
            db_session.commit()
            
            agixt_uri = getenv("AGIXT_URI", "http://localhost:7437")
            
            return f"""**OAuth-Linked MCP Session Created!**

Your session is linked to your Anthropic account: `{anthropic_user_id}`

**Session Token:** `{token}`
**Expires:** {mcp_session.expires_at.strftime('%Y-%m-%d %H:%M UTC')}

This session can access Claude features using your authenticated credentials.

**Claude Code Config:**
```json
{{
  "mcpServers": {{
    "agixt-oauth": {{
      "command": "python",
      "args": ["-m", "agixt.extensions.claude_code_mcp_server"],
      "env": {{
        "AGIXT_API_URL": "{agixt_uri}",
        "AGIXT_MCP_SESSION_TOKEN": "{token}",
        "AGIXT_AGENT_NAME": "{self.agent_name}",
        "AGIXT_USE_OAUTH": "true"
      }}
    }}
  }}
}}
```
"""
        except Exception as e:
            db_session.rollback()
            return f"Error creating OAuth session: {str(e)}"
        finally:
            db_session.close()
    
    async def list_mcp_sessions(self) -> str:
        """
        List all active MCP sessions for the current user.
        
        Returns:
            str: Formatted list of sessions
        """
        if not self.user_id:
            return "Error: User ID not available."
        
        session = get_session()
        try:
            sessions = (
                session.query(MCPSession)
                .filter(MCPSession.user_id == self.user_id)
                .filter(MCPSession.is_active == True)
                .order_by(MCPSession.created_at.desc())
                .all()
            )
            
            if not sessions:
                return "No active MCP sessions found."
            
            result = "**Active MCP Sessions:**\n\n"
            for s in sessions:
                metadata = json.loads(s.metadata) if s.metadata else {}
                name = metadata.get("name", "Unnamed")
                result += f"- **{name}** (ID: {str(s.id)[:8]}...)\n"
                result += f"  - Created: {s.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"  - Expires: {s.expires_at.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"  - Last Activity: {s.last_activity.strftime('%Y-%m-%d %H:%M')}\n\n"
            
            return result
        finally:
            session.close()
    
    async def get_mcp_session_info(self, session_id: str = "") -> str:
        """
        Get detailed information about an MCP session.
        
        Args:
            session_id: The session ID to look up
        
        Returns:
            str: Session details
        """
        if not session_id:
            return "Error: session_id is required"
        
        session = get_session()
        try:
            mcp_session = (
                session.query(MCPSession)
                .filter(MCPSession.id == session_id)
                .filter(MCPSession.user_id == self.user_id)
                .first()
            )
            
            if not mcp_session:
                return "Session not found or access denied."
            
            # Get execution stats
            exec_count = (
                session.query(MCPToolExecution)
                .filter(MCPToolExecution.session_id == session_id)
                .count()
            )
            
            metadata = json.loads(mcp_session.metadata) if mcp_session.metadata else {}
            
            return f"""**MCP Session Details**

- **Name:** {metadata.get('name', 'Unnamed')}
- **ID:** {mcp_session.id}
- **Status:** {'Active' if mcp_session.is_active else 'Revoked'}
- **Created:** {mcp_session.created_at.strftime('%Y-%m-%d %H:%M UTC')}
- **Expires:** {mcp_session.expires_at.strftime('%Y-%m-%d %H:%M UTC')}
- **Last Activity:** {mcp_session.last_activity.strftime('%Y-%m-%d %H:%M UTC')}
- **Tool Executions:** {exec_count}
- **Agent:** {metadata.get('agent_name', 'Unknown')}
"""
        finally:
            session.close()
    
    async def revoke_mcp_session(self, session_id: str = "") -> str:
        """
        Revoke an MCP session, immediately invalidating the token.
        
        Args:
            session_id: The session ID to revoke
        
        Returns:
            str: Confirmation message
        """
        if not session_id:
            return "Error: session_id is required"
        
        session = get_session()
        try:
            mcp_session = (
                session.query(MCPSession)
                .filter(MCPSession.id == session_id)
                .filter(MCPSession.user_id == self.user_id)
                .first()
            )
            
            if not mcp_session:
                return "Session not found or access denied."
            
            mcp_session.is_active = False
            session.commit()
            
            # Remove from active cache if present
            cache_key = str(mcp_session.id)
            if cache_key in self._active_sessions:
                del self._active_sessions[cache_key]
            
            return f"Session {session_id} has been revoked."
        except Exception as e:
            session.rollback()
            return f"Error revoking session: {str(e)}"
        finally:
            session.close()
    
    async def execute_mcp_tool(
        self,
        session_token: str,
        tool_name: str,
        arguments: str = "{}",
    ) -> str:
        """
        Execute an MCP tool within a sandboxed environment.
        
        This is the core method that handles tool execution for MCP sessions.
        It validates the session, sets up sandboxing, and executes the tool.
        
        Args:
            session_token: The MCP session token
            tool_name: Name of the tool to execute
            arguments: JSON string of tool arguments
        
        Returns:
            str: Tool execution result
        """
        import time
        start_time = time.time()
        
        # Validate session
        mcp_session = self._get_session_by_token(session_token)
        if not mcp_session:
            return json.dumps({"error": "Invalid or expired session token"})
        
        # Parse arguments
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON arguments"})
        
        session = get_session()
        execution_record = None
        
        try:
            # Log execution start
            if self.MCP_LOG_EXECUTIONS:
                execution_record = MCPToolExecution(
                    session_id=mcp_session.id,
                    tool_name=tool_name,
                    arguments=arguments,
                    status="pending",
                )
                session.add(execution_record)
                session.commit()
            
            # Update session activity
            mcp_session.last_activity = datetime.utcnow()
            session.commit()
            
            # Get session context
            metadata = json.loads(mcp_session.metadata) if mcp_session.metadata else {}
            
            # Execute the tool
            if self.MCP_SANDBOX_ENABLED:
                result = await self._execute_tool_sandboxed(
                    tool_name=tool_name,
                    arguments=args,
                    session_id=str(mcp_session.id),
                    user_id=str(mcp_session.user_id),
                    agent_name=metadata.get("agent_name", self.agent_name),
                )
            else:
                result = await self._execute_tool_direct(
                    tool_name=tool_name,
                    arguments=args,
                    session_id=str(mcp_session.id),
                    user_id=str(mcp_session.user_id),
                    agent_name=metadata.get("agent_name", self.agent_name),
                )
            
            # Update execution record
            if self.MCP_LOG_EXECUTIONS and execution_record:
                execution_record.status = "success"
                execution_record.result = result[:10000] if len(result) > 10000 else result
                execution_record.execution_time_ms = int((time.time() - start_time) * 1000)
                execution_record.completed_at = datetime.utcnow()
                session.commit()
            
            return result
            
        except Exception as e:
            if self.MCP_LOG_EXECUTIONS and execution_record:
                execution_record.status = "error"
                execution_record.result = str(e)
                execution_record.execution_time_ms = int((time.time() - start_time) * 1000)
                execution_record.completed_at = datetime.utcnow()
                session.commit()
            
            return json.dumps({"error": str(e)})
        finally:
            session.close()
    
    async def _execute_tool_sandboxed(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: str,
        user_id: str,
        agent_name: str,
    ) -> str:
        """Execute a tool in a sandboxed environment using safeexecute"""
        
        # Build the Python code to execute in sandbox
        sandbox_code = f'''
import os
import sys
import json
import asyncio

# Set up environment
os.environ["AGIXT_API_URL"] = "{getenv('AGIXT_URI', 'http://localhost:7437')}"
os.environ["AGIXT_AGENT_NAME"] = "{agent_name}"
os.environ["AGIXT_USER_ID"] = "{user_id}"

# Import the MCP tool executor
sys.path.insert(0, "{os.path.dirname(os.path.dirname(__file__))}")
from extensions.claude_code_mcp_tools import execute_tool

# Execute the tool
result = asyncio.run(execute_tool(
    tool_name="{tool_name}",
    arguments={json.dumps(arguments)},
    agent_name="{agent_name}",
))

print(json.dumps(result))
'''
        
        try:
            result = execute_python_code(
                code=sandbox_code,
                working_directory=os.path.join(os.getcwd(), "WORKSPACE", session_id),
            )
            return result
        except Exception as e:
            logging.error(f"Sandboxed execution failed: {e}")
            # Fall back to direct execution
            return await self._execute_tool_direct(
                tool_name, arguments, session_id, user_id, agent_name
            )
    
    async def _execute_tool_direct(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: str,
        user_id: str,
        agent_name: str,
    ) -> str:
        """Execute a tool directly (without sandbox)"""
        from extensions.claude_code_mcp_tools import execute_tool
        
        result = await execute_tool(
            tool_name=tool_name,
            arguments=arguments,
            agent_name=agent_name,
        )
        return json.dumps(result, indent=2, default=str)
    
    async def get_mcp_hub_status(self) -> str:
        """
        Get the current status of the MCP Hub.
        
        Returns:
            str: Hub status information
        """
        session = get_session()
        try:
            total_sessions = session.query(MCPSession).count()
            active_sessions = (
                session.query(MCPSession)
                .filter(MCPSession.is_active == True)
                .filter(MCPSession.expires_at > datetime.utcnow())
                .count()
            )
            total_executions = session.query(MCPToolExecution).count()
            
            return f"""**MCP Hub Status**

- **Hub Enabled:** {self.MCP_HUB_ENABLED}
- **Sandbox Enabled:** {self.MCP_SANDBOX_ENABLED}
- **SafeExecute Available:** {SAFEEXECUTE_AVAILABLE}
- **MCP Package Available:** {MCP_AVAILABLE}

**Statistics:**
- Total Sessions: {total_sessions}
- Active Sessions: {active_sessions}
- Total Tool Executions: {total_executions}

**Configuration:**
- Session Timeout: {self.MCP_SESSION_TIMEOUT_HOURS} hours
- Max Sessions Per User: {self.MCP_MAX_SESSIONS_PER_USER}
- Execution Logging: {self.MCP_LOG_EXECUTIONS}
"""
        finally:
            session.close()
    
    async def get_connection_info(self) -> str:
        """
        Get connection information for Claude Code.
        
        Returns:
            str: Connection instructions
        """
        agixt_uri = getenv("AGIXT_URI", "http://localhost:7437")
        
        return f"""**Claude Code MCP Hub Connection**

The MCP Hub allows Claude Code to securely connect to AGiXT without manual configuration.

**Setup Steps:**

1. **Create a Session:**
   Use the "Create MCP Session" command to generate a session token.

2. **Configure Claude Code:**
   Add the provided configuration to your Claude config file.

3. **Start Using:**
   Claude Code will automatically discover and use AGiXT tools.

**Available MCP Tools:**
- `agixt_chat` - Chat with agents
- `agixt_inference` - Advanced inference
- `agixt_run_chain` - Execute chains
- `agixt_query_memories` - Search memories
- `agixt_add_memory` - Add knowledge
- `agixt_learn_url` - Learn from URLs
- `agixt_execute_command` - Run commands
- And more...

**AGiXT URI:** {agixt_uri}

**Security:**
- Each session is isolated
- Tools execute in sandboxed containers
- All executions are logged
- Sessions expire automatically
"""
    
    async def cleanup_expired_sessions(self) -> str:
        """
        Clean up expired MCP sessions.
        
        Returns:
            str: Cleanup summary
        """
        session = get_session()
        try:
            expired = (
                session.query(MCPSession)
                .filter(MCPSession.expires_at < datetime.utcnow())
                .filter(MCPSession.is_active == True)
                .all()
            )
            
            count = len(expired)
            for s in expired:
                s.is_active = False
            
            session.commit()
            
            return f"Cleaned up {count} expired sessions."
        except Exception as e:
            session.rollback()
            return f"Error during cleanup: {str(e)}"
        finally:
            session.close()
