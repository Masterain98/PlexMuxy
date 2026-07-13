from __future__ import annotations

from pathlib import Path

from plexmuxy.font_catalog import build_font_catalog, normalize_font_name
from plexmuxy.font_matching import match_font_usage
from plexmuxy.models import FontUsage
from tests.font_test_utils import build_test_ttf


def usage(family: str, *, weight: int = 400, italic: bool = False, text: str = "A") -> FontUsage:
    return FontUsage(family, normalize_font_name(family), weight, italic, tuple(sorted(map(ord, text))), (Path("subtitle.ass"),))


def test_matcher_uses_internal_family_and_style_metadata(tmp_path: Path) -> None:
    regular = build_test_ttf(tmp_path / "not-the-family.ttf", family="Actual Family", style="Regular")
    bold = build_test_ttf(tmp_path / "also-not-family.ttf", family="Actual Family", style="Bold", weight=700)
    catalog = build_font_catalog([regular, bold]).faces

    result = match_font_usage(usage("Actual Family", weight=700), catalog)

    assert result.matched
    assert result.face is not None and result.face.weight == 700


def test_matcher_reports_semantic_ambiguity_instead_of_digest_tiebreak(tmp_path: Path) -> None:
    first = build_test_ttf(tmp_path / "one.ttf", family="Duplicate Family", characters=" A")
    second = build_test_ttf(tmp_path / "two.ttf", family="Duplicate Family", characters=" AB")
    catalog = build_font_catalog([first, second]).faces

    result = match_font_usage(usage("Duplicate Family"), catalog)

    assert result.status == "ambiguous"
    assert len(result.candidates) == 2


def test_matcher_deduplicates_identical_font_payloads(tmp_path: Path) -> None:
    first = build_test_ttf(tmp_path / "one.ttf", family="Copied Family")
    second = tmp_path / "two.ttf"
    second.write_bytes(first.read_bytes())
    catalog = build_font_catalog([first, second]).faces

    result = match_font_usage(usage("Copied Family"), catalog)

    assert result.matched


def test_matcher_reports_missing_codepoints(tmp_path: Path) -> None:
    font = build_test_ttf(tmp_path / "limited.ttf", family="Limited", characters=" A")
    catalog = build_font_catalog([font]).faces

    result = match_font_usage(usage("Limited", text="A中"), catalog)

    assert result.status == "missing-glyphs"
    assert result.missing_codepoints == (ord("中"),)
