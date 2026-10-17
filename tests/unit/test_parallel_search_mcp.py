"""Exercise the example through the real MCP client and an HTTP server."""

import asyncio
import contextlib
import io
import os
import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web

from agixt.mcp_client import MCPClient, MCPError
from examples import parallel_search_mcp as example


class ParallelMCPExampleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.clients = []
        self.mode = "normal"
        self.call_started = asyncio.Event()
        self.release_call = asyncio.Event()
        app = web.Application()
        app.router.add_post("/mcp", self.handle_request)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.endpoint = f"http://127.0.0.1:{port}/mcp"

        def make_client(*args, **kwargs):
            client = MCPClient(*args, **kwargs)
            self.clients.append(client)
            return client

        self.endpoint_patch = patch.object(example, "ENDPOINT", self.endpoint)
        self.client_patch = patch.object(example, "MCPClient", make_client)
        self.env_patch = patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "",
                "http_proxy": "",
                "https_proxy": "",
                "NO_PROXY": "127.0.0.1",
                "no_proxy": "127.0.0.1",
            },
        )
        self.env_patch.start()
        self.endpoint_patch.start()
        self.client_patch.start()

    async def asyncTearDown(self):
        self.release_call.set()
        self.client_patch.stop()
        self.endpoint_patch.stop()
        self.env_patch.stop()
        await self.runner.cleanup()

    async def handle_request(self, request):
        payload = await request.json()
        self.requests.append((str(request.url), dict(request.headers), payload))
        method = payload["method"]
        if method == "notifications/initialized":
            return web.Response(status=202)
        if method == "initialize":
            result = {"capabilities": {"tools": {"listChanged": False}}}
        elif method == "tools/list":
            names = [] if self.mode == "missing" else ["web_search", "web_fetch"]
            result = {"tools": [{"name": name} for name in names]}
        elif method == "tools/call":
            self.call_started.set()
            if self.mode == "wait":
                await self.release_call.wait()
            if self.mode == "http_error":
                return web.Response(status=503)
            if self.mode == "rpc_error":
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": payload["id"],
                        "error": {"code": -32602, "message": "Invalid arguments"},
                    }
                )
            text = (
                "Quota exceeded; retry later"
                if self.mode == "tool_error"
                else '{"results":[{"url":"https://example.org","excerpts":["Useful page text"]}]}'
            )
            result = {
                "content": [{"type": "text", "text": text}],
                "isError": self.mode == "tool_error",
            }
        else:
            raise AssertionError(method)
        return web.json_response(
            {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        )

    def assert_closed(self):
        self.assertTrue(self.clients[-1].transport.session.closed)

    async def test_search_and_fetch_use_real_client_and_print_content(self):
        for name, arguments in [
            (
                "web_search",
                {
                    "objective": "Find AGiXT setup instructions",
                    "search_queries": ["AGiXT installation Python Docker"],
                    "session_id": "example-test-session",
                },
            ),
            (
                "web_fetch",
                {
                    "urls": ["https://example.org"],
                    "objective": "Read setup instructions",
                    "session_id": "example-test-session",
                },
            ),
        ]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                await example.run(name, arguments)
            self.assertIn("Useful page text", output.getvalue())
            self.assertIn("https://example.org", output.getvalue())
            self.assert_closed()
            self.assertTrue(self.clients[-1].transport.session.trust_env)
            self.assertEqual(
                self.requests[-1][2]["params"], {"name": name, "arguments": arguments}
            )
        for url, headers, _ in self.requests:
            self.assertEqual(url, self.endpoint)
            self.assertEqual(headers["User-Agent"], example.USER_AGENT)
            self.assertEqual(headers["Accept"], "application/json, text/event-stream")
            self.assertNotIn("Authorization", headers)
            self.assertNotIn("x-api-key", {k.lower(): v for k, v in headers.items()})
        self.assertEqual(
            [r[2]["method"] for r in self.requests[:4]],
            ["initialize", "notifications/initialized", "tools/list", "tools/call"],
        )

    async def test_existing_client_keeps_proxy_default(self):
        client = MCPClient(example.TransportType.HTTP, endpoint_url=self.endpoint)
        try:
            await client.connect()
            self.assertFalse(client.transport.session.trust_env)
        finally:
            await client.disconnect()

    async def test_proxy_environment_is_used_when_opted_in(self):
        # The deliberately unresolvable destination can only reach our server
        # through the configured HTTP proxy.
        remote_url = "http://mcp.example.invalid/mcp"
        with patch.object(example, "ENDPOINT", remote_url), patch.dict(
            os.environ, {"http_proxy": self.endpoint, "no_proxy": ""}
        ), contextlib.redirect_stdout(io.StringIO()):
            await example.run("web_search", {})
        self.assertEqual(len(self.requests), 4)
        self.assertTrue(all(url == remote_url for url, _, _ in self.requests))
        self.assert_closed()

    async def test_missing_tool_is_rejected_before_dispatch(self):
        self.mode = "missing"
        with self.assertRaisesRegex(RuntimeError, "does not advertise web_search"):
            await example.run("web_search", {})
        self.assertFalse(self.call_started.is_set())
        self.assert_closed()

    async def test_http_and_protocol_errors_close_connection(self):
        for mode, error in [
            ("http_error", aiohttp.ClientResponseError),
            ("rpc_error", MCPError),
        ]:
            self.mode = mode
            with self.assertRaises(error):
                await example.run("web_search", {})
            self.assert_closed()

    async def test_tool_error_text_is_preserved(self):
        self.mode = "tool_error"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            await example.run("web_search", {})
        self.assertEqual(output.getvalue(), "Quota exceeded; retry later\n")
        self.assert_closed()

    async def test_timeout_closes_connection(self):
        self.mode = "wait"
        task = asyncio.create_task(example.run("web_search", {}, timeout=0.2))
        await asyncio.wait_for(self.call_started.wait(), timeout=2)
        with self.assertRaises(asyncio.TimeoutError):
            await task
        self.assert_closed()

    async def test_cancellation_closes_connection(self):
        self.mode = "wait"
        task = asyncio.create_task(example.run("web_search", {}))
        await asyncio.wait_for(self.call_started.wait(), timeout=2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_closed()
