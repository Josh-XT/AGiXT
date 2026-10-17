"""Search or fetch pages with AGiXT's MCP client. See parallel_search_mcp.md."""

import argparse
import asyncio

from agixt.mcp_client import MCPClient, TransportType

ENDPOINT = "https://search.parallel.ai/mcp"
USER_AGENT = "AGiXT-Parallel-MCP-Example/1.0"


async def run(tool_name, arguments, timeout=60):
    """Print the tool's text content and close the connection on every exit path."""
    client = MCPClient(
        TransportType.HTTP,
        endpoint_url=ENDPOINT,
        trust_env=True,
        auth_headers={
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        },
    )

    async def call():
        await client.connect()
        await client.initialize()
        tools = await client.list_tools()
        if tool_name not in {tool["name"] for tool in tools}:
            raise RuntimeError(f"Server does not advertise {tool_name}")
        return await client.call_tool(tool_name, arguments)

    try:
        content = await asyncio.wait_for(call(), timeout=timeout)
        for block in content:
            if block.get("type") == "text":
                print(block["text"])
    finally:
        await client.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id",
        required=True,
        help="Reuse one UUID across search and fetch calls for the same task",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    search = subparsers.add_parser("search", help="Search for current information")
    search.add_argument("objective")
    search.add_argument("--query", action="append", required=True)
    fetch = subparsers.add_parser("fetch", help="Extract relevant text from URLs")
    fetch.add_argument("urls", nargs="+")
    fetch.add_argument("--objective", default="Extract the main content of these pages")
    args = parser.parse_args()

    arguments = {"session_id": args.session_id}
    if args.action == "search":
        tool_name = "web_search"
        arguments.update(objective=args.objective, search_queries=args.query)
    else:
        tool_name = "web_fetch"
        arguments.update(urls=args.urls, objective=args.objective)
    asyncio.run(run(tool_name, arguments))


if __name__ == "__main__":
    main()
