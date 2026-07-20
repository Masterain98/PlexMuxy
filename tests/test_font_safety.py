import zipfile

import pytest
from fontTools.ttLib import TTCollection, TTFont

from plexmuxy.config import default_config
from plexmuxy.font import extract_zip, prepare_fonts, validate_members
from plexmuxy.font_usage import extract_referenced_font_names, select_referenced_fonts
from plexmuxy.models import ArchiveLimits
from tests.font_test_utils import build_test_ttf


def test_extract_referenced_font_names_reads_styles_and_overrides(tmp_path):
    subtitle = tmp_path / "test.ass"
    subtitle.write_text(
        "[V4+ Styles]\nStyle: Default, Noto Sans CJK SC,20,x\n[Events]\nDialogue: 0,0,0,Default,,0,0,0,,{\\fnArial}Text",
        encoding="utf-8",
    )
    assert extract_referenced_font_names(subtitle) == {"noto sans cjk sc", "arial"}


def test_select_referenced_fonts_falls_back_to_file_stem_for_invalid_font(tmp_path):
    subtitle = tmp_path / "test.ass"
    subtitle.write_text("Style: Default, Demo Font,20,x", encoding="utf-8")
    font = tmp_path / "Demo Font.ttf"
    font.write_bytes(b"not a real font")
    selected, missing = select_referenced_fonts([subtitle], [font])
    assert selected == [font]
    assert missing == set()


def test_select_referenced_fonts_reads_every_collection_face(tmp_path):
    first = build_test_ttf(tmp_path / "first.ttf", family="First Family")
    second = build_test_ttf(tmp_path / "second.ttf", family="Second Family")
    collection_path = tmp_path / "collection.ttc"
    collection = TTCollection()
    collection.fonts = [TTFont(first), TTFont(second)]
    try:
        collection.save(collection_path)
    finally:
        collection.close()
    subtitle = tmp_path / "test.ass"
    subtitle.write_text("Style: Default, Second Family,20,x", encoding="utf-8")

    selected, missing = select_referenced_fonts([subtitle], [collection_path])

    assert selected == [collection_path]
    assert missing == set()


def test_archive_limits_reject_count_size_and_depth():
    limits = ArchiveLimits(max_files=1, max_total_size=3, max_file_size=2, max_depth=1)
    with pytest.raises(ValueError, match="too many"):
        validate_members([("a", 1), ("b", 1)], limits)
    with pytest.raises(ValueError, match="maximum depth"):
        validate_members([("a/b", 1)], limits)
    with pytest.raises(ValueError, match="maximum size"):
        validate_members([("a", 3)], limits)


def test_zip_duplicate_is_deduplicated_and_conflict_is_renamed(tmp_path):
    destination = tmp_path / "Fonts"
    destination.mkdir()
    (destination / "font.ttf").write_bytes(b"same")
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("font.ttf", b"same")
    assert extract_zip(duplicate, destination) == []

    conflict = tmp_path / "conflict.zip"
    with zipfile.ZipFile(conflict, "w") as archive:
        archive.writestr("font.ttf", b"different")
    assert extract_zip(conflict, destination) == [destination / "font (1).ttf"]


def test_prepare_fonts_extracts_zip_and_reports_fonts(tmp_path):
    with zipfile.ZipFile(tmp_path / "Fonts.zip", "w") as archive:
        archive.writestr("nested/font.ttf", b"font")
    config = default_config()
    result = prepare_fonts(tmp_path, config.media, config.font)
    assert result.errors == []
    assert result.fonts == [tmp_path / "Fonts" / "nested" / "font.ttf"]
