"""Model selection screen — overlay for choosing a LLM model."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class ModelListScreen(ModalScreen[str | None]):
    """Modal overlay showing available models with keyboard selection."""

    CSS = """
    ModelListScreen {
        align: center middle;
    }

    #model-dialog {
        width: 55;
        max-height: 70%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #model-title {
        text-style: bold;
        padding-bottom: 1;
        border-bottom: solid $surface-darken-1;
    }

    #model-list {
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }

    .model-item {
        padding: 0 1;
        height: 1;
    }

    .model-item.selected {
        background: $primary;
        color: $text;
    }

    #model-help {
        padding-top: 1;
        border-top: solid $surface-darken-1;
        color: $text-disabled;
        text-style: italic;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("enter", "select", "Select"),
    ]

    def __init__(self, models: list[tuple[str, str]], current: str) -> None:
        super().__init__()
        self._models = models
        self._current = current
        self._cursor = 0
        for i, (_alias, model) in enumerate(models):
            if model == current:
                self._cursor = i
                break

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="model-dialog"):
                yield Static("🤖 Select Model", id="model-title")
                lines = ""
                for i, (alias, model) in enumerate(self._models):
                    prefix = "▸" if i == self._cursor else " "
                    marker = " [current]" if model == self._current else ""
                    lines += f"{prefix} {alias:<10} → {model}{marker}\n"
                yield Static(lines, id="model-list")
                yield Static(
                    "↑↓ select  Enter confirm  Esc cancel",
                    id="model-help",
                )

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select(self) -> None:
        if self._models and 0 <= self._cursor < len(self._models):
            self.dismiss(self._models[self._cursor][0])

    def action_cursor_up(self) -> None:
        if not self._models:
            return
        self._cursor = (self._cursor - 1) % len(self._models)
        self._redraw_list()

    def action_cursor_down(self) -> None:
        if not self._models:
            return
        self._cursor = (self._cursor + 1) % len(self._models)
        self._redraw_list()

    def _redraw_list(self) -> None:
        widget = self.query_one("#model-list", Static)
        lines = ""
        for i, (alias, model) in enumerate(self._models):
            prefix = "▸" if i == self._cursor else " "
            marker = " [current]" if model == self._current else ""
            lines += f"{prefix} {alias:<10} → {model}{marker}\n"
        widget.update(lines)
