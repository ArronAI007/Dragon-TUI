"""dragon-tui: A terminal UI for DeepSeek API with theme support.

Usage:
    dragon                  # auto-load config
    dragon --config ./config.toml
    DEEPSEEK_API_KEY=sk-xxx dragon
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from api.client import ChatResponse, DragonClient, ToolCall as APIToolCall
from api.errors import TUIError, classify
from config import Settings, load_settings
from mcp.manager import MCPManager
from session.manager import ConversationManager
from session.storage import SessionRecord, SessionStorage
from tools.builtins import registry
from tools.registry import ToolCall, ToolDef, ToolResult
from ui.chat_input import ChatInput
from ui.error_widget import ErrorWidget
from ui.markdown_message import MarkdownMessage
from ui.session_screen import SessionListScreen
from ui.shell_approve import ShellApprovalScreen
from ui.themes import cycle_code_theme, get_code_theme, set_code_theme, switch_mode
from ui.tool_widget import ToolCallWidget


# ── Defaults ────────────────────────────────────────────────

DEFAULT_SESSION_DIR = Path.home() / ".dragon-tui-py" / "sessions"
DEFAULT_HISTORY_FILE = Path.home() / ".dragon-tui-py" / "history.json"

COMMAND_HELP = {
    "/clear":     "Clear the conversation",
    "/save":      "Save session to disk",
    "/load":      "Open session list",
    "/model":     "Switch model (/model chat | /model pro)",
    "/reasoning": "Set reasoning effort (/reasoning off|low|medium|high|max)",
    "/tools":     "Toggle tool calling on/off",
    "/theme":     "Toggle dark/light mode (/theme dark | /theme light)",
    "/code":      "Cycle or set code theme (/code | /code monokai)",
    "/mcp":       "Show MCP server status + connected tools",
    "/help":      "Show this help",
}

MAX_TOOL_ITERATIONS = 5


# ────────────────────────────────────────────────────────────
# App
# ────────────────────────────────────────────────────────────

class ChatApp(App):
    """Main TUI application with theme + MCP + tool calling + error handling."""

    CSS = """
    #message-list {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        color: $text-disabled;
        padding: 0 2;
    }

    #chat-input {
        dock: bottom;
        height: auto;
        min-height: 1;
        max-height: 12;
        border: solid $primary-darken-2;
        padding: 0 1;
        margin: 0 1 1 1;
    }

    #chat-input:focus {
        border: solid $primary;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("ctrl+s", "save", "Save"),
        ("ctrl+o", "open_sessions", "Load"),
        ("ctrl+d", "toggle_dark_mode", "☀/🌙"),
        ("ctrl+shift+d", "cycle_code", "Code theme"),
        ("ctrl+m", "cycle_model", "Model"),
        ("ctrl+r", "cycle_reasoning", "Reasoning"),
        ("ctrl+t", "toggle_tools", "Tools"),
    ]

    REASONING_LEVELS = ["off", "low", "medium", "high", "max"]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.client = DragonClient(
            api_key=settings.api_key, base_url=settings.base_url
        )
        self.conversation = ConversationManager(
            model=settings.default_model,
            max_tokens=settings.max_context_tokens,
            buffer_ratio=settings.context_buffer_ratio,
        )
        self.storage = SessionStorage(
            Path(getattr(settings, "session_dir", str(DEFAULT_SESSION_DIR)))
        )
        self._session_id: str = ""
        self._tools_enabled: bool = True
        self.mcp = MCPManager()

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="message-list")
        yield Static("", id="status-bar")
        yield ChatInput(id="chat-input")
        yield Footer()

    async def on_mount(self) -> None:
        self._session_id = self.storage.new_id()

        # ── Apply theme from config ────────────────────
        dark = self.settings.theme != "light"
        self.dark = dark
        set_code_theme(self.settings.code_theme)
        switch_mode(dark)

        self._update_status()

        # Load input history
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.load_history(str(DEFAULT_HISTORY_FILE))

        # Show welcome message
        msg_list = self.query_one("#message-list", VerticalScroll)
        welcome_lines = [
            "# Dragon TUI",
            "",
            "基于 Python 和 Textual 构建的 Dragon TUI。",
            "",
            "**常用命令：**",
        ]
        for cmd, desc in COMMAND_HELP.items():
            welcome_lines.append(f"- `{cmd}` — {desc}")
        welcome_lines.append("")
        welcome_lines.append("输入消息开始对话，或输入 `/help` 查看更多功能。")
        welcome_widget = MarkdownMessage("\n".join(welcome_lines), role="thinking")
        welcome_widget.border_title = "Welcome"
        await msg_list.mount(welcome_widget)

        chat_input.focus()

        self._connect_mcp_servers()

    # ── MCP integration ───────────────────────────────────

    def _connect_mcp_servers(self) -> None:
        servers = self.settings.mcp_servers
        if not servers:
            return

        async def _connect():
            for cfg in servers:
                name = cfg.get("name", "?")
                try:
                    summary = await self.mcp.add_server(name, cfg)
                    for schema in self.mcp.get_tool_schemas():
                        t_name = schema["function"]["name"]
                        if registry.get_tool(t_name) is None:
                            handler = self.mcp.make_handler(t_name)
                            registry.add_tool(ToolDef(
                                name=t_name,
                                description=schema["function"]["description"],
                                parameters=schema["function"]["parameters"],
                                handler=handler,
                                requires_approval=self.mcp.needs_approval(t_name),
                            ))
                    self._flash_status(summary)
                except Exception as exc:
                    self._flash_status(f"MCP/{name}: {exc}")
            self._update_status()

        self.call_later(_connect)

    # ── Theme actions ─────────────────────────────────────

    async def action_toggle_dark_mode(self) -> None:
        """Toggle between dark and light mode."""
        self.dark = not self.dark
        new_theme = "dark" if self.dark else "light"
        self.settings.theme = new_theme
        ct = switch_mode(self.dark)
        self._refresh_all_messages()
        self._update_status()
        self._flash_status(f"Theme → {new_theme}  (code: {ct})")

    async def action_cycle_code(self) -> None:
        """Cycle the code syntax highlighting theme."""
        ct = cycle_code_theme()
        self.settings.code_theme = ct
        self._refresh_all_messages()
        self._update_status()
        self._flash_status(f"Code theme → {ct}")

    async def on_unmount(self) -> None:
        """Save history before the app exits."""
        try:
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.save_history(str(DEFAULT_HISTORY_FILE))
        except Exception:
            pass

    def _refresh_all_messages(self) -> None:
        """Force re-render of all message widgets after a theme change."""
        msg_list = self.query_one("#message-list", VerticalScroll)
        for child in msg_list.children:
            if isinstance(child, (MarkdownMessage, ToolCallWidget)):
                child.refresh(layout=True)

    # ── Actions ───────────────────────────────────────────

    async def action_clear(self) -> None:
        self.conversation.clear()
        msg_list = self.query_one("#message-list", VerticalScroll)
        await msg_list.remove_children()
        self._session_id = self.storage.new_id()
        self._update_status()

    async def action_save(self) -> None:
        self._do_save()
        self._flash_status("Session saved.")

    async def action_open_sessions(self) -> None:
        sessions = self.storage.list_sessions()
        screen = SessionListScreen(sessions)
        result = await self.push_screen_wait(screen)
        if result is None:
            return
        if result.startswith("__delete__"):
            await self._delete_session(result[len("__delete__"):])
            return
        await self._load_session(result)

    async def action_cycle_model(self) -> None:
        models = ["deepseek-chat", "deepseek-v4-pro"]
        current = self.settings.default_model
        idx = models.index(current) if current in models else -1
        next_idx = (idx + 1) % len(models)
        self.settings.default_model = models[next_idx]
        self.conversation = ConversationManager(
            model=models[next_idx],
            max_tokens=self.settings.max_context_tokens,
            buffer_ratio=self.settings.context_buffer_ratio,
        )
        self._update_status()
        self._flash_status(f"Model → {models[next_idx]}")

    async def action_cycle_reasoning(self) -> None:
        current = self.settings.reasoning_effort
        idx = self.REASONING_LEVELS.index(current) if current in self.REASONING_LEVELS else 0
        next_idx = (idx + 1) % len(self.REASONING_LEVELS)
        self.settings.reasoning_effort = self.REASONING_LEVELS[next_idx]
        self._update_status()
        self._flash_status(f"Reasoning → {self.REASONING_LEVELS[next_idx]}")

    async def action_toggle_tools(self) -> None:
        self._tools_enabled = not self._tools_enabled
        state = "ON" if self._tools_enabled else "OFF"
        self._flash_status(f"Tool calling: {state}")

    # ── Session persistence ───────────────────────────────

    def _do_save(self) -> None:
        try:
            record = SessionRecord(
                id=self._session_id,
                title=self.conversation.title,
                model=self.conversation.model,
                messages=self.conversation._messages,
            )
            self.storage.save(record)
        except Exception as exc:
            self._flash_status(f"Save failed: {exc}")

    async def _load_session(self, session_id: str) -> None:
        try:
            record = self.storage.load(session_id)
        except Exception as exc:
            self._flash_status(f"Cannot load session: {exc}")
            return

        if record is None:
            self._flash_status("Session not found.")
            return
        self.conversation = ConversationManager.from_dict(
            record.to_dict(),
            max_tokens=self.settings.max_context_tokens,
            buffer_ratio=self.settings.context_buffer_ratio,
        )
        self._session_id = record.id
        self.settings.default_model = record.model
        msg_list = self.query_one("#message-list", VerticalScroll)
        await msg_list.remove_children()
        for msg in self.conversation._messages:
            role = msg["role"]
            if role in ("system", "tool"):
                continue
            widget = MarkdownMessage(msg.get("content", ""), role=role)
            await msg_list.mount(widget)
        self._update_status()
        self._flash_status(
            f"Loaded: {record.title or '(untitled)'} ({record.message_count} msgs)"
        )

    async def _delete_session(self, session_id: str) -> None:
        self.storage.delete(session_id)
        self._flash_status("Session deleted.")
        sessions = self.storage.list_sessions()
        screen = SessionListScreen(sessions)
        result = await self.push_screen_wait(screen)
        if result and result.startswith("__delete__"):
            await self._delete_session(result[len("__delete__"):])
        elif result:
            await self._load_session(result)

    # ── Status bar ────────────────────────────────────────

    def _update_status(self) -> None:
        conv = self.conversation
        title = conv.title or "(new session)"
        tools = "🛠" if self._tools_enabled else ""
        mcp = f" MCP:{self.mcp.server_count}" if self.mcp.server_count else ""
        mode = "🌙" if self.dark else "☀"
        ct = get_code_theme()
        bar = self.query_one("#status-bar", Static)
        bar.update(
            f" {mode} {ct}"
            f" | {title}"
            f" | {conv.model}"
            f" | reasoning: {self.settings.reasoning_effort}"
            f" | tokens: {conv.token_count:,} / {conv.token_limit:,}"
            f" ({conv.capacity_pct:.0f}%)"
            f"  {tools}{mcp}"
        )

    async def _flash_status(self, text: str) -> None:
        bar = self.query_one("#status-bar", Static)
        bar.update(f" [bold]{text}[/]")
        await self.set_timer(2.0, self._update_status)

    # ── Input handler ─────────────────────────────────────

    async def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.text.strip()
        if not text:
            return
        if text.startswith("/"):
            self._run_command(text)
        else:
            await self._run_chat(text)

    def _run_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/clear":
            self.run_action("clear")
        elif cmd == "/save":
            self.run_action("save")
        elif cmd == "/load":
            self.run_action("open_sessions")
        elif cmd == "/model":
            self._set_model(arg)
        elif cmd == "/reasoning":
            self._set_reasoning(arg)
        elif cmd == "/tools":
            self.run_action("toggle_tools")
        elif cmd == "/theme":
            self._set_theme(arg)
        elif cmd == "/code":
            self._set_code_theme(arg)
        elif cmd == "/mcp":
            self._show_mcp_status()
        elif cmd == "/help":
            self._show_help()
        else:
            self._flash_status(f"Unknown command: {cmd}  (type /help)")

    def _set_model(self, arg: str) -> None:
        alias = arg.strip().lower()
        model_map = {"chat": "deepseek-chat", "pro": "deepseek-v4-pro", "v4": "deepseek-v4-pro"}
        if alias in model_map:
            self.settings.default_model = model_map[alias]
            self.conversation = ConversationManager(
                model=model_map[alias],
                max_tokens=self.settings.max_context_tokens,
                buffer_ratio=self.settings.context_buffer_ratio,
            )
            self._update_status()
            self._flash_status(f"Model → {model_map[alias]}")
        else:
            self._flash_status(
                f"Usage: /model chat | pro  (current: {self.settings.default_model})"
            )

    def _set_reasoning(self, arg: str) -> None:
        level = arg.strip().lower()
        if level in self.REASONING_LEVELS:
            self.settings.reasoning_effort = level
            self._update_status()
            self._flash_status(f"Reasoning → {level}")
        else:
            self._flash_status(
                f"Usage: /reasoning {'|'.join(self.REASONING_LEVELS)}"
                f"  (current: {self.settings.reasoning_effort})"
            )

    def _set_theme(self, arg: str) -> None:
        """Set UI theme: /theme dark | /theme light"""
        mode = arg.strip().lower()
        if mode in ("dark", "light"):
            self.dark = (mode == "dark")
            self.settings.theme = mode
            ct = switch_mode(self.dark)
            self._refresh_all_messages()
            self._update_status()
            self._flash_status(f"Theme → {mode}  (code: {ct})")
        else:
            self.run_action("toggle_dark_mode")

    def _set_code_theme(self, arg: str) -> None:
        """Set or cycle code theme: /code | /code monokai"""
        name = arg.strip().lower()
        if name:
            from ui.themes import ALL_CODE_THEMES
            if name in ALL_CODE_THEMES:
                set_code_theme(name)
                self.settings.code_theme = name
                self._refresh_all_messages()
                self._update_status()
                self._flash_status(f"Code theme → {name}")
            else:
                available = ", ".join(ALL_CODE_THEMES[:6]) + "..."
                self._flash_status(f"Unknown code theme. Available: {available}")
        else:
            self.run_action("cycle_code")

    def _show_help(self) -> None:
        lines = ["Available commands:\n"]
        for cmd, desc in COMMAND_HELP.items():
            lines.append(f"  {cmd:<14} {desc}")
        help_text = "\n".join(lines)
        msg_list = self.query_one("#message-list", VerticalScroll)
        widget = MarkdownMessage(help_text, role="thinking")
        widget.border_title = "Help"
        self.call_later(lambda: msg_list.mount(widget))

    def _show_mcp_status(self) -> None:
        lines = ["MCP Servers:\n"]
        if self.mcp.server_count == 0:
            lines.append("  (no MCP servers configured)")
            lines.append("  Add [[mcp_servers]] to your config.toml to connect.")
        else:
            for t_name in sorted(self.mcp._tool_index.keys()):
                srv, _ = self.mcp._tool_index[t_name]
                lines.append(f"  🔧 {t_name}  ({srv})")
            lines.append(f"\n  {self.mcp.server_count} server(s), {self.mcp.tool_count} tool(s)")
        help_text = "\n".join(lines)
        msg_list = self.query_one("#message-list", VerticalScroll)
        widget = MarkdownMessage(help_text, role="thinking")
        widget.border_title = "MCP"
        self.call_later(lambda: msg_list.mount(widget))

    # ── Chat flow ─────────────────────────────────────────

    async def _run_chat(self, text: str) -> None:
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.add_to_history(text)
        chat_input.save_history(str(DEFAULT_HISTORY_FILE))
        await self._process_message(text)

    async def _process_message(self, user_text: str) -> None:
        msg_list = self.query_one("#message-list", VerticalScroll)

        user_widget = MarkdownMessage(user_text, role="user")
        await msg_list.mount(user_widget)
        trimmed = self.conversation.add("user", user_text)
        if trimmed > 0:
            self._flash_status(
                f"✂ Trimmed {trimmed} earlier message(s) to stay within context window"
            )

        try:
            await self._run_tool_loop(msg_list)
        except TUIError as exc:
            self._rollback_last_user_message()
            error = ErrorWidget(str(exc), retryable=exc.retryable)
            await msg_list.mount(error)
            self._flash_status(str(exc))
        except Exception as exc:
            self._rollback_last_user_message()
            err = classify(exc)
            error = ErrorWidget(str(err), retryable=err.retryable)
            await msg_list.mount(error)
            self._flash_status(str(err)[:80])

        self._update_status()
        self._do_save()
        self.query_one("#chat-input", ChatInput).focus()

    def _rollback_last_user_message(self) -> None:
        conv = self.conversation
        for i in range(len(conv._messages) - 1, -1, -1):
            if conv._messages[i]["role"] == "user":
                conv._messages.pop(i)
                break

    # ── Tool call loop ────────────────────────────────────

    async def _run_tool_loop(self, msg_list: VerticalScroll) -> None:
        tools: list[dict] | None = None
        if self._tools_enabled:
            tools = registry.get_schemas()

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                resp = await self.client.chat(
                    messages=self.conversation.messages,
                    model=self.settings.default_model,
                    reasoning_effort=self.settings.reasoning_effort,
                    tools=tools,
                )
            except TUIError:
                raise

            if resp.content.strip():
                assistant = MarkdownMessage(resp.content, role="assistant")
                await msg_list.mount(assistant)
                msg_list.scroll_end(animate=False)

            if not resp.tool_calls:
                if resp.content.strip():
                    self.conversation.add("assistant", resp.content)
                break

            tool_call_objs: list[ToolCall] = []
            tool_widgets: list[ToolCallWidget] = []

            for tc_raw in resp.tool_calls:
                tc = ToolCall.from_openai(tc_raw)
                tool_call_objs.append(tc)

                widget = ToolCallWidget(tc)
                await msg_list.mount(widget)
                tool_widgets.append(widget)

                if registry.needs_approval(tc.name):
                    cmd = tc.arguments.get("command", "")
                    cwd = tc.arguments.get("cwd", "")
                    approved = await self._request_approval(cmd, cwd)
                    if not approved:
                        result = ToolResult(
                            call=tc, content="",
                            success=False, error="Denied by user.",
                        )
                        widget.set_result(result)
                        continue

                result = await registry.execute(tc)
                widget.set_result(result)

            msg_list.scroll_end(animate=False)

            conv = self.conversation
            conv._messages.append({
                "role": "assistant",
                "content": resp.content or None,
                "tool_calls": resp.tool_calls,
            })
            for tc, w in zip(tool_call_objs, tool_widgets):
                r = w.result
                conv._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": r.content if r else "Error: no result",
                })

        self._update_status()

    async def _request_approval(self, command: str, cwd: str = "") -> bool:
        screen = ShellApprovalScreen(command, cwd)
        return await self.push_screen_wait(screen)


# ────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dragon TUI")
    parser.add_argument("--config", help="Path to config.toml", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)

    if not settings.api_key:
        print("Error: No API key found.")
        print("  Set DEEPSEEK_API_KEY environment variable, or")
        print("  place a config.toml with api_key in the current directory,")
        print("  or at ~/.dragon/config.toml")
        raise SystemExit(1)

    app = ChatApp(settings)
    app.run()


if __name__ == "__main__":
    main()
