from __future__ import annotations

import re
from pathlib import Path

from .ass_analysis import iter_override_tags, parse_ass_file
from .font_catalog import (
    build_font_catalog,
)
from .font_catalog import (
    normalize_font_name as normalize_catalog_name,
)

STYLE_RE = re.compile(r"(?im)^Style:\s*[^,]*,\s*([^,\r\n]+)")
OVERRIDE_RE = re.compile(r"(?i)\\fn([^\\}\r\n]+)")


def normalize_font_name(name: str) -> str:
    return normalize_catalog_name(name)


def extract_referenced_font_names(subtitle_path: Path) -> set[str]:
    names: set[str] = set()
    try:
        document = parse_ass_file(subtitle_path)
        names.update(normalize_font_name(style.fontname) for style in document.styles)
        for event in document.events:
            if event.kind.casefold() != "dialogue":
                continue
            for block in re.findall(r"\{([^}]*)}", event.text):
                for tag in iter_override_tags(block):
                    if tag.name == "fn" and tag.parameter.strip() not in {"", "0"}:
                        names.add(normalize_font_name(tag.parameter))
    except (OSError, UnicodeError, ValueError):
        pass
    if names:
        return {name for name in names if name}

    # Keep a best-effort compatibility path for malformed legacy scripts. Such
    # input is never accepted by subset mode, but referenced mode can still
    # attach a conservatively selected complete font.
    raw = subtitle_path.read_bytes()
    text = ""
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "shift_jis"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeError:
            continue
    if not text:
        text = raw.decode("utf-8", errors="replace")
    names = {normalize_font_name(match) for match in STYLE_RE.findall(text)}
    names.update(normalize_font_name(match) for match in OVERRIDE_RE.findall(text))
    return {name for name in names if name}


def font_family_names(font_path: Path) -> set[str]:
    names: set[str] = {normalize_font_name(font_path.stem)}
    catalog = build_font_catalog([font_path])
    for face in catalog.faces:
        for value in (
            *face.family_names,
            *face.typographic_family_names,
            *face.full_names,
            *face.postscript_names,
        ):
            names.add(normalize_font_name(value))
    return {name for name in names if name}


def select_referenced_fonts(subtitles: list[Path], fonts: list[Path]) -> tuple[list[Path], set[str]]:
    referenced: set[str] = set()
    for subtitle in subtitles:
        referenced.update(extract_referenced_font_names(subtitle))
    selected: list[Path] = []
    found: set[str] = set()
    for font in fonts:
        family_names = font_family_names(font)
        matches = referenced & family_names
        if matches:
            selected.append(font)
            found.update(matches)
    return selected, referenced - found
