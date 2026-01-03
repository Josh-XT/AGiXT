"""
MCP Tool Executor for Claude Code Hub

This module provides the tool execution logic that can be run either
directly or inside a safeexecute sandbox container. It contains all
the MCP tools available to Claude Code users.
"""

import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# Tool definitions
TOOLS = {
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
        headers = {
            "Content-Type": "application/json",
        }
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
    
    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool and return the result"""
        
        # Get agent name from arguments or use default
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
    
    async def _chat(
        self,
        message: str,
        agent_name: str,
        conversation_name: str = None,
    ) -> Dict:
        """Send a chat message"""
        data = {
            "user_input": message,
            "prompt_category": "Default",
            "prompt_name": "Chat",
        }
        
        if conversation_name:
            data["conversation_name"] = conversation_name
        
        return await self._request(
            "POST",
            f"/v1/agent/{agent_name}/prompt",
            data=data,
        )
    
    async def _inference(
        self,
        user_input: str,
        agent_name: str,
        prompt_category: str,
        prompt_name: str,
        collection: int,
    ) -> Dict:
        """Run inference with specific settings"""
        data = {
            "user_input": user_input,
            "prompt_category": prompt_category,
            "prompt_name": prompt_name,
            "inject_memories_from_collection_number": collection,
        }
        
        return await self._request(
            "POST",
            f"/v1/agent/{agent_name}/prompt",
            data=data,
        )
    
    async def _run_chain(
        self,
        chain_name: str,
        user_input: str,
        agent_name: str,
        chain_args: Dict,
    ) -> Dict:
        """Run a chain"""
        data = {
            "prompt": user_input,
            "agent_override": agent_name,
            "chain_args": chain_args,
        }
        
        return await self._request(
            "POST",
            f"/v1/chain/{chain_name}/run",
            data=data,
        )
    
    async def _query_memories(
        self,
        query: str,
        agent_name: str,
        collection: int,
        limit: int,
    ) -> Dict:
        """Query agent memories"""
        data = {
            "user_input": query,
            "limit": limit,
            "min_relevance_score": 0.0,
        }
        
        return await self._request(
            "POST",
            f"/v1/agent/{agent_name}/memory/{collection}/query",
            data=data,
        )
    
    async def _add_memory(
        self,
        text: str,
        agent_name: str,
        collection: int,
    ) -> Dict:
        """Add a memory"""
        data = {
            "text": text,
        }
        
        return await self._request(
            "POST",
            f"/v1/agent/{agent_name}/memory/{collection}/add",
            data=data,
        )
    
    async def _learn_url(
        self,
        url: str,
        agent_name: str,
        collection: int,
    ) -> Dict:
        """Learn from a URL"""
        data = {
            "url": url,
            "collection_number": collection,
        }
        
        return await self._request(
            "POST",
            f"/v1/agent/{agent_name}/learn/url",
            data=data,
        )
    
    async def _get_conversation(
        self,
        conversation_name: str,
        agent_name: str,
        limit: int,
    ) -> Dict:
        """Get conversation history"""
        return await self._request(
            "GET",
            f"/v1/conversation/{agent_name}/{conversation_name}",
            params={"limit": limit},
        )
    
    async def _execute_command(
        self,
        command_name: str,
        command_args: Dict,
        agent_name: str,
    ) -> Dict:
        """Execute an agent command"""
        data = {
            "command_name": command_name,
            "command_args": command_args,
        }
        
        return await self._request(
            "POST",
            f"/v1/agent/{agent_name}/command",
            data=data,
        )


# Module-level function for use by safeexecute
async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    agent_name: str = None,
    api_url: str = None,
    api_key: str = None,
) -> Dict[str, Any]:
    """
    Execute an MCP tool.
    
    This function can be called directly or from a safeexecute sandbox.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        agent_name: Override agent name
        api_url: Override API URL
        api_key: Override API key
    
    Returns:
        Tool execution result
    """
    executor = MCPToolExecutor(
        api_url=api_url,
        api_key=api_key,
        agent_name=agent_name,
    )
    
    return await executor.execute(tool_name, arguments)


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
        for name, info in TOOLS.items()
    ]


# CLI entry point for testing
if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) < 2:
            print("Available tools:")
            for name, info in TOOLS.items():
                print(f"  {name}: {info['description']}")
            return
        
        tool_name = sys.argv[1]
        arguments = {}
        
        if len(sys.argv) > 2:
            try:
                arguments = json.loads(sys.argv[2])
            except:
                print("Arguments must be valid JSON")
                return
        
        result = await execute_tool(tool_name, arguments)
        print(json.dumps(result, indent=2, default=str))
    
    asyncio.run(main())
