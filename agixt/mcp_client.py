"""
Model Context Protocol (MCP) Client Implementation for AGiXT

This module provides a proper MCP client that follows the protocol specification
for interacting with MCP servers.
"""

import json
import uuid
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List, Union
from enum import Enum
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP-specific error"""

    def __init__(self, error_data: dict):
        self.code = error_data.get("code", -1)
        self.message = error_data.get("message", "Unknown error")
        self.data = error_data.get("data")
        super().__init__(f"MCP Error {self.code}: {self.message}")


class TransportType(Enum):
    HTTP = "http"
    STDIO = "stdio"


class JSONRPCMessage:
    """Helper class for JSON-RPC 2.0 message construction"""

    @staticmethod
    def request(
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> dict:
        """Create a JSON-RPC 2.0 request"""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id or str(uuid.uuid4()),
        }
        if params is not None:
            message["params"] = params
        return message

    @staticmethod
    def notification(method: str, params: Optional[Dict[str, Any]] = None) -> dict:
        """Create a JSON-RPC 2.0 notification (no id field)"""
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        return message


class HTTPTransport:
    """HTTP transport with Server-Sent Events support for MCP"""

    def __init__(
        self, endpoint_url: str, auth_headers: Optional[Dict[str, str]] = None
    ):
        self.endpoint_url = endpoint_url
        self.auth_headers = auth_headers or {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.sse_task: Optional[asyncio.Task] = None
        self.notification_handlers = {}

    async def connect(self):
        """Establish HTTP connection"""
        self.session = aiohttp.ClientSession(headers=self.auth_headers)

    async def disconnect(self):
        """Close HTTP connection"""
        if self.sse_task:
            self.sse_task.cancel()
        if self.session:
            await self.session.close()

    async def send_request(self, request: dict) -> dict:
        """Send JSON-RPC request and wait for response"""
        if not self.session:
            await self.connect()

        async with self.session.post(self.endpoint_url, json=request) as response:
            response.raise_for_status()
            return await response.json()

    async def send_notification(self, notification: dict):
        """Send JSON-RPC notification (no response expected)"""
        if not self.session:
            await self.connect()

        async with self.session.post(self.endpoint_url, json=notification) as response:
            response.raise_for_status()

    def register_notification_handler(self, method: str, handler):
        """Register a handler for server notifications"""
        self.notification_handlers[method] = handler

    async def _handle_sse_events(self):
        """Handle Server-Sent Events for server-to-client messages"""
        # This would implement SSE handling for receiving server notifications
        # For now, this is a placeholder
        pass


class StdioTransport:
    """Standard I/O transport for local MCP servers"""

    def __init__(
        self, command: str, args: List[str] = None, env: Optional[Dict[str, str]] = None
    ):
        self.command = command
        self.args = args or []
        self.env = env
        self.process: Optional[asyncio.subprocess.Process] = None
        self.read_task: Optional[asyncio.Task] = None
        self.notification_handlers = {}
        self._pending_requests = {}

    async def connect(self):
        """Start the MCP server process"""
        import os

        # Use provided environment or copy current environment
        process_env = self.env.copy() if self.env else os.environ.copy()

        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=process_env,
        )

        # Start reading from stdout
        self.read_task = asyncio.create_task(self._read_messages())

    async def disconnect(self):
        """Stop the MCP server process"""
        if self.read_task:
            self.read_task.cancel()
        if self.process:
            self.process.terminate()
            await self.process.wait()

    async def send_request(self, request: dict) -> dict:
        """Send request via stdin and wait for response"""
        if not self.process:
            raise RuntimeError("Transport not connected")

        request_id = request.get("id")
        response_future = asyncio.Future()

        # Store the future for this request ID
        self._pending_requests[request_id] = response_future

        # Send the request
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line.encode())
        await self.process.stdin.drain()

        # Wait for the response
        return await response_future

    async def send_notification(self, notification: dict):
        """Send notification via stdin (no response expected)"""
        if not self.process:
            raise RuntimeError("Transport not connected")

        # Send the notification
        notification_line = json.dumps(notification) + "\n"
        self.process.stdin.write(notification_line.encode())
        await self.process.stdin.drain()

    def register_notification_handler(self, method: str, handler):
        """Register a handler for server notifications"""
        self.notification_handlers[method] = handler

    async def _read_messages(self):
        """Read messages from stdout"""
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break

                message = json.loads(line.decode().strip())

                # Handle response
                if "id" in message:
                    request_id = message["id"]
                    if request_id in self._pending_requests:
                        self._pending_requests[request_id].set_result(message)
                        del self._pending_requests[request_id]

                # Handle notification
                elif "method" in message:
                    method = message["method"]
                    if method in self.notification_handlers:
                        await self.notification_handlers[method](
                            message.get("params", {})
                        )

            except Exception as e:
                logger.error(f"Error reading message: {e}")


class MCPClient:
    """
    MCP Client implementation following the Model Context Protocol specification
    """

    def __init__(self, transport_type: TransportType, **transport_params):
        self.transport_type = transport_type
        self.transport = self._create_transport(transport_type, transport_params)
        self.initialized = False
        self.server_capabilities = {}
        self.server_info = {}
        self.protocol_version = "2025-06-18"

    def _create_transport(self, transport_type: TransportType, params: dict):
        """Create the appropriate transport instance"""
        if transport_type == TransportType.HTTP:
            return HTTPTransport(
                endpoint_url=params.get("endpoint_url"),
                auth_headers=params.get("auth_headers", {}),
            )
        elif transport_type == TransportType.STDIO:
            return StdioTransport(
                command=params.get("command"),
                args=params.get("args", []),
                env=params.get("env"),
            )
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")

    async def connect(self):
        """Connect to the MCP server"""
        await self.transport.connect()

    async def disconnect(self):
        """Disconnect from the MCP server"""
        await self.transport.disconnect()

    async def initialize(self, client_info: Optional[dict] = None) -> dict:
        """
        Initialize the MCP connection with capability negotiation

        Returns:
            Server capabilities and info
        """
        if self.initialized:
            raise RuntimeError("Client already initialized")

        # Default client info
        if not client_info:
            client_info = {"name": "AGiXT-MCP-Client", "version": "1.0.0"}

        # Send initialize request
        response = await self._request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {
                    "tools": {},  # Client can call tools
                    "resources": {},  # Client can read resources
                    "prompts": {},  # Client can use prompts
                    "logging": {},  # Client can receive log messages
                },
                "clientInfo": client_info,
            },
        )

        # Store server capabilities
        self.server_capabilities = response.get("capabilities", {})
        self.server_info = response.get("serverInfo", {})

        # Send initialized notification
        await self._notify("notifications/initialized")

        self.initialized = True

        # Register notification handlers if server supports them
        if self.server_capabilities.get("tools", {}).get("listChanged"):
            self.transport.register_notification_handler(
                "notifications/tools/list_changed", self._handle_tools_changed
            )

        return {
            "capabilities": self.server_capabilities,
            "serverInfo": self.server_info,
        }

    async def list_tools(self) -> List[dict]:
        """List available tools from the server"""
        self._ensure_initialized()

        if not self.server_capabilities.get("tools"):
            return []

        response = await self._request("tools/list")
        return response.get("tools", [])

    async def call_tool(
        self, name: str, arguments: Optional[dict] = None
    ) -> List[dict]:
        """
        Call a tool on the server

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            List of content objects
        """
        self._ensure_initialized()

        if not self.server_capabilities.get("tools"):
            raise RuntimeError("Server does not support tools")

        response = await self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )

        return response.get("content", [])

    async def list_resources(self) -> List[dict]:
        """List available resources from the server"""
        self._ensure_initialized()

        if not self.server_capabilities.get("resources"):
            return []

        response = await self._request("resources/list")
        return response.get("resources", [])

    async def read_resource(self, uri: str) -> List[dict]:
        """
        Read a resource from the server

        Args:
            uri: Resource URI

        Returns:
            List of content objects
        """
        self._ensure_initialized()

        if not self.server_capabilities.get("resources"):
            raise RuntimeError("Server does not support resources")

        response = await self._request("resources/read", {"uri": uri})

        return response.get("content", [])

    async def list_prompts(self) -> List[dict]:
        """List available prompts from the server"""
        self._ensure_initialized()

        if not self.server_capabilities.get("prompts"):
            return []

        response = await self._request("prompts/list")
        return response.get("prompts", [])

    async def get_prompt(self, name: str, arguments: Optional[dict] = None) -> dict:
        """
        Get a prompt from the server

        Args:
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            Prompt messages and description
        """
        self._ensure_initialized()

        if not self.server_capabilities.get("prompts"):
            raise RuntimeError("Server does not support prompts")

        response = await self._request(
            "prompts/get", {"name": name, "arguments": arguments or {}}
        )

        return response

    async def _request(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a request and wait for response"""
        request = JSONRPCMessage.request(method, params)
        response = await self.transport.send_request(request)

        # Check for error
        if "error" in response:
            raise MCPError(response["error"])

        return response.get("result", {})

    async def _notify(self, method: str, params: Optional[dict] = None):
        """Send a notification (no response expected)"""
        notification = JSONRPCMessage.notification(method, params)
        await self.transport.send_notification(notification)

    def _ensure_initialized(self):
        """Ensure the client is initialized"""
        if not self.initialized:
            raise RuntimeError("Client not initialized. Call initialize() first.")

    async def _handle_tools_changed(self, params: dict):
        """Handle tools list changed notification"""
        logger.info("Tools list changed on server")
        # In a real implementation, this might trigger a refresh of cached tools


# AGiXT Integration Helper
class AGiXTMCPAdapter:
    """
    Adapter to integrate MCP client with AGiXT's extension system
    """

    def __init__(self, user_api_key: Optional[str] = None):
        self.clients: Dict[str, MCPClient] = {}
        self.user_api_key = user_api_key

    async def connect_to_server(self, server_id: str, server_config: dict) -> MCPClient:
        """
        Connect to an MCP server

        Args:
            server_id: Unique identifier for this server connection
            server_config: Configuration including transport type and parameters
        """
        transport_type = TransportType(server_config.get("transport", "http"))

        if transport_type == TransportType.HTTP:
            client = MCPClient(
                transport_type,
                endpoint_url=server_config["endpoint_url"],
                auth_headers=server_config.get("auth_headers", {}),
            )
        elif transport_type == TransportType.STDIO:
            # Handle AGiXT integration for stdio transports (like browser-use)
            env = server_config.get("env", {}).copy()

            # Auto-configure browser-use to use AGiXT if it's a browser-use server
            if "browser-use" in server_config.get("command", "") and self.user_api_key:
                from Globals import getenv

                agixt_uri = getenv("AGIXT_URI", "http://localhost:7437")
                agent_name = server_config.get("agent_name", "gpt-4o")

                # Configure browser-use to use AGiXT as OpenAI-compatible provider
                env["OPENAI_API_KEY"] = self.user_api_key
                env["OPENAI_BASE_URL"] = f"{agixt_uri}/v1/mcp/"
                env["BROWSER_USE_MODEL"] = agent_name  # Use agent name as model

                # Optimal defaults for vision models
                env["BROWSER_USE_HEADLESS"] = "true"
                env["BROWSER_USE_VIEWPORT_WIDTH"] = "1280"
                env["BROWSER_USE_VIEWPORT_HEIGHT"] = "720"

                logger.info(f"Configured browser-use MCP server to use AGiXT:")
                logger.info(f"  - Base URL: {env['OPENAI_BASE_URL']}")
                logger.info(f"  - Model (Agent): {agent_name}")
                logger.info(f"  - Headless: true, Viewport: 1280x720")

            client = MCPClient(
                transport_type,
                command=server_config["command"],
                args=server_config.get("args", []),
                env=env,
            )
        else:
            raise ValueError(f"Unsupported transport: {transport_type}")

        await client.connect()
        await client.initialize()

        self.clients[server_id] = client
        return client

    async def execute_mcp_action(self, server_id: str, action: str, **kwargs) -> Any:
        """
        Execute an action on an MCP server

        Args:
            server_id: Server identifier
            action: Action to perform (list_tools, call_tool, etc.)
            **kwargs: Action-specific parameters
        """
        if server_id not in self.clients:
            raise ValueError(f"No client connected for server: {server_id}")

        client = self.clients[server_id]

        if action == "list_tools":
            return await client.list_tools()
        elif action == "call_tool":
            return await client.call_tool(
                name=kwargs["tool_name"], arguments=kwargs.get("arguments", {})
            )
        elif action == "list_resources":
            return await client.list_resources()
        elif action == "read_resource":
            return await client.read_resource(uri=kwargs["uri"])
        elif action == "list_prompts":
            return await client.list_prompts()
        elif action == "get_prompt":
            return await client.get_prompt(
                name=kwargs["prompt_name"], arguments=kwargs.get("arguments", {})
            )
        else:
            raise ValueError(f"Unknown action: {action}")

    async def disconnect_all(self):
        """Disconnect all MCP clients"""
        for client in self.clients.values():
            await client.disconnect()
        self.clients.clear()
