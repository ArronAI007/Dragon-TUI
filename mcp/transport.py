"""Stdio transport for MCP — manages a subprocess with JSON-RPC over stdin/stdout.

Each message is a single JSON line terminated by newline.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any


class StdioTransport:
    """Manages a long-running subprocess for MCP communication.

    Usage:
        transport = StdioTransport("npx", ["-y", "mcp-server-fetch"])
        await transport.start()
        result = await transport.request("tools/list", {})
        await transport.close()
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Launch the subprocess."""
        merged_env = {**os.environ, **self.env}
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )

    async def request(self, method: str, params: dict | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result.

        Raises:
            RuntimeError: on transport failure or error response.
        """
        async with self._lock:
            self._request_id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params or {},
            }
            return await self._send_recv(payload)

    async def notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        async with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
            await self._send_only(payload)

    async def close(self) -> None:
        """Terminate the subprocess."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None

    # ── Internals ───────────────────────────────────────

    async def _send_recv(self, payload: dict) -> dict[str, Any]:
        """Send payload, read exactly one JSON-line response."""
        await self._send_only(payload)
        return await self._recv()

    async def _send_only(self, payload: dict) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Transport not started")
        msg = json.dumps(payload, ensure_ascii=False) + "\n"
        self._process.stdin.write(msg.encode())
        await self._process.stdin.drain()

    async def _recv(self) -> dict[str, Any]:
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Transport not started")
        line = await self._process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout unexpectedly")
        try:
            data = json.loads(line.decode())
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from MCP server: {exc}") from exc

        if "error" in data:
            err = data["error"]
            raise RuntimeError(
                f"MCP error {err.get('code', '')}: {err.get('message', 'unknown')}"
            )
        return data.get("result", data)
