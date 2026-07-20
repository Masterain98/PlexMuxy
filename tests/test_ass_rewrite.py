from __future__ import annotations

from pathlib import Path

import pytest

from plexmuxy.ass_analysis import analyze_ass_file, parse_ass_bytes
from plexmuxy.ass_rewrite import AssRewriteError, rewrite_ass_bytes, rewrite_ass_document, rewrite_ass_file


def _script(*style_and_event_lines: str, newline: str = "\n") -> str:
    return newline.join(style_and_event_lines) + newline


def test_rewrite_file_changes_only_style_and_dialogue_font_references_and_preserves_utf16(tmp_path):
    text = _script(
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default, @Original Font,0,0",
        "Style: Other,Fallback Font,0,0",
        "[Events]",
        "Format: Style, Text",
        r"Dialogue: Default,{\fnOriginal Font}A{\fn@Original Font}縦{\fn}B",
        r"Comment: Default,{\fnOriginal Font}COMMENT",
        newline="\r\n",
    )
    original = b"\xff\xfe" + text.encode("utf-16-le")
    source = tmp_path / "source.ass"
    destination = tmp_path / "workspace" / "rewritten.ass"
    source.write_bytes(original)

    result = rewrite_ass_file(source, destination, {"original font": "PMX_ABC123"})

    assert source.read_bytes() == original
    assert result.source_path == source
    assert result.output_path == destination
    assert result.replacement_count == 3
    assert result.document.encoding == "utf-16-le"
    assert result.document.bom == b"\xff\xfe"
    assert result.document.newline == "\r\n"
    assert destination.read_bytes() == result.output_bytes
    rewritten_text = result.output_bytes[2:].decode("utf-16-le")
    assert "Style: Default, @PMX_ABC123,0,0" in rewritten_text
    assert "Style: Other,Fallback Font,0,0" in rewritten_text
    assert r"{\fnPMX_ABC123}A{\fn@PMX_ABC123}縦{\fn}B" in rewritten_text
    assert r"Comment: Default,{\fnOriginal Font}COMMENT" in rewritten_text
    assert result.rewritten_families == (("Original Font", "PMX_ABC123"),)
    assert analyze_ass_file(destination).safe_to_rewrite is True


def test_rewrite_uses_dynamic_format_and_preserves_dialogue_commas():
    text = _script(
        "[V4 Styles]",
        "Format: Bold, Fontname, Name, Italic",
        "Style: 0,Font A,Default,0",
        "[Events]",
        "Format: Text, Layer, Style",
        r"Dialogue: before,{\fnFont A}after,with,commas,0,Default",
    )

    result = rewrite_ass_document(parse_ass_bytes(text.encode("utf-8")), {"Font A": "PMX_A"})
    rewritten = result.output_bytes.decode("utf-8")

    assert "Style: 0,PMX_A,Default,0" in rewritten
    assert r"Dialogue: before,{\fnPMX_A}after,with,commas,0,Default" in rewritten
    assert result.document.events[0].text == r"before,{\fnPMX_A}after,with,commas"


def test_alias_mapping_is_single_pass_and_unmapped_families_remain_unchanged():
    text = _script(
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: First,Family A,0,0",
        "Style: Second,Family B,0,0",
        "Style: Third,Fallback,0,0",
        "[Events]",
        "Format: Style, Text",
        r"Dialogue: First,{\fnFamily A}A{\fnFamily B}B{\fnFallback}C",
    )

    rewritten = rewrite_ass_bytes(
        text.encode("utf-8"),
        {"Family A": "Family B", "Family B": "PMX_B"},
    ).decode("utf-8")

    assert "Style: First,Family B,0,0" in rewritten
    assert "Style: Second,PMX_B,0,0" in rewritten
    assert "Style: Third,Fallback,0,0" in rewritten
    assert r"{\fnFamily B}A{\fnPMX_B}B{\fnFallback}C" in rewritten


def test_rewrite_handles_fn_inside_transform_parentheses_and_leaves_fn_zero_reset():
    text = _script(
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default,Font A,0,0",
        "[Events]",
        "Format: Style, Text",
        r"Dialogue: Default,{\t(0,1000,\fnFont A)}X{\fn0}Y",
    )

    rewritten = rewrite_ass_bytes(
        text.encode("utf-8"),
        {"Font A": "PMX_A", "0": "SHOULD_NOT_BE_USED"},
    ).decode("utf-8")

    assert r"{\t(0,1000,\fnPMX_A)}X{\fn0}Y" in rewritten


def test_bomless_shift_jis_rewrite_can_become_all_ascii_without_encoding_misclassification(tmp_path):
    text = _script(
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default,MS ｺﾞｼｯｸ,0,0",
        "[Events]",
        "Format: Style, Text",
        "Dialogue: Default,ASCII only",
    )
    source = tmp_path / "shift-jis.ass"
    destination = tmp_path / "rewritten.ass"
    source.write_bytes(text.encode("shift_jis"))

    result = rewrite_ass_file(source, destination, {"MS ｺﾞｼｯｸ": "PMX_ASCII"})

    assert result.document.encoding == "shift_jis"
    assert result.document.bom == b""
    assert result.output_bytes.isascii()
    assert "Style: Default,PMX_ASCII,0,0" in result.output_bytes.decode("ascii")


def test_ambiguous_legacy_encoding_is_rejected_before_rewrite(tmp_path):
    text = _script(
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default,MS Gothic,0,0",
        "[Events]",
        "Format: Style, Text",
        "Dialogue: Default,漢字",
    )
    source = tmp_path / "ambiguous.ass"
    destination = tmp_path / "rewritten.ass"
    source.write_bytes(text.encode("shift_jis"))

    with pytest.raises(AssRewriteError, match="not safe to rewrite"):
        rewrite_ass_file(source, destination, {"MS Gothic": "PMX_A"})

    assert not destination.exists()


def test_unclosed_override_is_rejected_without_creating_destination(tmp_path):
    source = tmp_path / "broken.ass"
    destination = tmp_path / "temporary.ass"
    source.write_text(
        _script(
            "[V4+ Styles]",
            "Format: Name, Fontname, Bold, Italic",
            "Style: Default,Font A,0,0",
            "[Events]",
            "Format: Style, Text",
            r"Dialogue: Default,Text{\fnFont A",
        ),
        encoding="utf-8",
    )
    original = source.read_bytes()

    with pytest.raises(AssRewriteError, match="not safe to rewrite"):
        rewrite_ass_file(source, destination, {"Font A": "PMX_A"})

    assert source.read_bytes() == original
    assert not destination.exists()


def test_alias_not_representable_in_original_encoding_is_rejected(tmp_path):
    text = _script(
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default,MS Gothic,0,0",
        "[Events]",
        "Format: Style, Text",
        "Dialogue: Default,ｱ",
    )
    source = tmp_path / "shift-jis.ass"
    destination = tmp_path / "rewritten.ass"
    source.write_bytes(text.encode("shift_jis"))
    original = source.read_bytes()

    with pytest.raises(AssRewriteError, match="cannot be represented"):
        rewrite_ass_file(source, destination, {"MS Gothic": "PMX_😀"})

    assert source.read_bytes() == original
    assert not destination.exists()


def test_rewrite_refuses_to_overwrite_source_file(tmp_path):
    source = tmp_path / "source.ass"
    source.write_text(
        _script(
            "[V4+ Styles]",
            "Format: Name, Fontname, Bold, Italic",
            "Style: Default,Arial,0,0",
        ),
        encoding="utf-8",
    )
    original = source.read_bytes()

    with pytest.raises(AssRewriteError, match="must differ"):
        rewrite_ass_file(source, Path(str(source)), {"Arial": "PMX_A"})

    assert source.read_bytes() == original


def test_untouched_lines_remain_byte_exact_in_legacy_encoding():
    text = _script(
        "; 注释保持字节不变",
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default,字体甲,0,0",
        "[Events]",
        "Format: Style, Text",
        "Dialogue: Default,正文",
    )
    raw = text.encode("gb18030")
    untouched_line = "; 注释保持字节不变\n".encode("gb18030")

    output = rewrite_ass_bytes(raw, {"字体甲": "PMX_FONT"})

    assert output.startswith(untouched_line)
    document = parse_ass_bytes(output)
    assert document.encoding == "gb18030"
    assert document.styles[0].fontname == "PMX_FONT"
