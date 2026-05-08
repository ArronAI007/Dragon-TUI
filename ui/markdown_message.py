"""Widget for rendering Markdown content in the chat.

Uses `rich.markdown.Markdown` for syntax-highlighted rendering.
Code theme is controlled by `ui.themes.get_code_theme()`.
"""

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual.widget import Widget

from ui.themes import get_code_theme


class MarkdownMessage(Widget):
    """Rich Markdown rendering widget with role-tinted borders.

    Roles:
        - "assistant": green border, Markdown rendering
        - "user": blue border, plain text
        - "thinking": dim border, italic text (reasoning tokens)
    """

    DEFAULT_CSS = """
    MarkdownMessage {
        border: solid $success;
        border-title-color: $success;
        padding: 1 2;
        margin: 0 0 1 0;
        height: auto;
    }
    MarkdownMessage.user {
        border: solid $primary;
        border-title-color: $primary;
    }
    MarkdownMessage.thinking {
        border: solid $surface-darken-2;
        border-title-color: $text-disabled;
    }
    """

    def __init__(self, content: str = "", *, role: str = "assistant"):
        super().__init__()
        self._content = content
        self.role = role

        if role == "user":
            self.add_class("user")
            self.border_title = "User"
        elif role == "thinking":
            self.add_class("thinking")
            self.border_title = "\U0001F9E0 Thinking"  # 🧠
        else:
            self.border_title = "AI"

    # ── Public API ──────────────────────────────────────

    @property
    def content(self) -> str:
        return self._content

    def update_content(self, text: str) -> None:
        """Replace the full content and schedule a re-render."""
        self._content = text
        self.refresh(layout=True)

    # ── Render ──────────────────────────────────────────

    def render(self) -> RenderableType:
        if not self._content:
            return Text("\u2026", style="dim italic")

        if self.role == "user":
            return Text.from_markup(self._content)

        if self.role == "thinking":
            return Text.from_markup(f"[dim italic]{self._content}[/]")

        # Assistant: full Markdown with syntax highlighting
        ct = get_code_theme()
        try:
            return Markdown(self._content, code_theme=ct, inline_code_theme=ct)
        except Exception:
            return Text(self._content)
