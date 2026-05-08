"""Session list screen — overlay for browsing and loading saved sessions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class SessionListScreen(ModalScreen[str | None]):
    """Modal overlay showing saved sessions with keyboard selection."""

    CSS = """
    SessionListScreen {
        align: center middle;
    }

    #session-dialog {
        width: 60;
        max-height: 70%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #session-dialog Label {
        padding: 1 0;
    }

    #session-title {
        text-style: bold;
        padding-bottom: 1;
        border-bottom: solid $surface-darken-1;
    }

    #session-list {
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }

    .session-item {
        padding: 0 1;
        height: 1;
    }

    .session-item.selected {
        background: $primary;
        color: $text;
    }

    #session-help {
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
        ("enter", "select", "Load"),
        ("d", "delete_session", "Delete"),
    ]

    def __init__(self, sessions: list[dict]):
        super().__init__()
        self._sessions = sessions
        self._cursor = 0

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="session-dialog"):
                yield Static("📂 Saved Sessions", id="session-title")

                if not self._sessions:
                    yield Static("  (no saved sessions)", id="session-list")
                else:
                    # Build items as a single Static for simplicity
                    lines = ""
                    for i, s in enumerate(self._sessions):
                        prefix = "▸" if i == 0 else " "
                        title = s.get("title", "(untitled)")[:40]
                        date = s.get("updated_at", "")[:10]
                        msgs = s.get("message_count", 0)
                        lines += f"{prefix} {date}  {title}  ({msgs} msgs)\n"
                    yield Static(lines, id="session-list")

                yield Static(
                    "↑↓ select  Enter load  d delete  Esc cancel",
                    id="session-help",
                )

    # ── Actions ───────────────────────────────────────────

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select(self) -> None:
        if self._sessions and 0 <= self._cursor < len(self._sessions):
            self.dismiss(self._sessions[self._cursor]["id"])

    def action_cursor_up(self) -> None:
        if not self._sessions:
            return
        self._cursor = (self._cursor - 1) % len(self._sessions)
        self._redraw_list()

    def action_cursor_down(self) -> None:
        if not self._sessions:
            return
        self._cursor = (self._cursor + 1) % len(self._sessions)
        self._redraw_list()

    def action_delete_session(self) -> None:
        if self._sessions and 0 <= self._cursor < len(self._sessions):
            self.dismiss(f"__delete__{self._sessions[self._cursor]['id']}")

    # ── Helpers ───────────────────────────────────────────

    def _redraw_list(self):
        widget = self.query_one("#session-list", Static)
        lines = ""
        for i, s in enumerate(self._sessions):
            prefix = "▸" if i == self._cursor else " "
            title = s.get("title", "(untitled)")[:40]
            date = s.get("updated_at", "")[:10]
            msgs = s.get("message_count", 0)
            lines += f"{prefix} {date}  {title}  ({msgs} msgs)\n"
        widget.update(lines)
