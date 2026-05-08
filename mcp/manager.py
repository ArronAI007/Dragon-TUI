"""MCP manager — connects to multiple MCP servers and merges their tools.

Lifecycle:
    1. add_server(config)  → connect + handshake + discover tools
    2. get_tool_schemas()  → OpenAI-format schemas for all MCP tools
    3. make_handler(name)  → async callable that executes the tool
    4. close_all()         → terminate all subprocesses
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from mcp.client import MCPClient
from mcp.sse_transport import SSETransport
from mcp.transport import StdioTransport


class MCPManager:
    """Manages multiple MCP server connections and tool routing."""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        # tool_name → (server_name, raw_tool_descriptor)
        self._tool_index: dict[str, tuple[str, dict]] = {}

    async def add_server(self, name: str, config: dict) -> str:
        """Connect to an MCP server and register its tools.

        Args:
            name: friendly name for this server
            config: stdio: {"type":"stdio", "command", "args", "env"}
                    sse:    {"type":"sse", "url", "headers"}

        Returns:
            Summary string.
        """
        transport_type = config.get("type", "stdio")

        if transport_type == "sse":
            transport = SSETransport(
                url=config["url"],
                headers=config.get("headers"),
            )
        else:
            transport = StdioTransport(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("env"),
            )

        client = MCPClient(name, transport)

        try:
            await client.start()
            tools = await client.list_tools()
        except Exception:
            await client.close()
            raise

        self._clients[name] = client

        count = 0
        for tool in tools:
            t_name = tool.get("name", "")
            if not t_name:
                continue
            # Prefix tool name with server name to avoid collisions
            # qualified = f"{name}__{t_name}"
            self._tool_index[t_name] = (name, tool)
            count += 1

        return f"MCP/{name}: connected ({client._server_info.get('serverInfo', {}).get('name', '?')}), {count} tools"

    def get_tool_schemas(self) -> list[dict]:
        """Return OpenAI-format tool schemas for all MCP tools."""
        schemas = []
        for t_name, (server_name, tool) in self._tool_index.items():
            input_schema = tool.get("inputSchema", {
                "type": "object",
                "properties": {},
            })
            # Ensure required is a list
            if "required" in input_schema and not isinstance(input_schema["required"], list):
                input_schema["required"] = []

            schemas.append({
                "type": "function",
                "function": {
                    "name": t_name,
                    "description": tool.get("description", f"MCP tool from {server_name}"),
                    "parameters": input_schema,
                },
            })
        return schemas

    def make_handler(self, tool_name: str) -> Callable[..., Awaitable[str]]:
        """Build an async handler for a tool (for ToolRegistry registration)."""
        server_name, _tool = self._tool_index.get(tool_name, (None, None))
        if server_name is None:
            async def _unknown(**kwargs) -> str:
                return f"Unknown MCP tool: {tool_name}"
            return _unknown

        client = self._clients[server_name]

        async def _handler(**kwargs) -> str:
            return await client.call_tool(tool_name, kwargs)

        return _handler

    def needs_approval(self, tool_name: str) -> bool:
        """MCP tools don't require approval by default."""
        return False

    async def close_all(self) -> None:
        """Terminate all server subprocesses."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        self._tool_index.clear()

    @property
    def server_count(self) -> int:
        return len(self._clients)

    @property
    def tool_count(self) -> int:
        return len(self._tool_index)
