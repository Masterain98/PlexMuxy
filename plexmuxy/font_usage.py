from __future__ import annotations

import re
from pathlib import Path

STYLE_RE = re.compile(r"(?im)^Style:\s*[^,]*,\s*([^,\r\n]+)")
OVERRIDE_RE = re.compile(r"(?i)\\fn([^\\}\r\n]+)")


def normalize_font_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def extract_referenced_font_names(subtitle_path: Path) -> set[str]:
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
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return {normalize_font_name(font_path.stem)}
    names: set[str] = {normalize_font_name(font_path.stem)}
    try:
        font = TTFont(font_path, lazy=True, fontNumber=0)
        for record in font["name"].names:
            if record.nameID not in {1, 4, 6, 16, 17}:
                continue
            try:
                names.add(normalize_font_name(record.toUnicode()))
            except UnicodeError:
                continue
        font.close()
    except Exception:
        return names
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
