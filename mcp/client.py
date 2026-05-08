"""MCP client — wraps a transport with the Model Context Protocol handshake.

Implements the required lifecycle:
    1. initialize          → capabilities exchange
    2. notifications/initialized  → notify server we're ready
    3. tools/list          → discover available tools
    4. tools/call          → execute a tool
"""

from __future__ import annotations

from typing import Any

from mcp.transport import StdioTransport


class MCPClient:
    """High-level MCP client over a stdio transport."""

    def __init__(self, server_name: str, transport: StdioTransport):
        self.server_name = server_name
        self.transport = transport
        self._server_info: dict = {}
        self._tools: list[dict] = []

    async def start(self) -> None:
        """Connect and perform the MCP handshake."""
        await self.transport.start()

        # ── Initialize ─────────────────────────────────
        result = await self.transport.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "dragon-tui",
                "version": "0.3.0",
            },
        })
        self._server_info = result

        # ── Notify initialized ─────────────────────────
        await self.transport.notify("notifications/initialized", {})

    async def list_tools(self) -> list[dict]:
        """Discover tools from the server. Returns raw MCP tool descriptors."""
        result = await self.transport.request("tools/list", {})
        self._tools = result.get("tools", [])
        return self._tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool on the server and return a text representation."""
        result = await self.transport.request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

        # MCP returns content as a list of {type, text/mimeType/data}
        content = result.get("content", [])
        if not content:
            return "(no output)"

        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "resource":
                    # For resources, show the URI and text if available
                    uri = item.get("resource", {}).get("uri", "")
                    text = item.get("resource", {}).get("text", "")
                    parts.append(f"[resource: {uri}]\n{text}" if text else f"[resource: {uri}]")
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))

        return "\n".join(parts) if parts else str(content)

    @property
    def tools(self) -> list[dict]:
        return self._tools

    async def close(self) -> None:
        await self.transport.close()
