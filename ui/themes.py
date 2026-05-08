"""Theme state — manages code syntax highlighting themes.

Used by MarkdownMessage and ToolCallWidget at render time.
Switched via Ctrl+D (light/dark) and Ctrl+Shift+D (cycle code theme).
"""

from __future__ import annotations

# ── Available code themes (Rich/Pygments) ──────────────

DARK_CODE_THEMES = [
    "one-dark",
    "monokai",
    "dracula",
    "github-dark",
    "material",
    "native",
]

LIGHT_CODE_THEMES = [
    "github-light",
    "friendly",
    "vs",
    "tango",
    "perldoc",
    "default",
]

ALL_CODE_THEMES = DARK_CODE_THEMES + LIGHT_CODE_THEMES

# ── State ──────────────────────────────────────────────

_current_code_theme = "one-dark"


def get_code_theme() -> str:
    """Return the current code theme name."""
    return _current_code_theme


def set_code_theme(theme: str) -> None:
    """Set the code theme (must be a valid Rich/Pygments theme)."""
    global _current_code_theme
    if theme in ALL_CODE_THEMES:
        _current_code_theme = theme


def cycle_code_theme() -> str:
    """Cycle to the next code theme within the current dark/light family.

    Returns the new theme name.
    """
    global _current_code_theme
    family = DARK_CODE_THEMES if _current_code_theme in DARK_CODE_THEMES else LIGHT_CODE_THEMES
    idx = family.index(_current_code_theme) if _current_code_theme in family else 0
    next_idx = (idx + 1) % len(family)
    _current_code_theme = family[next_idx]
    return _current_code_theme


def code_theme_for_mode(dark: bool) -> str:
    """Return a sensible default code theme for the given UI mode."""
    if dark:
        return "one-dark"
    return "github-light"


def switch_mode(dark: bool) -> str:
    """Called when the UI switches dark↔light. Picks a matching code theme.

    Returns the new theme name.
    """
    global _current_code_theme
    new_family = DARK_CODE_THEMES if dark else LIGHT_CODE_THEMES
    # If current theme is already in the target family, keep it
    if _current_code_theme in new_family:
        return _current_code_theme
    # Otherwise, pick the default for that mode
    _current_code_theme = code_theme_for_mode(dark)
    return _current_code_theme
