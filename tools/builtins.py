"""Built-in tools for the Dragon TUI.

Tools provided:
    read_file    — read a file from the workspace
    list_dir     — list directory contents
    grep_files   — search for a pattern in files
    exec_shell   — run a shell command (requires approval)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.registry import ToolRegistry

# ── Shared registry instance ────────────────────────────

registry = ToolRegistry()

# ── Workspace root ──────────────────────────────────────

WORKSPACE = Path.cwd()


def _safe_path(raw: str) -> Path:
    """Resolve a path, rejecting traversal outside the workspace."""
    p = (WORKSPACE / raw).resolve()
    if not str(p).startswith(str(WORKSPACE.resolve())):
        raise ValueError(f"Path escapes workspace: {raw}")
    return p


# ── Tools ───────────────────────────────────────────────

@registry.register(
    name="read_file",
    description="Read a file from the filesystem. Returns the file contents.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file, relative to the workspace root.",
            },
            "lines": {
                "type": "string",
                "description": "Optional line range, e.g. '1-50' or '100'.",
            },
        },
        "required": ["path"],
    },
)
async def read_file(path: str, lines: str = "") -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"File not found: {path}"
    if not p.is_file():
        return f"Not a file: {path}"

    try:
        text = p.read_text()
    except Exception as exc:
        return f"Error reading {path}: {exc}"

    if lines:
        return _slice_lines(text, lines)

    # Truncate very large files
    max_chars = 50_000
    if (n := len(text)) > max_chars:
        return text[:max_chars] + f"\n\n... (truncated {n - max_chars:,} chars)"
    return text


@registry.register(
    name="list_dir",
    description="List entries in a directory.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path relative to workspace root (default: '.')",
            },
        },
    },
)
async def list_dir(path: str = ".") -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"Directory not found: {path}"
    if not p.is_dir():
        return f"Not a directory: {path}"

    entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    lines = []
    for e in entries:
        suffix = "/" if e.is_dir() else ""
        lines.append(f"  {e.name}{suffix}")
    return "\n".join(lines) if lines else "(empty)"


@registry.register(
    name="grep_files",
    description="Search for a regex pattern in files within the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search (default: '.')",
            },
            "include": {
                "type": "string",
                "description": "Glob patterns for files to include, comma-separated. E.g. '*.py,*.toml'",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 30)",
            },
        },
        "required": ["pattern"],
    },
)
async def grep_files(
    pattern: str,
    path: str = ".",
    include: str = "",
    max_results: int = 30,
) -> str:
    import re

    p = _safe_path(path)
    if not p.exists():
        return f"Path not found: {path}"

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Invalid regex: {exc}"

    # Resolve include patterns
    include_globs = [g.strip() for g in include.split(",") if g.strip()] if include else []
    if not include_globs:
        include_globs = ["*"]

    results: list[str] = []
    files = [p] if p.is_file() else p.rglob("*")

    for fp in files:
        if not fp.is_file():
            continue
        # Match include patterns
        rel = str(fp.relative_to(p)) if p.is_dir() else fp.name
        if not any(fp.match(g) for g in include_globs):
            continue
        # Skip binary-looking files
        try:
            text = fp.read_text()
        except Exception:
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                results.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                if len(results) >= max_results:
                    break
        if len(results) >= max_results:
            break

    if not results:
        return f"No matches for '{pattern}'"
    if len(results) >= max_results:
        results.append(f"... (capped at {max_results} results)")
    return "\n".join(results)


@registry.register(
    name="exec_shell",
    description="Execute a shell command. Requires user approval.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: workspace root)",
            },
        },
        "required": ["command"],
    },
    requires_approval=True,
)
async def exec_shell(command: str, cwd: str = "") -> str:
    work_dir = _safe_path(cwd) if cwd else WORKSPACE
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = result.stdout
        if result.stderr:
            out += "\n[stderr]\n" + result.stderr
        if not out.strip():
            out = f"(exit code {result.returncode})"
        return out
    except subprocess.TimeoutExpired:
        return "Command timed out (30s)"
    except Exception as exc:
        return f"Error: {exc}"


# ── Helpers ─────────────────────────────────────────────

def _slice_lines(text: str, spec: str) -> str:
    lines = text.splitlines()
    if "-" in spec:
        a, b = spec.split("-", 1)
        start = int(a) - 1 if a else 0
        end = int(b) if b else len(lines)
        return "\n".join(lines[start:end])
    else:
        n = int(spec) - 1
        return lines[n] if 0 <= n < len(lines) else "(line out of range)"
