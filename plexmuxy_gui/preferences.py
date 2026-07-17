"""Persistent GUI-only preferences (appearance theme and interface language).

These preferences intentionally live outside ``config.json`` because they are
purely presentational choices made in the desktop shell, not muxing behaviour.

The GUI previously relied on ``localStorage`` for these values, but pywebview's
built-in HTTP server binds to a fresh random port on every launch. Because
``localStorage`` is isolated per-origin (scheme + host + port), a new port means
a new origin, so the stored theme/language could not be read back and the UI
always fell back to "System". Persisting through the Python backend keeps the
choice stable across restarts regardless of the serving port.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from plexmuxy.config import resolve_config_path

PREFERENCES_FILENAME = "gui-preferences.json"

VALID_THEMES = ("system", "light", "dark")
VALID_LOCALES = ("system", "en", "zh-CN", "zh-TW", "ru")

DEFAULT_PREFERENCES: dict[str, str] = {"theme": "system", "locale": "system"}


def preferences_path() -> Path:
    """Return the GUI preferences file, stored alongside the active config."""
    return resolve_config_path().parent / PREFERENCES_FILENAME


def load_preferences() -> dict[str, str]:
    """Load persisted GUI preferences, falling back to safe defaults."""
    path = preferences_path()
    if not path.exists():
        return dict(DEFAULT_PREFERENCES)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logging.debug("Could not read GUI preferences at %s", path, exc_info=True)
        return dict(DEFAULT_PREFERENCES)
    if not isinstance(raw, dict):
        return dict(DEFAULT_PREFERENCES)
    theme = raw.get("theme")
    locale = raw.get("locale")
    return {
        "theme": theme if theme in VALID_THEMES else DEFAULT_PREFERENCES["theme"],
        "locale": locale if locale in VALID_LOCALES else DEFAULT_PREFERENCES["locale"],
    }


def save_preferences(payload: dict[str, Any]) -> dict[str, str]:
    """Merge and atomically persist GUI preferences, returning the stored values."""
    if not isinstance(payload, dict):
        raise ValueError("Preferences payload must be an object")

    current = load_preferences()
    if "theme" in payload:
        theme = payload["theme"]
        if theme not in VALID_THEMES:
            raise ValueError(f"theme must be one of: {', '.join(VALID_THEMES)}")
        current["theme"] = theme
    if "locale" in payload:
        locale = payload["locale"]
        if locale not in VALID_LOCALES:
            raise ValueError(f"locale must be one of: {', '.join(VALID_LOCALES)}")
        current["locale"] = locale

    target = preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(current, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return current
