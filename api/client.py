"""Dragon API client with SSE streaming, tool calls, and retry logic."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

import httpx

from api.errors import TUIError, classify


# ── Data types ──────────────────────────────────────────

@dataclass
class StreamEvent:
    """A single event from the SSE stream."""
    kind: str          # "thinking" | "content" | "tool_start" | "tool_delta" | "tool_end"
    text: str = ""
    call_id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class ChatResponse:
    """Accumulated response from a chat completion."""
    content: str = ""
    thinking: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = ""


@dataclass
class ToolCall:
    """Parsed tool call."""
    id: str
    name: str
    arguments: dict

    @classmethod
    def from_openai(cls, raw: dict) -> ToolCall:
        func = raw.get("function", {})
        try:
            args = json.loads(func.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}
        return cls(
            id=raw.get("id", ""),
            name=func.get("name", ""),
            arguments=args,
        )


# ── Client ──────────────────────────────────────────────

class DragonClient:
    """Async client with retry, error translation, and streaming support."""

    # Retry configuration
    MAX_RETRIES = 2
    RETRY_BASE_DELAY = 1.0    # seconds
    RETRY_MAX_DELAY = 10.0    # seconds

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                # Retry at the transport layer for idempotent GETs only;
                # we handle POST retries ourselves.
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── High-level API ──────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        reasoning_effort: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        """Send a chat request with retry on transient failures.

        Raises:
            TUIError: on non-retryable failures or after exhausting retries.
        """
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._chat_impl(
                    messages=messages,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    tools=tools,
                )
            except TUIError as exc:
                if not exc.retryable or attempt >= self.MAX_RETRIES:
                    raise
                last_exc = exc
            except Exception as exc:
                tui_err = classify(exc)
                if not tui_err.retryable or attempt >= self.MAX_RETRIES:
                    raise tui_err from exc
                last_exc = tui_err

            # Exponential backoff with jitter
            delay = min(
                self.RETRY_BASE_DELAY * (2 ** attempt),
                self.RETRY_MAX_DELAY,
            )
            await asyncio.sleep(delay)

        # Should be unreachable, but satisfy type checker
        err = last_exc or TUIError("Unknown error")
        raise err

    async def _chat_impl(
        self,
        messages: list[dict],
        model: str | None = None,
        reasoning_effort: str | None = None,
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        """Single-attempt implementation (no retry)."""
        resp = ChatResponse()
        tool_bufs: dict[int, dict] = {}

        try:
            async for ev in self._stream_events(
                messages=messages,
                model=model,
                reasoning_effort=reasoning_effort,
                tools=tools,
            ):
                if ev.kind == "thinking":
                    resp.thinking += ev.text
                elif ev.kind == "content":
                    resp.content += ev.text
                elif ev.kind == "tool_start":
                    idx = int(ev.call_id) if ev.call_id.isdigit() else 0
                    tool_bufs[idx] = {"id": ev.text, "name": ev.name, "arguments": ""}
                elif ev.kind == "tool_delta":
                    idx = int(ev.call_id) if ev.call_id.isdigit() else 0
                    if idx in tool_bufs:
                        tool_bufs[idx]["arguments"] += ev.text
                elif ev.kind == "tool_end":
                    pass

        except (httpx.RemoteProtocolError, httpx.ReadError, GeneratorExit) as exc:
            # SSE stream broke — but we may already have partial content
            if resp.content or resp.tool_calls:
                # Return what we got; don't lose partial progress
                pass
            else:
                raise classify(exc) from exc

        # Build tool_calls from buffers
        for idx in sorted(tool_bufs.keys()):
            buf = tool_bufs[idx]
            if buf["name"]:
                resp.tool_calls.append({
                    "id": buf["id"],
                    "type": "function",
                    "function": {
                        "name": buf["name"],
                        "arguments": buf["arguments"],
                    },
                })

        return resp

    # ── Low-level streaming ─────────────────────────────

    async def _stream_events(
        self,
        messages: list[dict],
        model: str | None = None,
        reasoning_effort: str | None = None,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield StreamEvent objects from the SSE stream.

        Raises httpx errors directly — retry is handled by `chat()`.
        """
        client = await self._get_client()
        body: dict = {
            "model": model or "deepseek-chat",
            "messages": messages,
            "stream": True,
        }
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        if tools:
            body["tools"] = tools

        tool_call_acc: dict[int, dict] = {}

        async with client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    return

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                if "reasoning_content" in delta and delta["reasoning_content"]:
                    yield StreamEvent(kind="thinking", text=delta["reasoning_content"])

                if "content" in delta and delta["content"]:
                    yield StreamEvent(kind="content", text=delta["content"])

                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_call_acc:
                            tool_call_acc[idx] = {"id": "", "name": "", "args": ""}
                        buf = tool_call_acc[idx]

                        if "id" in tc and tc["id"]:
                            buf["id"] = tc["id"]
                            yield StreamEvent(
                                kind="tool_start",
                                call_id=str(idx),
                                text=tc["id"],
                                name=tc.get("function", {}).get("name", ""),
                            )

                        func = tc.get("function", {})
                        if "name" in func and func["name"]:
                            buf["name"] = func["name"]
                            yield StreamEvent(
                                kind="tool_start",
                                call_id=str(idx),
                                text=buf["id"],
                                name=func["name"],
                            )

                        if "arguments" in func and func["arguments"]:
                            buf["args"] += func["arguments"]
                            yield StreamEvent(
                                kind="tool_delta",
                                call_id=str(idx),
                                text=func["arguments"],
                            )

    # ── Legacy streaming (backward compat) ──────────────

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """Stream chat completions. Yields (kind, text)."""
        async for ev in self._stream_events(
            messages=messages,
            model=model,
            reasoning_effort=reasoning_effort,
        ):
            if ev.kind in ("thinking", "content"):
                yield (ev.kind, ev.text)
