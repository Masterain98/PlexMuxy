from __future__ import annotations

import re

from fontTools.ttLib import TTFont
from pathlib import Path

from plexmuxy.ass_font_embedder import embed_fonts_into_ass

from tests.font_test_utils import build_test_ttf


def _uudecode(body: str) -> bytes:
    """Naive Aegisub/libass uudecode (trailing partial group bytes are harmless)."""
    body = re.sub(r"\s", "", body)
    out = bytearray()
    for i in range(0, len(body), 4):
        q = body[i : i + 4].ljust(4, " ")
        c = [(ord(ch) - 33) & 0x3F for ch in q]
        n = (c[0] << 18) | (c[1] << 12) | (c[2] << 6) | c[3]
        out += bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
    return bytes(out)


def _extract_font_blob(text: str, label: str) -> str:
    lines = text.splitlines()
    buf: list[str] = []
    cur: str | None = None
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith("fontname:"):
            if cur is not None:
                return "".join(buf)
            cur = s.split(":", 1)[1].strip()
            buf = []
        elif cur is not None and ln and not ln.startswith("["):
            buf.append(ln)
    if cur is not None:
        return "".join(buf)
    raise AssertionError("font not found")


def test_embed_fonts_into_ass_roundtrip(tmp_path: Path) -> None:
    family = "FZYaSong-B-GBK"
    font = build_test_ttf(tmp_path / "subset.ttf", family=family)
    src = tmp_path / "sub.ass"
    src.write_text(
        "[Script Info]\nTitle: x\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname\nStyle: D,FZYaSong-B-GBK,40\n\n"
        "[Events]\nFormat: L, T\nDialogue: 0,Hi\n",
        encoding="utf-8",
    )
    out = tmp_path / "sub.embedded.ass"
    embed_fonts_into_ass(src, [font], out)

    text = out.read_text(encoding="utf-8")
    low = text.lower()
    assert low.index("[fonts]") < low.index("[events]")

    blob = _uudecode(_extract_font_blob(text, family))
    rebuilt = tmp_path / "rebuilt.ttf"
    rebuilt.write_bytes(blob)
    with TTFont(rebuilt) as f:
        assert f["name"].getDebugName(1) == family


def test_embed_preserves_utf16_bom(tmp_path: Path) -> None:
    font = build_test_ttf(tmp_path / "f.ttf", family="FZTest")
    src = tmp_path / "sub.ass"
    src.write_bytes(b"\xff\xfe" + "x\n".encode("utf-16-le"))
    out = tmp_path / "e.ass"
    embed_fonts_into_ass(src, [font], out)
    assert out.read_bytes().startswith(b"\xff\xfe")


def test_embed_without_events_appends_at_end(tmp_path: Path) -> None:
    font = build_test_ttf(tmp_path / "f.ttf", family="NoEvents")
    src = tmp_path / "sub.ass"
    src.write_text("[Script Info]\nTitle: x\n", encoding="utf-8")
    out = tmp_path / "e.ass"
    embed_fonts_into_ass(src, [font], out)
    text = out.read_text(encoding="utf-8")
    assert "[Fonts]" in text
    assert text.strip().endswith("fontname: NoEvents") or "[Fonts]" in text


def test_embed_skips_non_font_attachments(tmp_path: Path) -> None:
    font = build_test_ttf(tmp_path / "f.ttf", family="FZTest")
    not_a_font = tmp_path / "readme.txt"
    not_a_font.write_text("not a font", encoding="utf-8")
    src = tmp_path / "sub.ass"
    src.write_text(
        "[Script Info]\nTitle: x\n\n[Events]\nFormat: L, T\nDialogue: 0,Hi\n",
        encoding="utf-8",
    )
    out = tmp_path / "e.ass"
    embed_fonts_into_ass(src, [font, not_a_font], out)
    text = out.read_text(encoding="utf-8")
    # Only the real font is embedded.
    assert text.count("fontname:") == 1
