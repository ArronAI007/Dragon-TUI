"""SSE transport for MCP — connects to a remote MCP server via HTTP SSE.

Protocol (MCP 2024-11-05):
    1. GET to server URL → SSE stream
    2. Server sends 'endpoint' event with POST URL
    3. Client POSTs JSON-RPC to that endpoint
    4. Server sends responses back through the SSE stream

Usage:
    transport = SSETransport("https://mcp.example.com/sse", headers={...})
    await transport.start()
    result = await transport.request("tools/list", {})
    await transport.close()
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx


class SSETransport:
    """HTTP SSE-based MCP transport for remote servers."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self._http: httpx.AsyncClient | None = None
        self._message_endpoint: str = ""
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._sse_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Open SSE connection and discover the message endpoint."""
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            headers=self.headers,
        )

        # ── Phase 1: open SSE stream, read endpoint event ──
        endpoint = ""
        async with self._http.stream("GET", self.url) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("event: ") and line[7:].strip() == "endpoint":
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    # The endpoint event's data is a URL path
                    if endpoint == "":
                        endpoint = data.strip()
                        # Resolve relative URL
                        if endpoint.startswith("/"):
                            from urllib.parse import urlparse
                            parsed = urlparse(self.url)
                            endpoint = f"{parsed.scheme}://{parsed.netloc}{endpoint}"
                        self._message_endpoint = endpoint
                        break
                # Some servers send endpoint as a single SSE event with both lines
                if line.startswith("event: endpoint"):
                    continue

        if not self._message_endpoint:
            raise RuntimeError("MCP SSE server did not provide an endpoint URL")

        # ── Phase 2: restart SSE stream for message delivery ──
        self._sse_task = asyncio.create_task(self._read_sse())

    async def request(self, method: str, params: dict | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response via SSE."""
        async with self._lock:
            self._request_id += 1
            rid = self._request_id
            payload = {
                "jsonrpc": "2.0",
                "id": rid,
                "method": method,
                "params": params or {},
            }

            # Create a future to receive the response
            future: asyncio.Future = asyncio.get_event_loop().create_future()
            self._pending[rid] = future

            try:
                # POST to message endpoint
                if self._http is None:
                    raise RuntimeError("Transport not started")
                resp = await self._http.post(
                    self._message_endpoint,
                    content=json.dumps(payload, ensure_ascii=False),
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()

                # Wait for the response to arrive via SSE
                result = await asyncio.wait_for(future, timeout=30)
                return result

            finally:
                self._pending.pop(rid, None)

    async def notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if self._http is None:
            raise RuntimeError("Transport not started")
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        async with self._lock:
            await self._http.post(
                self._message_endpoint,
                content=json.dumps(payload, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
            )

    async def close(self) -> None:
        """Close the SSE connection and HTTP client."""
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
            self._sse_task = None

        # Reject all pending futures
        for rid, future in self._pending.items():
            if not future.done():
                future.set_exception(RuntimeError("Transport closed"))

        if self._http:
            await self._http.aclose()
            self._http = None

    # ── SSE reader ───────────────────────────────────────

    async def _read_sse(self) -> None:
        """Background task: read SSE events and route responses."""
        if self._http is None:
            return

        try:
            async with self._http.stream("GET", self.url) as response:
                response.raise_for_status()
                current_event: str | None = None
                current_data: str = ""

                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        current_data = line[6:]
                    elif line == "" and current_data:
                        # End of SSE event
                        await self._handle_sse_event(current_event, current_data)
                        current_event = None
                        current_data = ""

        except asyncio.CancelledError:
            raise
        except Exception:
            # SSE stream ended — reject remaining pending futures
            for rid, future in list(self._pending.items()):
                if not future.done():
                    future.set_exception(RuntimeError("SSE stream closed"))
            self._pending.clear()

    async def _handle_sse_event(self, event_name: str | None, data: str) -> None:
        """Route an SSE event to the appropriate pending future."""
        if event_name == "endpoint":
            # Endpoint updates — ignore after initial handshake
            return

        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return

        if not isinstance(msg, dict):
            return

        if "error" in msg:
            err = msg["error"]
            exc = RuntimeError(
                f"MCP error {err.get('code', '')}: {err.get('message', 'unknown')}"
            )
            rid = msg.get("id")
            if rid is not None and rid in self._pending:
                self._pending[rid].set_exception(exc)
            return

        rid = msg.get("id")
        if rid is not None and rid in self._pending:
            result = msg.get("result", msg)
            self._pending[rid].set_result(result)
