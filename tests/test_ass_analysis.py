from __future__ import annotations

from pathlib import Path

import pytest

from plexmuxy.ass_analysis import analyze_ass_bytes, iter_override_tags, parse_ass_bytes


def _script(*event_lines: str, newline: str = "\n") -> str:
    lines = [
        "[V4+ Styles]",
        "Format: Name, Fontname, Bold, Italic",
        "Style: Default,Arial,0,0",
        "[Events]",
        "Format: Style, Text",
        *event_lines,
    ]
    return newline.join(lines) + newline


def _usage_map(analysis):
    return {
        (usage.requested_family, usage.weight, usage.italic, usage.vertical): set(usage.codepoints)
        for usage in analysis.usages
    }


def test_parses_v4_and_v4_plus_styles_using_each_section_format():
    text = "\n".join(
        [
            "[V4 Styles]",
            "Format: Bold, Name, Italic, Fontname",
            "Style: -1,Legacy,0,Legacy Font",
            "[V4+ Styles]",
            "Format: Fontname, Italic, Name, Bold",
            "Style: Modern Font,-1,Modern,0",
            "[Events]",
            "Format: Text, Style, Layer",
            "Dialogue: Text, with, commas,Legacy,0",
            "Dialogue: Modern text,Modern,0",
        ]
    )

    analysis = analyze_ass_bytes(text.encode("utf-8"))

    assert [(style.name, style.fontname, style.bold, style.italic) for style in analysis.document.styles] == [
        ("Legacy", "Legacy Font", True, False),
        ("Modern", "Modern Font", False, True),
    ]
    assert analysis.document.events[0].text == "Text, with, commas"
    assert analysis.complete is True
    usages = _usage_map(analysis)
    assert ord("T") in usages[("Legacy Font", 700, False, False)]
    assert ord("M") in usages[("Modern Font", 400, True, False)]


@pytest.mark.parametrize(
    ("expected_encoding", "codec", "bom", "sample"),
    [
        ("utf-8-sig", "utf-8", b"\xef\xbb\xbf", "UTF-8 字幕"),
        ("utf-8", "utf-8", b"", "UTF-8 字幕"),
        ("utf-16-le", "utf-16-le", b"\xff\xfe", "UTF-16 字幕"),
        ("utf-16-be", "utf-16-be", b"\xfe\xff", "UTF-16 字幕"),
        ("gb18030", "gb18030", b"", "简体中文字幕"),
        ("shift_jis", "shift_jis", b"", "字幕テスト"),
    ],
)
def test_supported_encodings_round_trip_exact_bytes(expected_encoding, codec, bom, sample):
    text = _script(f"Dialogue: Default,{sample}", newline="\r\n")
    raw = bom + text.encode(codec)
    encoding_hint = "shift_jis" if expected_encoding == "shift_jis" else None

    document = parse_ass_bytes(raw, encoding_hint=encoding_hint)
    analysis = analyze_ass_bytes(raw, encoding_hint=encoding_hint)

    assert document.encoding == expected_encoding
    assert document.bom == bom
    assert document.newline == "\r\n"
    assert document.to_bytes() == raw
    assert ord(sample[-1]) in set().union(*(set(usage.codepoints) for usage in analysis.usages))


@pytest.mark.parametrize(("codec", "sample"), [("utf-16-le", "小字集"), ("utf-16-be", "小字集")])
def test_bomless_utf16_is_detected_from_ass_ascii_structure(codec, sample):
    raw = _script(f"Dialogue: Default,{sample}").encode(codec)

    document = parse_ass_bytes(raw)

    assert document.encoding == codec
    assert document.bom == b""
    assert document.events[0].text == sample


def test_override_state_machine_tracks_font_weight_italic_reset_drawing_and_escapes(tmp_path):
    text = "\n".join(
        [
            "[V4+ Styles]",
            "Format: Name, Fontname, Bold, Italic",
            "Style: Default,Arial,0,0",
            "Style: Alt,@Yu Mincho,-1,-1",
            "[Events]",
            "Format: Style, Text",
            (
                r"Dialogue: Default,A{\fnCourier New}B{\b1}C{\i1}D{\rAlt}縦"
                r"{\p1}m 0 0 l 10 10{\p0}\h{\fn}戻\N次\n行{\r}Z"
            ),
        ]
    )
    source = tmp_path / "state.ass"
    source.write_text(text, encoding="utf-8")

    analysis = analyze_ass_bytes(source.read_bytes(), source_path=source)
    usages = _usage_map(analysis)

    assert {ord("A"), ord("Z")} <= usages[("Arial", 400, False, False)]
    assert ord("B") in usages[("Courier New", 400, False, False)]
    assert ord("C") in usages[("Courier New", 700, False, False)]
    assert ord("D") in usages[("Courier New", 700, True, False)]
    vertical = usages[("Yu Mincho", 700, True, True)]
    assert {ord("縦"), ord("戻"), ord("次"), ord("行"), 0x0020, 0x00A0} <= vertical
    assert ord("m") not in set().union(*usages.values())
    assert all(usage.subtitle_paths == (source,) for usage in analysis.usages)
    assert analysis.complete is True
    assert analysis.safe_to_rewrite is True


def test_explicit_bold_weights_are_aggregated_separately():
    text = _script(r"Dialogue: Default,{\b100}x{\b500}y{\b750}w{\b900}z{\b0}q")

    usages = _usage_map(analyze_ass_bytes(text.encode("utf-8")))

    assert ord("x") in usages[("Arial", 100, False, False)]
    assert ord("y") in usages[("Arial", 500, False, False)]
    assert ord("w") in usages[("Arial", 750, False, False)]
    assert ord("z") in usages[("Arial", 900, False, False)]
    assert ord("q") in usages[("Arial", 400, False, False)]


def test_minus_one_font_flags_restore_current_style_defaults():
    text = "\n".join(
        [
            "[V4+ Styles]",
            "Format: Name, Fontname, Bold, Italic",
            "Style: Default,Arial,0,0",
            "Style: Alt,Alt Font,-1,-1",
            "[Events]",
            "Format: Style, Text",
            r"Dialogue: Default,{\b1\i1}A{\b-1\i-1}B{\rAlt\b0\i0}C{\b-1\i-1}D",
        ]
    )

    analysis = analyze_ass_bytes(text.encode("utf-8"))
    usages = _usage_map(analysis)

    assert ord("A") in usages[("Arial", 700, True, False)]
    assert ord("B") in usages[("Arial", 400, False, False)]
    assert ord("C") in usages[("Alt Font", 400, False, False)]
    assert ord("D") in usages[("Alt Font", 700, True, False)]
    assert analysis.complete is True


def test_fn_zero_restores_current_style_family_after_style_reset():
    text = "\n".join(
        [
            "[V4+ Styles]",
            "Format: Name, Fontname, Bold, Italic",
            "Style: Default,Arial,0,0",
            "Style: Alt,Alt Font,0,0",
            "[Events]",
            "Format: Style, Text",
            r"Dialogue: Default,{\fnTemporary}A{\fn0}B{\rAlt\fnTemporary}C{\fn0}D",
        ]
    )

    usages = _usage_map(analyze_ass_bytes(text.encode("utf-8")))

    assert ord("A") in usages[("Temporary", 400, False, False)]
    assert ord("B") in usages[("Arial", 400, False, False)]
    assert ord("C") in usages[("Temporary", 400, False, False)]
    assert ord("D") in usages[("Alt Font", 400, False, False)]


def test_nested_transform_font_tag_is_parsed_and_applied_without_losing_parenthesis_boundary():
    text = _script(r"Dialogue: Default,{\t(0,1000,\fnAnimated Font)}X")

    analysis = analyze_ass_bytes(text.encode("utf-8"))
    tags = iter_override_tags(r"\t(0,1000,\fnAnimated Font)")

    assert [(tag.name, tag.parameter, tag.parenthesis_depth) for tag in tags] == [
        ("fn", "Animated Font", 1)
    ]
    assert not any(issue.code == "animated_font_override" for issue in analysis.issues)
    assert analysis.complete is True
    assert analysis.safe_to_rewrite is True
    assert ord("X") in _usage_map(analysis)[("Animated Font", 400, False, False)]


def test_ambiguous_bomless_legacy_encoding_blocks_lossy_analysis_and_rewrite():
    raw = _script("Dialogue: Default,漢字").encode("shift_jis")

    analysis = analyze_ass_bytes(raw)
    explicitly_decoded = parse_ass_bytes(raw, encoding_hint="shift_jis")

    assert any(issue.code == "ambiguous_legacy_encoding" for issue in analysis.issues)
    assert analysis.complete is False
    assert analysis.safe_to_rewrite is False
    assert explicitly_decoded.events[0].text == "漢字"


def test_comment_events_do_not_contribute_font_or_characters():
    text = _script(
        r"Comment: Default,{\fnComment Font}COMMENT_ONLY",
        "Dialogue: Default,Visible",
    )

    analysis = analyze_ass_bytes(text.encode("utf-8"))

    assert {usage.requested_family for usage in analysis.usages} == {"Arial"}
    all_codepoints = set().union(*(set(usage.codepoints) for usage in analysis.usages))
    assert ord("V") in all_codepoints
    assert ord("C") not in all_codepoints


def test_unknown_dialogue_and_reset_styles_are_reported_as_incomplete():
    text = _script(
        "Dialogue: Missing,Skipped",
        r"Dialogue: Default,A{\rAlsoMissing}B",
    )

    analysis = analyze_ass_bytes(text.encode("utf-8"))

    assert {issue.code for issue in analysis.issues} >= {"unknown_dialogue_style", "unknown_reset_style"}
    assert analysis.complete is False
    assert analysis.safe_to_rewrite is True


def test_unclosed_override_marks_document_unsafe_to_rewrite():
    text = _script(r"Dialogue: Default,Before{\fnBroken Font after")

    analysis = analyze_ass_bytes(text.encode("utf-8"))

    assert any(issue.code == "unclosed_override_block" for issue in analysis.issues)
    assert analysis.complete is False
    assert analysis.safe_to_rewrite is False


def test_original_mixed_line_endings_and_final_line_are_preserved():
    raw = (
        b"[V4+ Styles]\r\n"
        b"Format: Name, Fontname, Bold, Italic\n"
        b"Style: Default,Arial,0,0\r"
        b"[Events]\r\n"
        b"Format: Style, Text\n"
        b"Dialogue: Default,No final newline"
    )

    document = parse_ass_bytes(raw, source_path=Path("mixed.ass"))

    assert [line.ending for line in document.lines] == ["\r\n", "\n", "\r", "\r\n", "\n", ""]
    assert document.to_bytes() == raw
