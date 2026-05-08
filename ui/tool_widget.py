"""Widget for rendering tool calls and results in the chat."""

from __future__ import annotations

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.widget import Widget

from tools.registry import ToolCall, ToolResult
from ui.themes import get_code_theme


class ToolCallWidget(Widget):
    """Renders a tool invocation — name, arguments, and result."""

    DEFAULT_CSS = """
    ToolCallWidget {
        border: solid $warning;
        border-title-color: $warning;
        padding: 1 2;
        margin: 0 0 1 0;
        height: auto;
    }
    """

    def __init__(self, call: ToolCall, result: ToolResult | None = None):
        super().__init__()
        self.call = call
        self.result = result
        self.border_title = f"🔧 {call.name}"

    def set_result(self, result: ToolResult) -> None:
        self.result = result
        if not result.success:
            self.border_title = f"❌ {self.call.name}"
            self.styles.border = ("solid", "$error")
        self.refresh(layout=True)

    def render(self):
        import json

        parts: list = []

        args_text = json.dumps(self.call.arguments, ensure_ascii=False, indent=2)
        parts.append(Text("Arguments:", style="dim"))
        parts.append(Text(args_text, style="italic"))

        if self.result is not None:
            parts.append(Text(""))
            if self.result.success:
                ct = get_code_theme()
                try:
                    md = Markdown(self.result.content, code_theme=ct)
                    parts.append(md)
                except Exception:
                    parts.append(Text(self.result.content))
            else:
                parts.append(Text(f"Error: {self.result.error}", style="bold red"))
        else:
            parts.append(Text(""))
            parts.append(Text("⏳ Running…", style="dim italic"))

        return Group(*parts)
