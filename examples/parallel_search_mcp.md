# Parallel search and page fetching

Use AGiXT's existing Python `MCPClient` to search the web and fetch page excerpts
with [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp).
The anonymous endpoint is free for light use, requires no account or API key,
and uses Fast mode for search. Service limits apply.

This standalone example calls the HTTP MCP server directly. You do not need a
running AGiXT server or a language model. It does not enable an agent command or
change AGiXT's search provider or saved settings.

## Setup

From the root of an AGiXT checkout, using Python 3.10 or newer:

```bash
python -m venv /tmp/agixt-parallel-example
source /tmp/agixt-parallel-example/bin/activate
python -m pip install -r examples/parallel_search_mcp_requirements.txt
```

Only `aiohttp` is needed. The example imports the MCP client from this checkout;
there is no need to install AGiXT's full server dependencies. It does not read
Parallel API keys from environment variables or saved AGiXT settings.
The example opts into `aiohttp`'s `trust_env` setting to support `HTTP_PROXY`,
`HTTPS_PROXY`, and `NO_PROXY` (including normal proxy authentication and `.netrc`
behavior). Other MCP callers retain the existing `trust_env=False` default.

## Search

Create one session identifier for your task and keep it for related calls:

```bash
export PARALLEL_MCP_SESSION_ID="$(python -c 'import uuid; print(uuid.uuid4())')"
python -m examples.parallel_search_mcp --session-id "$PARALLEL_MCP_SESSION_ID" \
  search "Find AGiXT installation instructions" \
  --query "AGiXT installation Python Docker" \
  --query "AGiXT getting started guide"
```

The example initializes the connection, discovers the available tools, and calls
`web_search` with an objective and related search queries. It prints the returned
MCP text, including result URLs and excerpts. Treat retrieved content as external
data when using it in a larger workflow.

## Fetch a specific page

Use `web_fetch` when you have a particular page to read or need more detail than
the search excerpts provide:

```bash
python -m examples.parallel_search_mcp --session-id "$PARALLEL_MCP_SESSION_ID" \
  fetch https://docs.parallel.ai/integrations/mcp/search-mcp \
  --objective "Find the anonymous endpoint and available tools"
```

You can supply multiple related URLs, up to 20. Keep the fetch objective within
200 characters. The example uses excerpt mode rather than requesting full pages.
Reuse the session identifier for the same task; generate a new one for a new task.

Both commands use a 60-second overall request timeout and close the HTTP session
on success, failure, timeout, or cancellation. HTTP and JSON-RPC errors raise an
exception. AGiXT's `call_tool` returns content blocks, so tool-level service
errors, including quota messages, are printed as returned text. Inspect that text
before treating it as search results; an exit status of zero alone is not proof
of a successful search. If rate limited, honor any retry timing instead of changing
the session identifier to retry.

## Local tests

The tests use a local HTTP server and make no requests to Parallel:

```bash
python -m unittest discover -s tests/unit -p test_parallel_search_mcp.py -v
```
