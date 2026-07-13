from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fontTools.ttLib import TTCollection, TTFont

from plexmuxy.font_catalog import build_font_catalog
from plexmuxy.font_subset import FontSubsetError, subset_font_face
from tests.font_test_utils import build_test_ttf


def test_subset_font_keeps_requested_characters_and_rewrites_all_family_names(tmp_path: Path) -> None:
    source = build_test_ttf(tmp_path / "source.ttf", family="Original Family", characters=" AB中")
    face = build_font_catalog([source]).faces[0]
    font = TTFont(source)
    font["name"].setName("原始字体", 1, 3, 1, 0x0804)
    font.save(source)
    font.close()
    face = build_font_catalog([source]).faces[0]
    output = tmp_path / "PMX_TEST-Regular.ttf"

    result = subset_font_face(face, source, {ord(" "), ord("A"), ord("中")}, "PMX_TEST", output)

    assert result.path == output
    subset = TTFont(output)
    try:
        assert set(subset.getBestCmap()) == {ord(" "), ord("A"), ord("中")}
        families = {record.toUnicode() for record in subset["name"].names if record.nameID in {1, 16, 21}}
        assert families == {"PMX_TEST"}
        assert subset["OS/2"].usWeightClass == 400
    finally:
        subset.close()


def test_subset_output_is_deterministic(tmp_path: Path) -> None:
    source = build_test_ttf(tmp_path / "source.ttf", family="Stable Font", characters=" ABC")
    face = build_font_catalog([source]).faces[0]
    first = subset_font_face(face, source, {32, 65, 66}, "PMX_STABLE", tmp_path / "one.ttf")
    second = subset_font_face(face, source, {32, 65, 66}, "PMX_STABLE", tmp_path / "two.ttf")

    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()


def test_subset_rejects_missing_character_and_unsafe_color_face(tmp_path: Path) -> None:
    source = build_test_ttf(tmp_path / "source.ttf", family="Limited", characters=" A")
    face = build_font_catalog([source]).faces[0]

    with pytest.raises(FontSubsetError, match="missing requested"):
        subset_font_face(face, source, {ord("中")}, "PMX_LIMITED", tmp_path / "missing.ttf")
    with pytest.raises(FontSubsetError, match="Color and bitmap"):
        subset_font_face(replace(face, has_color=True), source, {ord("A")}, "PMX_LIMITED", tmp_path / "color.ttf")


def test_collection_face_is_saved_as_an_independent_font(tmp_path: Path) -> None:
    regular = build_test_ttf(tmp_path / "regular.ttf", family="Collection", style="Regular")
    bold = build_test_ttf(tmp_path / "bold.ttf", family="Collection", style="Bold", weight=700)
    fonts = [TTFont(regular), TTFont(bold)]
    collection_path = tmp_path / "faces.ttc"
    try:
        collection = TTCollection()
        collection.fonts = fonts
        collection.save(collection_path)
    finally:
        for font in fonts:
            font.close()
    face = next(item for item in build_font_catalog([collection_path]).faces if item.face_index == 1)

    result = subset_font_face(face, collection_path, {ord(" "), ord("A")}, "PMX_COLLECTION", tmp_path / "bold.ttf")

    assert result.path.suffix == ".ttf"
    output = TTFont(result.path)
    try:
        assert output["OS/2"].usWeightClass == 700
    finally:
        output.close()
