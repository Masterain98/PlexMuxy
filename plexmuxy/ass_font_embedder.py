"""Self-contained ASS generation with embedded fonts (Aegisub/libass compatible).

This mirrors the scheme used by tools such as assfonts: the subsetted (or full)
font binaries are uuencoded and placed in a ``[Fonts]`` section inserted just
before the ``[events]`` section of the subtitle file. Players built on libass
decode the embedded blobs and register them by the font's real family name, so
the existing style references keep working without any name rewriting.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

_FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"})


def _font_family_name(path: Path) -> str | None:
    """Best-effort family name used for an embedded font's ``fontname:`` label."""
    try:
        with TTFont(path) as font:
            name = font["name"]
            for name_id in (1, 16, 4):
                value = name.getDebugName(name_id)
                if value:
                    return value
    except Exception:
        return None
    return None


def _uuencode(data: bytes) -> str:
    """Aegisub/libass uuencode variant.

    Each 6-bit group is emitted as ``value + 33`` (``!`` for 0). There is no
    per-line length byte; newlines are inserted purely for readability every
    80 encoded characters.
    """
    out: list[str] = []
    written = 0
    length = len(data)
    for i in range(0, length, 3):
        b0 = data[i]
        b1 = data[i + 1] if i + 1 < length else 0
        b2 = data[i + 2] if i + 2 < length else 0
        n = (b0 << 16) | (b1 << 8) | b2
        groups = (length - i) if (length - i) < 3 else 3
        groups += 1  # 1 byte -> 2 chars, 2 bytes -> 3, 3 bytes -> 4
        for shift in (18, 12, 6, 0):
            if groups <= 0:
                break
            out.append(chr(((n >> shift) & 0x3F) + 33))
            groups -= 1
            written += 1
            if written == 80 and i + 3 < length:
                out.append("\n")
                written = 0
    return "".join(out)


def _read_ass_text(path: Path) -> tuple[str, str, bytes]:
    """Return (text, encoding_for_encode, bom_bytes).

    Reuses the canonical encoding detection from ``ass_analysis`` so that
    GB18030, Shift-JIS, and BOM-less UTF-16 ASS files accepted by the planner
    are decoded and re-encoded correctly instead of falling back to lossy
    UTF-8 replacement.
    """
    from .ass_analysis import AssDecodeError, _codec_for_encoding, _detect_encoding

    raw = path.read_bytes()
    encoding, bom, payload, issue = _detect_encoding(raw)
    if issue is not None and issue.rewrite_unsafe:
        raise AssDecodeError(issue.message)
    codec = _codec_for_encoding(encoding)
    text = payload.decode(codec, errors="strict")
    return text, codec, bom


def _encode_ass_text(text: str, encoding: str, bom: bytes) -> bytes:
    data = text.encode(encoding)
    if bom:
        return bom + data
    return data


def _build_fonts_block(font_paths: list[Path]) -> str:
    blocks: list[str] = []
    for path in font_paths:
        if path.suffix.lower() not in _FONT_SUFFIXES:
            continue
        if not path.exists():
            continue
        label = _font_family_name(path) or path.stem
        encoded = _uuencode(path.read_bytes())
        blocks.append(f"fontname: {label}\n{encoded}")
    return "\n".join(blocks)


def _insert_fonts_section(text: str, fonts_block: str) -> str:
    """Insert a ``[Fonts]`` section (containing ``fonts_block``) before ``[events]``."""
    lines = text.split("\n")
    insert_at = None
    for idx, line in enumerate(lines):
        if line.strip().lower() == "[events]":
            insert_at = idx
            break
    if insert_at is None:
        return text.rstrip("\n") + "\n\n[Fonts]\n\n" + fonts_block + "\n"
    return "\n".join(
        lines[:insert_at] + ["[Fonts]", fonts_block, ""] + lines[insert_at:]
    )


def embed_fonts_into_ass(
    subtitle_path: Path,
    font_paths: list[Path],
    output_path: Path,
) -> Path:
    """Write a self-contained ASS (fonts embedded in ``[Fonts]``) to ``output_path``."""
    text, encoding, bom = _read_ass_text(subtitle_path)
    fonts_block = _build_fonts_block(font_paths)
    new_text = _insert_fonts_section(text, fonts_block)
    output_path.write_bytes(_encode_ass_text(new_text, encoding, bom))
    return output_path
