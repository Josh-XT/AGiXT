"""
Example of using the proper MCP client with AGiXT
"""

import asyncio
from agixtsdk import AGiXTSDK


async def main():
    # Initialize AGiXT SDK
    sdk = AGiXTSDK(base_uri="http://localhost:7437", api_key="your-api-key")

    # Example 1: List tools from an MCP server
    print("=== Listing MCP Tools ===")
    result = await sdk.execute_command(
        agent_name="your-agent",
        command_name="Use MCP Server",
        command_args={
            "endpoint_url": "https://example-mcp-server.com/rpc",
            "api_key": "your-mcp-api-key",
            "action": "list_tools",
        },
    )
    print(result)

    # Example 2: Call a specific tool
    print("\n=== Calling MCP Tool ===")
    result = await sdk.execute_command(
        agent_name="your-agent",
        command_name="Use MCP Server",
        command_args={
            "endpoint_url": "https://example-mcp-server.com/rpc",
            "api_key": "your-mcp-api-key",
            "action": "call_tool",
            "tool_name": "weather/current",
            "tool_arguments": '{"location": "San Francisco", "units": "fahrenheit"}',
        },
    )
    print(result)

    # Example 3: List available resources
    print("\n=== Listing MCP Resources ===")
    result = await sdk.execute_command(
        agent_name="your-agent",
        command_name="Use MCP Server",
        command_args={
            "endpoint_url": "https://example-mcp-server.com/rpc",
            "api_key": "your-mcp-api-key",
            "action": "list_resources",
        },
    )
    print(result)

    # Example 4: Read a specific resource
    print("\n=== Reading MCP Resource ===")
    result = await sdk.execute_command(
        agent_name="your-agent",
        command_name="Use MCP Server",
        command_args={
            "endpoint_url": "https://example-mcp-server.com/rpc",
            "api_key": "your-mcp-api-key",
            "action": "read_resource",
            "resource_uri": "file:///docs/api-guide.md",
        },
    )
    print(result)

    # Example 5: Using a local MCP server with stdio transport
    print("\n=== Using Local MCP Server (stdio) ===")
    # This would require modifying the mcp_client function to support stdio transport
    # For now, this is just a conceptual example


if __name__ == "__main__":
    asyncio.run(main())
