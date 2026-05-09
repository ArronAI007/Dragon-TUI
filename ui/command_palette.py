"""Modal command palette for slash commands.

Pops up when the user types '/' in the chat input. Supports real-time
filtering, arrow-key navigation, and Enter/Tab selection.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option


class CommandPalette(ModalScreen[str | None]):
    """Overlay that lets the user pick a slash command.

    Dismisses with the selected command string (e.g. '/model') or None
    when the user cancels.
    """

    CSS = """
    CommandPalette {
        align: center bottom;
        padding-bottom: 3;
    }

    #palette-container {
        width: 70;
        height: auto;
        max-height: 24;
        border: solid $primary;
        background: $surface;
        padding: 0 0 1 0;
    }

    #palette-input {
        border: none;
        border-bottom: solid $primary-darken-2;
        padding: 0 2;
        height: auto;
        min-height: 1;
    }

    #palette-list {
        height: auto;
        max-height: 18;
        border: none;
        padding: 0;
    }

    #palette-list > .option-list--option {
        padding: 0 2;
    }

    #palette-list > .option-list--option-highlighted {
        background: $primary-darken-2;
    }

    #palette-empty {
        height: auto;
        padding: 1 2;
        color: $text-disabled;
        display: none;
    }

    #palette-empty.visible {
        display: block;
    }
    """

    def __init__(
        self,
        commands: dict[str, str],
        *,
        initial_query: str = "",
    ) -> None:
        super().__init__()
        self.commands = commands
        self.initial_query = initial_query
        self._filtered: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-container"):
            yield Input(
                value=self.initial_query,
                placeholder="Filter commands...",
                id="palette-input",
            )
            yield OptionList(id="palette-list")
            yield Static("No matching commands", id="palette-empty")

    def on_mount(self) -> None:
        input_widget = self.query_one("#palette-input", Input)
        input_widget.focus()
        self._filter(self.initial_query)

    def _filter(self, query: str) -> None:
        list_widget = self.query_one("#palette-list", OptionList)
        empty_widget = self.query_one("#palette-empty", Static)

        query_lower = query.lower().lstrip("/")
        self._filtered = [
            cmd
            for cmd in self.commands
            if query_lower in cmd.lower()
            or query_lower in self.commands[cmd].lower()
        ]

        list_widget.clear_options()
        if self._filtered:
            for cmd in self._filtered:
                desc = self.commands[cmd]
                list_widget.add_option(Option(f"{cmd:<16} {desc}", id=cmd))
            list_widget.highlighted = 0
            list_widget.styles.display = "block"
            empty_widget.remove_class("visible")
        else:
            list_widget.styles.display = "none"
            empty_widget.add_class("visible")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter(event.value)

    def on_key(self, event) -> None:
        list_widget = self.query_one("#palette-list", OptionList)

        if event.key == "down":
            if list_widget.option_count > 0:
                current = list_widget.highlighted
                if current is None:
                    list_widget.highlighted = 0
                else:
                    list_widget.highlighted = min(
                        current + 1, list_widget.option_count - 1
                    )
            event.stop()
            event.prevent_default()
        elif event.key == "up":
            if list_widget.option_count > 0:
                current = list_widget.highlighted
                if current is None:
                    list_widget.highlighted = 0
                else:
                    list_widget.highlighted = max(current - 1, 0)
            event.stop()
            event.prevent_default()
        elif event.key in ("enter", "tab"):
            self._select()
            event.stop()
            event.prevent_default()
        elif event.key == "escape":
            self.dismiss(None)
            event.stop()
            event.prevent_default()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def _select(self) -> None:
        list_widget = self.query_one("#palette-list", OptionList)
        highlighted = list_widget.highlighted
        if highlighted is not None and 0 <= highlighted < list_widget.option_count:
            option = list_widget.get_option_at_index(highlighted)
            self.dismiss(option.id)
        else:
            self.dismiss(None)
