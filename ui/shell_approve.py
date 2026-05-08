"""Shell command approval dialog."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ShellApprovalScreen(ModalScreen[bool]):
    """Modal dialog to approve or deny a shell command."""

    CSS = """
    ShellApprovalScreen {
        align: center middle;
    }

    #approve-dialog {
        width: 70;
        background: $surface;
        border: solid $warning;
        padding: 1 2;
    }

    #approve-command {
        margin: 1 0;
        padding: 1;
        background: $surface-darken-1;
        border: solid $surface-darken-2;
    }

    #approve-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    #approve-buttons Button {
        margin: 0 2;
    }
    """

    BINDINGS = [
        ("y", "approve", "Yes"),
        ("n", "deny", "No"),
        ("escape", "deny", "Cancel"),
    ]

    def __init__(self, command: str, cwd: str = ""):
        super().__init__()
        self._command = command
        self._cwd = cwd

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="approve-dialog"):
                yield Static("⚠ Execute shell command?", id="approve-title")
                if self._cwd:
                    yield Static(f"  cwd: {self._cwd}", id="approve-cwd")
                yield Static(self._command, id="approve-command")
                with Center(id="approve-buttons"):
                    yield Button("✓ Approve (y)", variant="warning", id="btn-yes")
                    yield Button("✗ Deny (n / Esc)", variant="default", id="btn-no")

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
