from __future__ import annotations

import json
import locale
import os
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = {"en", "zh-CN"}


class Messages:
    def __init__(self, language: str) -> None:
        self.language = normalize_language(language)
        self._fallback = _load_catalog("en")
        self._catalog = self._fallback if self.language == "en" else _load_catalog(self.language)

    def get(self, key: str, default: str | None = None, **values: Any) -> str:
        template = self._catalog.get(key, self._fallback.get(key, default if default is not None else key))
        try:
            return str(template).format(**values)
        except (KeyError, ValueError):
            return str(self._fallback.get(key, default if default is not None else key))


def normalize_language(value: str | None) -> str:
    selected = str(value or "system").strip()
    if selected == "system":
        selected = _system_language()
    aliases = {"zh": "zh-CN", "zh_cn": "zh-CN", "zh-cn": "zh-CN", "en_us": "en", "en-us": "en"}
    normalized = aliases.get(selected.casefold(), selected)
    return normalized if normalized in SUPPORTED_LANGUAGES else "en"


def requested_language(argv: list[str]) -> str:
    for index, item in enumerate(argv):
        if item == "--language" and index + 1 < len(argv):
            return normalize_language(argv[index + 1])
        if item.startswith("--language="):
            return normalize_language(item.partition("=")[2])
    return normalize_language(os.environ.get("PLEXMUXY_LANGUAGE", "system"))


def _system_language() -> str:
    name = locale.getlocale()[0] or os.environ.get("LANG", "")
    return "zh-CN" if str(name).casefold().startswith("zh") else "en"


def _load_catalog(language: str) -> dict[str, str]:
    path = Path(__file__).resolve().parent / "locales" / f"{language}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
