from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

from plexmuxy.font_catalog import build_font_catalog, normalize_font_name
from plexmuxy.font_prepare import (
    SubsetWorkspace,
    build_subset_intent,
    compress_codepoints,
    expand_codepoint_ranges,
    materialize_font_source,
)
from plexmuxy.models import FontConfig, FontUsage
from tests.font_test_utils import build_test_ttf


def test_build_subset_intent_groups_faces_and_uses_deterministic_alias(tmp_path: Path) -> None:
    regular = build_test_ttf(tmp_path / "regular.ttf", family="Intent Family", style="Regular", characters=" AB")
    bold = build_test_ttf(tmp_path / "bold.ttf", family="Intent Family", style="Bold", weight=700, characters=" AB")
    subtitle = tmp_path / "show.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    catalog = build_font_catalog([regular, bold]).faces
    usages = [
        FontUsage("Intent Family", normalize_font_name("Intent Family"), 400, False, (32, 65), (subtitle,)),
        FontUsage("Intent Family", normalize_font_name("Intent Family"), 700, False, (32, 66), (subtitle,)),
    ]

    first = build_subset_intent([subtitle], usages, catalog)
    second = build_subset_intent([subtitle], usages, catalog)

    assert first == second
    assert first.issues == ()
    assert len(first.groups) == 1
    assert len(first.groups[0].faces) == 2
    assert first.groups[0].codepoint_ranges == ((32, 32), (65, 66))
    assert first.groups[0].alias_family.startswith("PMX_")
    assert first.summary.matched_face_count == 2


def test_build_subset_intent_reports_missing_and_ambiguous_fonts(tmp_path: Path) -> None:
    one = build_test_ttf(tmp_path / "one.ttf", family="Ambiguous", characters=" A")
    two = build_test_ttf(tmp_path / "two.ttf", family="Ambiguous", characters=" AB")
    subtitle = tmp_path / "show.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    usages = [
        FontUsage("Missing", "missing", 400, False, (65,), (subtitle,)),
        FontUsage("Ambiguous", "ambiguous", 400, False, (65,), (subtitle,)),
    ]

    intent = build_subset_intent([subtitle], usages, build_font_catalog([one, two]).faces)

    assert {issue.code for issue in intent.issues} == {"font_family_missing", "font_match_ambiguous"}
    assert intent.groups == ()


def test_build_subset_intent_reports_predictable_full_font_fallback(tmp_path: Path) -> None:
    source = build_test_ttf(tmp_path / "color.ttf", family="Color Family", characters=" A")
    subtitle = tmp_path / "show.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    face = replace(build_font_catalog([source]).faces[0], has_color=True)
    usage = FontUsage("Color Family", "color family", 400, False, (32, 65), (subtitle,))

    intent = build_subset_intent([subtitle], [usage], [face])

    assert intent.issues == ()
    assert intent.summary.fallback_family_count == 1


def test_materialize_archive_font_verifies_stable_member_identity(tmp_path: Path) -> None:
    source = build_test_ttf(tmp_path / "font.ttf", family="Archive Source")
    archive = tmp_path / "Fonts.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(source, "fonts/source.ttf")
    source.unlink()
    face = build_font_catalog([], archives=[archive]).faces[0]
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()

    with SubsetWorkspace("plan", root=workspace_root) as workspace:
        materialized = materialize_font_source(face, workspace, FontConfig())
        assert materialized.is_file()
        assert materialized.parent == workspace.sources
        assert build_font_catalog([materialized]).faces[0].source_digest == face.source_digest

    assert list(workspace_root.iterdir()) == []


def test_codepoint_range_round_trip() -> None:
    ranges = compress_codepoints({1, 2, 3, 9, 11, 12})
    assert ranges == ((1, 3), (9, 9), (11, 12))
    assert expand_codepoint_ranges(ranges) == {1, 2, 3, 9, 11, 12}
