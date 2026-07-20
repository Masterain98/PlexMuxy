"""Tests for the standardized setting compatibility layer."""

from __future__ import annotations

import pytest

from plexmuxy.compatibility import (
    SETTING_COMPATIBILITY,
    Requirement,
    evaluate_compatibility,
    parse_requirement,
    parse_version,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("66", (66,)),
        ("v66", (66,)),
        ("66.0.0", (66, 0, 0)),
        ("  v70.1 ", (70, 1)),
        ("mkvmerge v65.0.0", None),  # not a leading version
        ("", None),
        (None, None),
    ],
)
def test_parse_version(value, expected):
    assert parse_version(value) == expected


@pytest.mark.parametrize(
    "text",
    ["mkvmerge>=66", " mkvmerge >= 66 ", "ffmpeg>=6.0", "mkvmerge==66.0.0"],
)
def test_parse_requirement_accepts_standard_notation(text):
    requirement = parse_requirement(text)
    assert isinstance(requirement, Requirement)
    assert requirement.tool == requirement.tool.casefold()


@pytest.mark.parametrize("text", ["mkvmerge", ">=66", "mkvmerge!=66", "mkvmerge>=abc"])
def test_parse_requirement_rejects_invalid_notation(text):
    with pytest.raises(ValueError):
        parse_requirement(text)


def test_requirement_comparison_operators():
    ge = parse_requirement("mkvmerge>=66")
    assert ge.is_satisfied_by((66,)) is True
    assert ge.is_satisfied_by((66, 0, 0)) is True
    assert ge.is_satisfied_by((70,)) is True
    assert ge.is_satisfied_by((65, 9, 9)) is False

    lt = parse_requirement("mkvmerge<66")
    assert lt.is_satisfied_by((65,)) is True
    assert lt.is_satisfied_by((66,)) is False


def test_unknown_detected_version_is_not_blocked():
    requirement = parse_requirement("mkvmerge>=66")
    assert requirement.is_satisfied_by(None) is True


def test_requirement_describe_is_human_readable():
    assert parse_requirement("mkvmerge>=66").describe() == "mkvmerge \u2265 66"


def test_modern_mime_mode_is_registered():
    assert "font.mime_mode.modern" in SETTING_COMPATIBILITY
    assert SETTING_COMPATIBILITY["font.mime_mode.modern"] == ("mkvmerge>=66",)


def test_evaluate_marks_modern_unavailable_for_old_mkvmerge():
    report = evaluate_compatibility({"mkvmerge": "65.0.0"})
    entry = report["font.mime_mode.modern"]
    assert entry["satisfied"] is False
    assert entry["unmet"] == ["mkvmerge>=66"]
    assert entry["unmet_describe"] == ["mkvmerge \u2265 66"]
    assert entry["requirements"][0]["detected"] == "65.0.0"


def test_evaluate_marks_modern_available_for_new_mkvmerge():
    report = evaluate_compatibility({"mkvmerge": "66.0.0"})
    entry = report["font.mime_mode.modern"]
    assert entry["satisfied"] is True
    assert entry["unmet"] == []


def test_evaluate_gives_benefit_of_the_doubt_when_version_missing():
    report = evaluate_compatibility({"mkvmerge": None})
    entry = report["font.mime_mode.modern"]
    assert entry["satisfied"] is True
    assert entry["requirements"][0]["detected"] is None


def test_evaluate_handles_empty_versions_mapping():
    report = evaluate_compatibility(None)
    assert report["font.mime_mode.modern"]["satisfied"] is True
