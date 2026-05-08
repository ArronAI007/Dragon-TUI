"""Error display widget for the chat — red-bordered message with retry hint."""

from __future__ import annotations

from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text
from textual.widget import Widget


class ErrorWidget(Widget):
    """Renders an error message in a red-bordered panel."""

    DEFAULT_CSS = """
    ErrorWidget {
        border: solid $error;
        border-title-color: $error;
        padding: 1 2;
        margin: 0 0 1 0;
        height: auto;
    }
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__()
        self._message = message
        self._retryable = retryable
        self.border_title = "⚠ Error"
        if retryable:
            self.border_subtitle = "auto-retried"

    def render(self) -> RenderableType:
        parts = [Text(self._message, style="bold red")]
        if self._retryable:
            parts.append(Text(""))
            parts.append(Text(
                "This error is transient — the request will be retried automatically.",
                style="dim",
            ))
        return Panel(Text("\n").join(parts))
