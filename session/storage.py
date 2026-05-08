"""JSON-based session persistence.

Storage layout:
    {session_dir}/
    ├── index.json          # list of session metadata
    └── {session_id}.json   # individual session data
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Helpers ────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ── Session record ─────────────────────────────────────

class SessionRecord:
    """Metadata + data for one saved session."""

    __slots__ = (
        "id",
        "title",
        "created_at",
        "updated_at",
        "model",
        "messages",
    )

    def __init__(
        self,
        id: str,
        title: str = "",
        created_at: str = "",
        updated_at: str = "",
        model: str = "deepseek-chat",
        messages: list[dict] | None = None,
    ):
        self.id = id
        self.title = title
        self.created_at = created_at or _now_iso()
        self.updated_at = updated_at or _now_iso()
        self.model = model
        self.messages = messages or []

    @classmethod
    def from_dict(cls, data: dict) -> SessionRecord:
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            model=data.get("model", "deepseek-chat"),
            messages=data.get("messages", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "messages": self.messages,
        }

    @property
    def message_count(self) -> int:
        return len(self.messages)


# ── Storage engine ─────────────────────────────────────

class SessionStorage:
    """Manages session files on disk."""

    INDEX_FILE = "index.json"

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    # ── Read ────────────────────────────────────────────

    def _read_index(self) -> list[dict]:
        path = self.directory / self.INDEX_FILE
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _write_index(self, records: list[dict]) -> None:
        path = self.directory / self.INDEX_FILE
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2))

    def list_sessions(self) -> list[dict]:
        """Return session metadata sorted newest-first."""
        records = self._read_index()
        records.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return records

    def load(self, session_id: str) -> SessionRecord | None:
        """Load a single session by ID."""
        path = self.directory / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return SessionRecord.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    # ── Write ───────────────────────────────────────────

    def save(self, record: SessionRecord) -> None:
        """Persist a session record to disk."""
        record.updated_at = _now_iso()

        # Write session file
        path = self.directory / f"{record.id}.json"
        path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
        )

        # Update index
        index = self._read_index()
        # Remove existing entry for this ID
        index = [r for r in index if r["id"] != record.id]
        index.append(
            {
                "id": record.id,
                "title": record.title,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "model": record.model,
                "message_count": record.message_count,
            }
        )
        self._write_index(index)

    def delete(self, session_id: str) -> bool:
        """Remove a session file and its index entry."""
        path = self.directory / f"{session_id}.json"
        deleted = False
        if path.exists():
            path.unlink()
            deleted = True

        index = [r for r in self._read_index() if r["id"] != session_id]
        self._write_index(index)
        return deleted

    def new_id(self) -> str:
        """Generate a unique session ID."""
        base = _make_id()
        sid = base
        n = 1
        while (self.directory / f"{sid}.json").exists():
            sid = f"{base}-{n}"
            n += 1
        return sid
