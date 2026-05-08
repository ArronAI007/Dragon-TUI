"""Tool registry — define, register, and execute tools for the AI to call."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

# ── Tool definitions ────────────────────────────────────

@dataclass
class ToolDef:
    """Definition of a callable tool with JSON Schema parameters."""

    name: str
    description: str
    parameters: dict  # JSON Schema for the parameters
    handler: Callable[..., Awaitable[str]]
    requires_approval: bool = False

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    """A parsed tool call extracted from the API response."""

    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    """Result of executing a tool."""

    call: ToolCall
    content: str
    success: bool = True
    error: str = ""


# ── Registry ────────────────────────────────────────────

class ToolRegistry:
    """Holds registered tools and provides schema/execution access."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        *,
        requires_approval: bool = False,
    ):
        """Decorator to register a tool handler."""

        def decorator(
            func: Callable[..., Awaitable[str]],
        ) -> Callable[..., Awaitable[str]]:
            self._tools[name] = ToolDef(
                name=name,
                description=description,
                parameters=parameters,
                handler=func,
                requires_approval=requires_approval,
            )
            return func

        return decorator

    def add_tool(self, tool_def: ToolDef) -> None:
        """Register a pre-built tool definition (non-decorator API)."""
        self._tools[tool_def.name] = tool_def

    def get_schemas(self) -> list[dict]:
        """Return OpenAI-format tool schemas for all registered tools."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def get_tool(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def needs_approval(self, name: str) -> bool:
        tool = self._tools.get(name)
        return tool.requires_approval if tool else False

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result."""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                call=call,
                content="",
                success=False,
                error=f"Unknown tool: {call.name}",
            )

        try:
            content = await tool.handler(**call.arguments)
            return ToolResult(call=call, content=str(content))
        except Exception as exc:
            return ToolResult(
                call=call,
                content="",
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
