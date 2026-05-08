"""Multi-line chat input with history navigation + fuzzy search.

Key bindings:
  - Enter         → submit
  - Shift+Enter   → insert newline
  - Ctrl+Enter    → insert newline (alt)
  - ↑ / ↓         → history navigation (when at first/last line)
  - Ctrl+P / Ctrl+N → history navigation (always)
  - Ctrl+R        → fuzzy search history
  - Tab           → insert 4 spaces

Posts `ChatInput.Submitted(text)` when the user presses Enter.
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class ChatInput(TextArea):
    """Multi-line input with send-via-Enter, history, and Ctrl+R fuzzy search."""

    # ── Custom message ──────────────────────────────────

    class Submitted(Message):
        """Posted when the user presses Enter to submit the text."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    # ── Lifecycle ───────────────────────────────────────

    def __init__(
        self,
        *,
        max_history: int = 200,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._history: list[str] = []
        self._history_cursor: int = -1
        self._draft_saved: str = ""
        self._max_history = max_history

        # ── Search mode state ─────────────────────────
        self._search_mode: bool = False
        self._search_query: str = ""
        self._search_matches: list[str] = []
        self._search_index: int = -1
        self._search_draft: str = ""  # saved text from before search

    # ── Public API ──────────────────────────────────────

    @property
    def history_count(self) -> int:
        return len(self._history)

    def add_to_history(self, text: str) -> None:
        """Record a submitted message (called externally after send)."""
        if not text.strip():
            return
        if self._history and self._history[0] == text:
            return
        self._history.insert(0, text)
        if len(self._history) > self._max_history:
            self._history.pop()
        self._history_cursor = -1

    # ── Persistence ───────────────────────────────────

    def save_history(self, path: str) -> None:
        import json
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._history, ensure_ascii=False, indent=2))

    def load_history(self, path: str) -> None:
        import json
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list):
                self._history = data[:self._max_history]
                self._history_cursor = -1
        except (json.JSONDecodeError, OSError):
            pass

    # ── Key handling ────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        """Intercept keys before TextArea's own handling."""

        key = event.key
        shift = "shift+" in key
        ctrl = "ctrl+" in key

        # ── Ctrl+R: enter / cycle search ──────────────
        if ctrl and key == "r":
            if self._search_mode:
                self._search_next()
            else:
                self._enter_search()
            event.prevent_default()
            event.stop()
            return

        # ── Search mode: route to search handler ──────
        if self._search_mode:
            self._on_search_key(event)
            event.prevent_default()
            event.stop()
            return

        # ── Enter (submit) ─────────────────────────────
        if key == "enter" and not shift:
            text = self.text
            if text.strip():
                self.clear()
                self.post_message(self.Submitted(text))
            event.prevent_default()
            event.stop()
            return

        # ── Shift+Enter or Ctrl+Enter (newline) ────────
        if key == "enter" and (shift or ctrl):
            self.insert("\n")
            event.prevent_default()
            event.stop()
            return

        # ── Up arrow / Ctrl+P (history back) ───────────
        if key == "up" or (ctrl and key == "p"):
            row, _col = self.cursor_location
            if row == 0:
                self._history_prev()
                event.prevent_default()
                event.stop()
                return

        # ── Down arrow / Ctrl+N (history forward) ──────
        if key == "down" or (ctrl and key == "n"):
            row, _col = self.cursor_location
            total_lines = self.document.line_count - 1
            if row >= total_lines:
                self._history_next()
                event.prevent_default()
                event.stop()
                return

        # ── Tab (insert 4 spaces) ──────────────────────
        if key == "tab":
            self.insert("    ")
            event.prevent_default()
            event.stop()
            return

    # ── Search mode ─────────────────────────────────────

    def _enter_search(self) -> None:
        """Activate fuzzy search mode."""
        self._search_mode = True
        self._search_draft = self.text
        self._search_query = ""
        self._search_matches = []
        self._search_index = -1
        self.clear()
        self.border_title = "🔍 search: "
        self.border_subtitle = "Ctrl+R next | Enter select | Esc cancel"

    def _exit_search(self, *, cancel: bool = False) -> None:
        """Leave search mode, optionally restoring the previous draft."""
        if cancel:
            self.load_text(self._search_draft)
        # else: keep the currently displayed match
        self._search_mode = False
        self._search_query = ""
        self._search_matches.clear()
        self._search_index = -1
        self.border_title = ""
        self.border_subtitle = ""
        if self.text:
            self.cursor_location = (self.document.line_count - 1, 0)

    def _on_search_key(self, event: events.Key) -> None:
        """Handle key presses while in search mode."""
        key = event.key
        ctrl = "ctrl+" in key

        if key == "escape":
            self._exit_search(cancel=True)
            return

        if key == "enter" and "shift+" not in key:
            self._exit_search(cancel=False)
            return

        if ctrl and key == "r":
            self._search_next()
            return

        if key == "backspace":
            if self._search_query:
                self._search_query = self._search_query[:-1]
                self._update_search_matches()
            return

        # Printable character → append to search query
        if len(key) == 1 and key.isprintable() and not ctrl:
            self._search_query += key
            self._update_search_matches()
            return

    def _update_search_matches(self) -> None:
        """Filter history by the current search query."""
        q = self._search_query
        if not q:
            self._search_matches = []
            self._search_index = -1
            self.clear()
            self.border_title = "🔍 search: "
            self.border_subtitle = "Ctrl+R next | Enter select | Esc cancel"
            return

        self._search_matches = [
            h for h in self._history if _fuzzy_match(q, h)
        ]
        self._search_index = 0 if self._search_matches else -1

        if self._search_matches:
            match = self._search_matches[self._search_index]
            self.load_text(match)
            self.border_title = f"🔍 search: {q}"
            self.border_subtitle = f"match {self._search_index + 1}/{len(self._search_matches)}"
        else:
            self.clear()
            self.border_title = f"🔍 search: {q}"
            self.border_subtitle = "no matches"

    def _search_next(self) -> None:
        """Cycle to the next matching history entry."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        match = self._search_matches[self._search_index]
        self.load_text(match)
        self.border_subtitle = f"match {self._search_index + 1}/{len(self._search_matches)}"

    # ── History internals ───────────────────────────────

    def _history_prev(self) -> None:
        """Step backward through history."""
        if not self._history:
            return
        if self._history_cursor == -1:
            self._draft_saved = self.text
        if self._history_cursor < len(self._history) - 1:
            self._history_cursor += 1
            self.load_text(self._history[self._history_cursor])
            self.cursor_location = (self.document.line_count - 1, 0)

    def _history_next(self) -> None:
        """Step forward through history."""
        if self._history_cursor <= 0:
            self._history_cursor = -1
            self.load_text(self._draft_saved)
            self._draft_saved = ""
            self.cursor_location = (self.document.line_count - 1, 0)
            return
        self._history_cursor -= 1
        self.load_text(self._history[self._history_cursor])
        self.cursor_location = (self.document.line_count - 1, 0)


# ── Fuzzy match helper ──────────────────────────────────

def _fuzzy_match(query: str, text: str) -> bool:
    """Check if all query characters appear in order (case-insensitive).

    This is a classic fzf-style sequential match — no scoring, just inclusion.
    """
    qi = 0
    ql = query.lower()
    tl = text.lower()
    for ch in tl:
        if qi < len(ql) and ch == ql[qi]:
            qi += 1
    return qi == len(ql)
