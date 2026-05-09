"""Inline command suggestions dropdown for slash commands.

Displayed above the chat input when the user types '/'.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


class CommandSuggestions(Vertical):
    """A dropdown list of slash commands that appears above the input."""

    CSS = """
    CommandSuggestions {
        display: none;
        dock: bottom;
        height: auto;
        max-height: 12;
        width: 100%;
        background: $surface;
        border: solid $primary-darken-2;
        padding: 0;
    }

    CommandSuggestions.visible {
        display: block;
    }

    #suggestion-list {
        height: auto;
        max-height: 12;
        border: none;
        padding: 0;
    }

    #suggestion-list > .option-list--option {
        padding: 0 2;
    }

    #suggestion-list > .option-list--option-highlighted {
        background: $primary-darken-2;
    }

    #suggestion-empty {
        height: auto;
        padding: 1 2;
        color: $text-disabled;
        display: none;
    }

    #suggestion-empty.visible {
        display: block;
    }
    """

    def __init__(self, commands: dict[str, str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.commands = commands
        self._filtered: list[str] = []

    def compose(self) -> ComposeResult:
        yield OptionList(id="suggestion-list")
        yield Static("No matching commands", id="suggestion-empty")

    def filter(self, query: str) -> None:
        list_widget = self.query_one("#suggestion-list", OptionList)
        empty_widget = self.query_one("#suggestion-empty", Static)

        query_lower = query.lower()
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

    def next_option(self) -> None:
        list_widget = self.query_one("#suggestion-list", OptionList)
        if list_widget.option_count > 0:
            current = list_widget.highlighted
            if current is None:
                list_widget.highlighted = 0
            else:
                list_widget.highlighted = min(current + 1, list_widget.option_count - 1)

    def prev_option(self) -> None:
        list_widget = self.query_one("#suggestion-list", OptionList)
        if list_widget.option_count > 0:
            current = list_widget.highlighted
            if current is None:
                list_widget.highlighted = 0
            else:
                list_widget.highlighted = max(current - 1, 0)

    def get_selected(self) -> str | None:
        list_widget = self.query_one("#suggestion-list", OptionList)
        highlighted = list_widget.highlighted
        if highlighted is not None and 0 <= highlighted < list_widget.option_count:
            return list_widget.get_option_at_index(highlighted).id
        return None
