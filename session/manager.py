"""Conversation manager: token counting, context window auto-trimming.

Uses tiktoken (cl100k_base) for accurate token counting.
Falls back to a heuristic estimator if tiktoken is unavailable.
"""

from __future__ import annotations

# ── Model context windows ──────────────────────────────

MODEL_WINDOWS: dict[str, int] = {
    "deepseek-chat": 128_000,
    "deepseek-v4-pro": 1_000_000,
    "deepseek-reasoner": 128_000,
}

_DEFAULT_WINDOW = 128_000


def _detect_window(model: str) -> int:
    """Guess context window size from model name."""
    for prefix, size in MODEL_WINDOWS.items():
        if model.startswith(prefix):
            return size
    return _DEFAULT_WINDOW


# ── Token counter ──────────────────────────────────────

def _make_tokenizer():
    """Return a callable that counts tokens in a string."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return lambda text: len(enc.encode(text))
    except Exception:
        return None


def _heuristic_count(text: str) -> int:
    """Fallback token estimator.
    ~1.5 chars/token for CJK, ~4 chars/token for ASCII, blended.
    """
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u303f")
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4)


# ── Conversation manager ───────────────────────────────

class ConversationManager:
    """Token-aware multi-turn conversation with automatic trimming.

    - System prompts are preserved during trimming.
    - Trimming removes the oldest non-system message pairs first.
    - Trims to *buffer_ratio* of the model's context window.
    """

    def __init__(
        self,
        model: str,
        max_tokens: int | None = None,
        buffer_ratio: float = 0.8,
    ):
        self.model = model
        self.buffer_ratio = buffer_ratio
        self.max_tokens = max_tokens or _detect_window(model)
        self._messages: list[dict] = []
        self._tokenize = _make_tokenizer() or _heuristic_count
        self._trimmed_total = 0  # lifetime count of trimmed messages
        self._title = ""  # auto-set from first user message

    # ── Public API ──────────────────────────────────────

    @property
    def messages(self) -> list[dict]:
        """Return a *copy* of the current message list for API calls."""
        return list(self._messages)

    @property
    def title(self) -> str:
        """Session title (derived from first user message)."""
        return self._title

    @property
    def token_count(self) -> int:
        """Estimate total tokens in the conversation."""
        return sum(self._count(m["content"]) for m in self._messages)

    @property
    def token_limit(self) -> int:
        """Soft limit: buffer_ratio * max_tokens."""
        return int(self.max_tokens * self.buffer_ratio)

    @property
    def capacity_pct(self) -> float:
        """Percentage of soft limit currently used (0–100+)."""
        if self.token_limit == 0:
            return 0.0
        return (self.token_count / self.token_limit) * 100

    @property
    def trimmed_total(self) -> int:
        """How many messages have been trimmed over the conversation's life."""
        return self._trimmed_total

    def add(self, role: str, content: str) -> int:
        """Append a message and trim if needed.

        Returns:
            Number of messages removed during trimming (0 = none).
        """
        self._messages.append({"role": role, "content": content})

        # Auto-set title from first user message
        if role == "user" and not self._title:
            self._title = content[:60].replace("\n", " ").strip()

        return self._trim_if_needed()

    def set_system(self, content: str) -> None:
        """Replace or insert the system prompt (always preserved)."""
        self._messages = [m for m in self._messages if m["role"] != "system"]
        if content:
            self._messages.insert(0, {"role": "system", "content": content})

    def clear(self) -> None:
        """Reset the conversation."""
        self._messages.clear()
        self._title = ""

    # ── Serialization ───────────────────────────────────

    def to_dict(self) -> dict:
        """Export conversation to a serializable dict."""
        return {
            "model": self.model,
            "messages": list(self._messages),
            "title": self._title,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        max_tokens: int | None = None,
        buffer_ratio: float = 0.8,
    ) -> ConversationManager:
        """Restore a conversation from a serialized dict."""
        model = data.get("model", "deepseek-chat")
        inst = cls(
            model=model,
            max_tokens=max_tokens or _detect_window(model),
            buffer_ratio=buffer_ratio,
        )
        inst._messages = list(data.get("messages", []))
        inst._title = data.get("title", "")
        return inst

    # ── Internals ───────────────────────────────────────

    def _count(self, text: str) -> int:
        return self._tokenize(text)

    def _trim_if_needed(self) -> int:
        """Remove oldest non-system messages until under the soft limit."""
        removed = 0
        safety = len(self._messages) * 2  # prevent infinite loop

        while self.token_count > self.token_limit and len(self._messages) > 1:
            for i, msg in enumerate(self._messages):
                if msg["role"] != "system":
                    self._messages.pop(i)
                    self._trimmed_total += 1
                    removed += 1
                    break
            else:
                break  # nothing left to remove

            safety -= 1
            if safety <= 0:
                break
        return removed
