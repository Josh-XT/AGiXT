"""
MCP Hub Endpoints for AGiXT

These endpoints enable Claude Code to connect to AGiXT via MCP session tokens.
Instead of users manually configuring MCP servers, they can:
1. Create a session via the claude_code_hub extension
2. Use the session token to authenticate MCP connections
3. Execute tools through the hub with proper sandboxing
"""

import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Header, Depends, Request
from pydantic import BaseModel, Field
from datetime import datetime

from MagicalAuth import MagicalAuth, verify_api_key
from Globals import getenv

router = APIRouter()
logger = logging.getLogger(__name__)


class MCPToolRequest(BaseModel):
    """Request to execute an MCP tool"""
    tool_name: str = Field(..., description="Name of the MCP tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class MCPToolResponse(BaseModel):
    """Response from MCP tool execution"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class MCPSessionInfo(BaseModel):
    """MCP session information"""
    session_id: str
    user_id: str
    agent_name: str
    expires_at: str
    is_active: bool


class MCPToolListResponse(BaseModel):
    """List of available MCP tools"""
    tools: list


async def validate_mcp_session(
    authorization: str = Header(None, description="Bearer token for MCP session"),
) -> Dict[str, Any]:
    """
    Validate an MCP session token from the Authorization header.
    
    Returns session info if valid, raises HTTPException if invalid.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = parts[1]
    
    # Check if it's an MCP session token
    if not token.startswith("agixt_mcp_"):
        raise HTTPException(status_code=401, detail="Invalid MCP session token format")
    
    # Look up the session
    from DB import get_session
    from sqlalchemy import text
    
    db_session = get_session()
    try:
        # Query for the session
        result = db_session.execute(
            text("""
                SELECT id, user_id, session_token, anthropic_user_id,
                       created_at, expires_at, last_activity, is_active, metadata
                FROM mcp_sessions
                WHERE session_token = :token
                AND is_active = true
                AND expires_at > :now
            """),
            {"token": token, "now": datetime.utcnow()}
        ).fetchone()
        
        if not result:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        
        # Update last activity
        db_session.execute(
            text("UPDATE mcp_sessions SET last_activity = :now WHERE id = :id"),
            {"now": datetime.utcnow(), "id": result.id}
        )
        db_session.commit()
        
        metadata = json.loads(result.metadata) if result.metadata else {}
        
        return {
            "session_id": str(result.id),
            "user_id": str(result.user_id),
            "agent_name": metadata.get("agent_name", "gpt4free"),
            "expires_at": result.expires_at.isoformat(),
            "is_active": result.is_active,
            "metadata": metadata,
        }
    finally:
        db_session.close()


@router.get("/v1/mcp/tools", tags=["MCP Hub"])
async def list_mcp_tools(
    session: Dict = Depends(validate_mcp_session),
) -> MCPToolListResponse:
    """
    List available MCP tools.
    
    This endpoint returns all MCP tools that can be executed through the hub.
    Requires a valid MCP session token.
    """
    from extensions.claude_code import get_tool_definitions
    
    return MCPToolListResponse(tools=get_tool_definitions())


@router.post("/v1/mcp/execute", tags=["MCP Hub"])
async def execute_mcp_tool(
    request: MCPToolRequest,
    session: Dict = Depends(validate_mcp_session),
) -> MCPToolResponse:
    """
    Execute an MCP tool.
    
    This endpoint executes an MCP tool with the given arguments.
    The tool runs in a sandboxed environment if safeexecute is available.
    Requires a valid MCP session token.
    """
    import time
    start_time = time.time()
    
    try:
        from extensions.claude_code import execute_mcp_tool as run_tool, MCP_TOOLS
        
        # Validate tool exists
        if request.tool_name not in MCP_TOOLS:
            return MCPToolResponse(
                success=False,
                error=f"Unknown tool: {request.tool_name}",
            )
        
        # Execute the tool
        result = await run_tool(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_name=session.get("agent_name"),
        )
        
        execution_time = int((time.time() - start_time) * 1000)
        
        # Check for errors in result
        if isinstance(result, dict) and "error" in result:
            return MCPToolResponse(
                success=False,
                error=result["error"],
                execution_time_ms=execution_time,
            )
        
        return MCPToolResponse(
            success=True,
            result=result,
            execution_time_ms=execution_time,
        )
    
    except Exception as e:
        logger.error(f"MCP tool execution error: {e}")
        return MCPToolResponse(
            success=False,
            error=str(e),
            execution_time_ms=int((time.time() - start_time) * 1000),
        )


@router.get("/v1/mcp/session", tags=["MCP Hub"])
async def get_session_info(
    session: Dict = Depends(validate_mcp_session),
) -> MCPSessionInfo:
    """
    Get information about the current MCP session.
    
    Returns session details including user, agent, and expiration.
    """
    return MCPSessionInfo(
        session_id=session["session_id"],
        user_id=session["user_id"],
        agent_name=session["agent_name"],
        expires_at=session["expires_at"],
        is_active=session["is_active"],
    )


@router.post("/v1/mcp/connect", tags=["MCP Hub"])
async def mcp_connect(
    request: Request,
    session: Dict = Depends(validate_mcp_session),
):
    """
    MCP Connection endpoint for stdio-style communication.
    
    This endpoint can be used by Claude Code to establish an MCP connection.
    It returns the available tools and handles JSON-RPC style requests.
    """
    from extensions.claude_code import get_tool_definitions, execute_mcp_tool
    
    # Get the request body if any
    try:
        body = await request.json()
    except:
        body = {}
    
    # Handle different MCP methods
    method = body.get("method", "initialize")
    params = body.get("params", {})
    request_id = body.get("id", 1)
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "0.1.0",
                "serverInfo": {
                    "name": "AGiXT MCP Hub",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "tools": True,
                },
            },
        }
    
    elif method == "tools/list":
        tools = get_tool_definitions()
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": t["inputSchema"],
                    }
                    for t in tools
                ],
            },
        }
    
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        result = await execute_mcp_tool(
            tool_name=tool_name,
            arguments=arguments,
            agent_name=session.get("agent_name"),
        )
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, default=str),
                    }
                ],
            },
        }
    
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }
