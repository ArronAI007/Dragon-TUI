"""Configuration management for dragon-tui.

Reads from:
    1. Environment variables (DEEPSEEK_ prefix)
    2. config.toml in the project root
    3. ~/.dragon/config.toml (shared with the Rust TUI)

Environment variables take precedence over config file.
"""

import os
import sys
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


# ── TOML reader ────────────────────────────────────────

def _load_toml_data(path: Path) -> dict[str, Any]:
    """Read a TOML file and return the full parsed dict."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    if not path.exists():
        return {}

    with open(path, "rb") as f:
        return tomllib.load(f)


def _extract_flat(data: dict) -> dict[str, str]:
    """Extract flat key-value pairs from TOML data."""
    out: dict[str, str] = {}
    key_map = {
        "api_key": "api_key",
        "base_url": "base_url",
        "default_text_model": "default_model",
        "default_model": "default_model",
        "reasoning_effort": "reasoning_effort",
        "throttle_ms": "throttle_ms",
        "max_context_tokens": "max_context_tokens",
        "context_buffer_ratio": "context_buffer_ratio",
        "theme": "theme",
        "code_theme": "code_theme",
        "system_prompt": "system_prompt",
    }
    for toml_key, setting_key in key_map.items():
        if toml_key in data:
            out[setting_key] = str(data[toml_key])
    return out


def _extract_mcp_servers(data: dict) -> list[dict]:
    """Extract [[mcp_servers]] entries from TOML data.

    Supports two transport types:
        - stdio (default):  {"name", "command", "args", "env"}
        - sse:              {"name", "type"="sse", "url", "headers"}
    """
    servers = data.get("mcp_servers", [])
    if not isinstance(servers, list):
        return []
    result = []
    for s in servers:
        if not isinstance(s, dict) or "name" not in s:
            continue

        transport_type = s.get("type", "stdio")

        if transport_type == "sse" and "url" in s:
            result.append({
                "name": s["name"],
                "type": "sse",
                "url": s["url"],
                "headers": s.get("headers", {}),
            })
        elif "command" in s:
            result.append({
                "name": s["name"],
                "type": "stdio",
                "command": s["command"],
                "args": s.get("args", []),
                "env": s.get("env", {}),
            })
    return result


def _find_config(config_path: str | None = None) -> Path | None:
    """Find a config file, returning its path or None."""
    if config_path:
        p = Path(config_path)
        return p if p.exists() else None

    local = Path("config.toml")
    if local.exists():
        return local

    global_ = Path.home() / ".dragon" / "config.toml"
    if global_.exists():
        return global_

    return None


# ── Settings model ─────────────────────────────────────

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEEPSEEK_",
        extra="ignore",
    )

    # ── API ────────────────────────────────────────────
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"

    # ── Model ──────────────────────────────────────────
    default_model: str = "deepseek-chat"
    reasoning_effort: str = "medium"  # off | low | medium | high | max

    # ── UI ─────────────────────────────────────────────
    throttle_ms: int = 30
    max_context_tokens: int = 128_000
    context_buffer_ratio: float = 0.8

    # ── Theme ──────────────────────────────────────────
    theme: str = "dark"         # "dark" | "light"
    code_theme: str = "one-dark"

    # ── System prompt ──────────────────────────────────
    system_prompt: str = "You are Dragon TUI, a helpful AI assistant."

    # ── MCP (not managed by pydantic-settings) ────────
    # Set externally by load_settings().
    mcp_servers: list[dict] = []


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from config file + env vars (env wins)."""
    toml_path = _find_config(config_path)
    toml_data = _load_toml_data(toml_path) if toml_path else {}
    file_values = _extract_flat(toml_data)

    settings = Settings(**file_values)

    # Load MCP server configs (not handled by pydantic-settings)
    settings.mcp_servers = _extract_mcp_servers(toml_data)

    return settings
