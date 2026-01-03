#!/usr/bin/env python3
"""
AGiXT MCP Server for Claude Code

This is a standalone MCP server that exposes AGiXT functionality to Claude Code.
It communicates via stdio using the Model Context Protocol.

Usage:
    python claude_code_mcp_server.py

Environment Variables:
    AGIXT_API_URL: AGiXT API base URL (default: http://localhost:7437)
    AGIXT_API_KEY: AGiXT API key for authentication
    AGIXT_AGENT_NAME: Default agent name to use (default: gpt4)
"""

import os
import sys
import json
import asyncio
import logging
from typing import Any, Sequence, Optional, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: MCP package not installed. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,  # Log to stderr to not interfere with stdio
)
logger = logging.getLogger("agixt-mcp-server")

# Configuration from environment
AGIXT_API_URL = os.getenv("AGIXT_API_URL", "http://localhost:7437")
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
AGIXT_AGENT_NAME = os.getenv("AGIXT_AGENT_NAME", "gpt4")
AGIXT_USER = os.getenv("AGIXT_USER", "")

# Server instance
server = Server("agixt-mcp-server")


# ==================== AGiXT Client ====================

class AGiXTMCPClient:
    """HTTP client for AGiXT API calls from the MCP server."""
    
    def __init__(self):
        self.base_url = AGIXT_API_URL.rstrip("/")
        self.api_key = AGIXT_API_KEY
        self.default_agent = AGIXT_AGENT_NAME
        self._session = None
    
    @property
    def headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                base_url=self.base_url,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=300),
            )
        return self._session
    
    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Any:
        session = await self._get_session()
        
        try:
            if method.upper() == "GET":
                async with session.get(endpoint, params=params) as response:
                    response.raise_for_status()
                    return await response.json() if response.content_length else None
            elif method.upper() == "POST":
                async with session.post(endpoint, json=data, params=params) as response:
                    response.raise_for_status()
                    return await response.json() if response.content_length else None
            elif method.upper() == "PUT":
                async with session.put(endpoint, json=data, params=params) as response:
                    response.raise_for_status()
                    return await response.json() if response.content_length else None
            elif method.upper() == "DELETE":
                async with session.delete(endpoint, params=params) as response:
                    response.raise_for_status()
                    return await response.json() if response.content_length else None
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise
    
    # Agent methods
    async def list_agents(self) -> List[Dict]:
        result = await self._request("GET", "/api/v1/agent")
        return result.get("agents", []) if isinstance(result, dict) else result or []
    
    async def get_agent(self, agent_name: str) -> Dict:
        return await self._request("GET", f"/api/v1/agent/{agent_name}")
    
    async def create_agent(self, agent_name: str, settings: Dict = None) -> Dict:
        return await self._request("POST", "/api/v1/agent", data={
            "agent_name": agent_name,
            "settings": settings or {},
        })
    
    async def delete_agent(self, agent_name: str) -> Dict:
        return await self._request("DELETE", f"/api/v1/agent/{agent_name}")
    
    async def get_agent_commands(self, agent_name: str) -> Dict:
        result = await self._request("GET", f"/api/v1/agent/{agent_name}/commands")
        return result.get("commands", {}) if isinstance(result, dict) else {}
    
    # Chat methods
    async def chat(
        self,
        agent_name: str,
        message: str,
        conversation_name: str = "-",
        **kwargs,
    ) -> str:
        data = {
            "model": agent_name,
            "messages": [{"role": "user", "content": message}],
            "user": conversation_name,
            **kwargs,
        }
        result = await self._request("POST", "/v1/chat/completions", data=data)
        if isinstance(result, dict) and "choices" in result:
            return result["choices"][0]["message"]["content"]
        return str(result)
    
    async def inference(
        self,
        agent_name: str,
        user_input: str,
        **kwargs,
    ) -> str:
        data = {"user_input": user_input, **kwargs}
        result = await self._request("POST", f"/api/v1/agent/{agent_name}/prompt", data=data)
        return result.get("response", str(result)) if isinstance(result, dict) else str(result)
    
    # Chain methods
    async def list_chains(self) -> List[Dict]:
        return await self._request("GET", "/api/v1/chains") or []
    
    async def get_chain(self, chain_name: str) -> Dict:
        return await self._request("GET", f"/api/v1/chain/{chain_name}")
    
    async def run_chain(self, chain_name: str, user_input: str, **kwargs) -> Any:
        data = {"chain_name": chain_name, "user_input": user_input, **kwargs}
        return await self._request("POST", f"/api/v1/chain/{chain_name}/run", data=data)
    
    # Memory methods
    async def query_memories(
        self,
        agent_name: str,
        query: str,
        collection_number: str = "0",
        limit: int = 10,
        min_relevance: float = 0.3,
    ) -> List[Dict]:
        # Get agent ID first
        agents = await self.list_agents()
        agent_id = None
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                break
        if not agent_id:
            return []
        
        result = await self._request(
            "POST",
            f"/api/v1/agent/{agent_id}/memory/{collection_number}/query",
            data={"user_input": query, "limit": limit, "min_relevance_score": min_relevance},
        )
        return result.get("memories", []) if isinstance(result, dict) else []
    
    async def add_memory(self, agent_name: str, text: str, collection_number: str = "0") -> Dict:
        agents = await self.list_agents()
        agent_id = None
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                break
        if not agent_id:
            raise Exception(f"Agent '{agent_name}' not found")
        
        return await self._request(
            "POST",
            f"/api/v1/agent/{agent_id}/memory/{collection_number}/text",
            data={"user_input": text},
        )
    
    async def learn_url(self, agent_name: str, url: str, collection_number: str = "0") -> Dict:
        agents = await self.list_agents()
        agent_id = None
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                break
        if not agent_id:
            raise Exception(f"Agent '{agent_name}' not found")
        
        return await self._request(
            "POST",
            f"/api/v1/agent/{agent_id}/memory/{collection_number}/url",
            data={"url": url},
        )
    
    # Conversation methods
    async def list_conversations(self, agent_name: str) -> List[Dict]:
        agents = await self.list_agents()
        agent_id = None
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                break
        if not agent_id:
            return []
        
        result = await self._request("GET", f"/api/v1/agent/{agent_id}/conversations")
        return result.get("conversations", []) if isinstance(result, dict) else result or []
    
    async def get_conversation(
        self,
        agent_name: str,
        conversation_name: str,
        limit: int = 100,
    ) -> List[Dict]:
        agents = await self.list_agents()
        agent_id = None
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                break
        if not agent_id:
            return []
        
        result = await self._request(
            "GET",
            f"/api/v1/agent/{agent_id}/conversation",
            params={"conversation_name": conversation_name, "limit": limit},
        )
        return result.get("history", []) if isinstance(result, dict) else result or []
    
    async def delete_conversation(self, agent_name: str, conversation_name: str) -> Dict:
        agents = await self.list_agents()
        agent_id = None
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
                break
        if not agent_id:
            raise Exception(f"Agent '{agent_name}' not found")
        
        return await self._request(
            "DELETE",
            f"/api/v1/agent/{agent_id}/conversation",
            params={"conversation_name": conversation_name},
        )
    
    # Command methods
    async def execute_command(
        self,
        agent_name: str,
        command_name: str,
        command_args: Dict = None,
        conversation_name: str = "-",
    ) -> Any:
        return await self._request(
            "POST",
            f"/api/v1/agent/{agent_name}/command",
            data={
                "command_name": command_name,
                "command_args": command_args or {},
                "conversation_name": conversation_name,
            },
        )
    
    # Prompt methods
    async def list_prompts(self, category: str = "Default") -> List[str]:
        result = await self._request("GET", "/api/v1/prompts", params={"prompt_category": category})
        return result.get("prompts", []) if isinstance(result, dict) else result or []
    
    async def get_prompt(self, prompt_name: str, category: str = "Default") -> Dict:
        return await self._request("GET", f"/api/v1/prompt/{category}/{prompt_name}")
    
    # Provider methods
    async def list_providers(self) -> List[str]:
        result = await self._request("GET", "/api/v1/providers")
        return result.get("providers", []) if isinstance(result, dict) else result or []


# Global client instance
_client: Optional[AGiXTMCPClient] = None


def get_client() -> AGiXTMCPClient:
    global _client
    if _client is None:
        _client = AGiXTMCPClient()
    return _client


# ==================== Tool Definitions ====================

TOOLS = [
    # Agent Tools
    Tool(
        name="agixt_list_agents",
        description="List all available AGiXT agents with their IDs and names.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="agixt_get_agent",
        description="Get configuration and settings for a specific AGiXT agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name of the agent"},
            },
            "required": ["agent_name"],
        },
    ),
    Tool(
        name="agixt_create_agent",
        description="Create a new AGiXT agent with specified settings.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name for the new agent"},
                "provider": {"type": "string", "description": "AI provider (e.g., openai, anthropic)", "default": "gpt4free"},
                "model": {"type": "string", "description": "Model to use", "default": "gpt-4"},
            },
            "required": ["agent_name"],
        },
    ),
    Tool(
        name="agixt_delete_agent",
        description="Delete an existing AGiXT agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name of the agent to delete"},
            },
            "required": ["agent_name"],
        },
    ),
    Tool(
        name="agixt_get_agent_commands",
        description="Get available commands for an AGiXT agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name of the agent"},
            },
            "required": ["agent_name"],
        },
    ),
    
    # Chat Tools
    Tool(
        name="agixt_chat",
        description="Send a message to an AGiXT agent and get a response. This is the primary way to interact with agents.",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to send to the agent"},
                "agent_name": {"type": "string", "description": "Agent to chat with (uses default if not specified)"},
                "conversation_name": {"type": "string", "description": "Conversation context name", "default": "-"},
                "context_results": {"type": "integer", "description": "Number of memory results to include", "default": 5},
                "browse_links": {"type": "boolean", "description": "Whether to browse URLs in the message", "default": False},
                "websearch": {"type": "boolean", "description": "Whether to perform web searches", "default": False},
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="agixt_inference",
        description="Run advanced inference with custom prompts, memory injection, and fine-grained control.",
        inputSchema={
            "type": "object",
            "properties": {
                "user_input": {"type": "string", "description": "Input for the agent"},
                "agent_name": {"type": "string", "description": "Agent name"},
                "prompt_category": {"type": "string", "description": "Prompt template category", "default": "Default"},
                "prompt_name": {"type": "string", "description": "Prompt template name", "default": "Custom Input"},
                "conversation_name": {"type": "string", "description": "Conversation context", "default": "-"},
                "context_results": {"type": "integer", "description": "Number of memory results", "default": 100},
            },
            "required": ["user_input"],
        },
    ),
    
    # Chain Tools
    Tool(
        name="agixt_list_chains",
        description="List all available AGiXT chains (multi-step automation workflows).",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="agixt_get_chain",
        description="Get details of a specific chain including all steps.",
        inputSchema={
            "type": "object",
            "properties": {
                "chain_name": {"type": "string", "description": "Name of the chain"},
            },
            "required": ["chain_name"],
        },
    ),
    Tool(
        name="agixt_run_chain",
        description="Execute an AGiXT chain with input. Chains can perform complex multi-step tasks.",
        inputSchema={
            "type": "object",
            "properties": {
                "chain_name": {"type": "string", "description": "Name of the chain to run"},
                "user_input": {"type": "string", "description": "Input for the chain"},
                "agent_name": {"type": "string", "description": "Agent override for all steps"},
                "conversation_name": {"type": "string", "description": "Conversation context", "default": "-"},
                "all_responses": {"type": "boolean", "description": "Return all step responses", "default": False},
            },
            "required": ["chain_name", "user_input"],
        },
    ),
    
    # Memory Tools
    Tool(
        name="agixt_query_memories",
        description="Query an agent's memories using semantic search.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "agent_name": {"type": "string", "description": "Agent whose memories to search"},
                "collection_number": {"type": "string", "description": "Memory collection (0-5)", "default": "0"},
                "limit": {"type": "integer", "description": "Maximum results", "default": 10},
                "min_relevance": {"type": "number", "description": "Minimum similarity score (0-1)", "default": 0.3},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="agixt_add_memory",
        description="Add new information to an agent's memory/knowledge base.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to add to memory"},
                "agent_name": {"type": "string", "description": "Agent name"},
                "collection_number": {"type": "string", "description": "Memory collection", "default": "0"},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="agixt_learn_url",
        description="Have an agent learn and memorize content from a URL.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to learn from"},
                "agent_name": {"type": "string", "description": "Agent name"},
                "collection_number": {"type": "string", "description": "Memory collection", "default": "0"},
            },
            "required": ["url"],
        },
    ),
    
    # Conversation Tools
    Tool(
        name="agixt_list_conversations",
        description="List all conversations for an agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent name"},
            },
            "required": [],
        },
    ),
    Tool(
        name="agixt_get_conversation",
        description="Get message history for a conversation.",
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_name": {"type": "string", "description": "Conversation name"},
                "agent_name": {"type": "string", "description": "Agent name"},
                "limit": {"type": "integer", "description": "Maximum messages", "default": 100},
            },
            "required": ["conversation_name"],
        },
    ),
    Tool(
        name="agixt_delete_conversation",
        description="Delete a conversation and its history.",
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_name": {"type": "string", "description": "Conversation to delete"},
                "agent_name": {"type": "string", "description": "Agent name"},
            },
            "required": ["conversation_name"],
        },
    ),
    
    # Command Tools
    Tool(
        name="agixt_execute_command",
        description="Execute a specific command on an AGiXT agent (web search, file ops, API calls, etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "command_name": {"type": "string", "description": "Command to execute"},
                "command_args": {"type": "object", "description": "Command arguments", "default": {}},
                "agent_name": {"type": "string", "description": "Agent name"},
                "conversation_name": {"type": "string", "description": "Conversation context", "default": "-"},
            },
            "required": ["command_name"],
        },
    ),
    
    # Prompt & Provider Tools
    Tool(
        name="agixt_list_prompts",
        description="List available prompt templates.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Prompt category", "default": "Default"},
            },
            "required": [],
        },
    ),
    Tool(
        name="agixt_get_prompt",
        description="Get a specific prompt template.",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt_name": {"type": "string", "description": "Prompt name"},
                "category": {"type": "string", "description": "Prompt category", "default": "Default"},
            },
            "required": ["prompt_name"],
        },
    ),
    Tool(
        name="agixt_list_providers",
        description="List available AI providers.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
    client = get_client()
    default_agent = AGIXT_AGENT_NAME
    
    def get_agent(args: dict) -> str:
        return args.get("agent_name") or default_agent
    
    try:
        result = None
        
        # Agent Tools
        if name == "agixt_list_agents":
            agents = await client.list_agents()
            result = {"agents": agents, "count": len(agents)}
        
        elif name == "agixt_get_agent":
            result = await client.get_agent(arguments["agent_name"])
        
        elif name == "agixt_create_agent":
            settings = {
                "provider": arguments.get("provider", "gpt4free"),
                "AI_MODEL": arguments.get("model", "gpt-4"),
            }
            result = await client.create_agent(arguments["agent_name"], settings)
        
        elif name == "agixt_delete_agent":
            result = await client.delete_agent(arguments["agent_name"])
        
        elif name == "agixt_get_agent_commands":
            result = await client.get_agent_commands(arguments["agent_name"])
        
        # Chat Tools
        elif name == "agixt_chat":
            response = await client.chat(
                agent_name=get_agent(arguments),
                message=arguments["message"],
                conversation_name=arguments.get("conversation_name", "-"),
                context_results=arguments.get("context_results", 5),
                browse_links=arguments.get("browse_links", False),
                websearch=arguments.get("websearch", False),
            )
            result = {"agent": get_agent(arguments), "response": response}
        
        elif name == "agixt_inference":
            response = await client.inference(
                agent_name=get_agent(arguments),
                user_input=arguments["user_input"],
                prompt_category=arguments.get("prompt_category", "Default"),
                prompt_name=arguments.get("prompt_name", "Custom Input"),
                conversation_name=arguments.get("conversation_name", "-"),
                context_results=arguments.get("context_results", 100),
            )
            result = {"agent": get_agent(arguments), "response": response}
        
        # Chain Tools
        elif name == "agixt_list_chains":
            chains = await client.list_chains()
            result = {"chains": chains, "count": len(chains)}
        
        elif name == "agixt_get_chain":
            result = await client.get_chain(arguments["chain_name"])
        
        elif name == "agixt_run_chain":
            response = await client.run_chain(
                chain_name=arguments["chain_name"],
                user_input=arguments["user_input"],
                agent_override=arguments.get("agent_name", ""),
                conversation_name=arguments.get("conversation_name", "-"),
                all_responses=arguments.get("all_responses", False),
            )
            result = {"chain_name": arguments["chain_name"], "result": response}
        
        # Memory Tools
        elif name == "agixt_query_memories":
            memories = await client.query_memories(
                agent_name=get_agent(arguments),
                query=arguments["query"],
                collection_number=arguments.get("collection_number", "0"),
                limit=arguments.get("limit", 10),
                min_relevance=arguments.get("min_relevance", 0.3),
            )
            result = {"query": arguments["query"], "memories": memories, "count": len(memories)}
        
        elif name == "agixt_add_memory":
            response = await client.add_memory(
                agent_name=get_agent(arguments),
                text=arguments["text"],
                collection_number=arguments.get("collection_number", "0"),
            )
            result = {"message": "Memory added", "result": response}
        
        elif name == "agixt_learn_url":
            response = await client.learn_url(
                agent_name=get_agent(arguments),
                url=arguments["url"],
                collection_number=arguments.get("collection_number", "0"),
            )
            result = {"message": f"Learning from URL: {arguments['url']}", "result": response}
        
        # Conversation Tools
        elif name == "agixt_list_conversations":
            conversations = await client.list_conversations(get_agent(arguments))
            result = {"conversations": conversations, "count": len(conversations)}
        
        elif name == "agixt_get_conversation":
            history = await client.get_conversation(
                agent_name=get_agent(arguments),
                conversation_name=arguments["conversation_name"],
                limit=arguments.get("limit", 100),
            )
            result = {"conversation_name": arguments["conversation_name"], "history": history}
        
        elif name == "agixt_delete_conversation":
            response = await client.delete_conversation(
                agent_name=get_agent(arguments),
                conversation_name=arguments["conversation_name"],
            )
            result = {"message": f"Conversation '{arguments['conversation_name']}' deleted", "result": response}
        
        # Command Tools
        elif name == "agixt_execute_command":
            response = await client.execute_command(
                agent_name=get_agent(arguments),
                command_name=arguments["command_name"],
                command_args=arguments.get("command_args", {}),
                conversation_name=arguments.get("conversation_name", "-"),
            )
            result = {"command": arguments["command_name"], "result": response}
        
        # Prompt & Provider Tools
        elif name == "agixt_list_prompts":
            prompts = await client.list_prompts(arguments.get("category", "Default"))
            result = {"prompts": prompts, "count": len(prompts)}
        
        elif name == "agixt_get_prompt":
            result = await client.get_prompt(
                arguments["prompt_name"],
                arguments.get("category", "Default"),
            )
        
        elif name == "agixt_list_providers":
            providers = await client.list_providers()
            result = {"providers": providers, "count": len(providers)}
        
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    
    except Exception as e:
        logger.error(f"Tool '{name}' failed: {e}")
        return [TextContent(type="text", text=json.dumps({
            "error": True,
            "message": str(e),
            "tool": name,
        }, indent=2))]


async def run_server():
    logger.info("Starting AGiXT MCP Server...")
    logger.info(f"API URL: {AGIXT_API_URL}")
    logger.info(f"Default Agent: {AGIXT_AGENT_NAME}")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
