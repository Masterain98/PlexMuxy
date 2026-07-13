from __future__ import annotations

import zipfile
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from plexmuxy.font_catalog import build_font_catalog, normalize_font_name
from plexmuxy.models import FontConfig, MediaConfig
from tests.font_test_utils import build_test_ttf


def test_catalog_reads_names_style_and_codepoints(tmp_path: Path) -> None:
    path = build_test_ttf(tmp_path / "unexpected-file-name.ttf", family="内部字体", style="Bold Italic", weight=700, italic=True)

    result = build_font_catalog([path])

    assert result.errors == []
    assert len(result.faces) == 1
    face = result.faces[0]
    assert "内部字体" in face.family_names
    assert face.weight == 700
    assert face.italic is True
    assert {ord("A"), ord("中")}.issubset(face.unicode_codepoints)
    assert face.outline_type == "truetype"


def test_catalog_enumerates_every_collection_face(tmp_path: Path) -> None:
    regular = build_test_ttf(tmp_path / "regular.ttf", family="Collection Face", style="Regular")
    bold = build_test_ttf(tmp_path / "bold.ttf", family="Collection Face", style="Bold", weight=700)
    fonts = [TTFont(regular), TTFont(bold)]
    collection_path = tmp_path / "faces.ttc"
    try:
        collection = TTCollection()
        collection.fonts = fonts
        collection.save(collection_path)
    finally:
        for font in fonts:
            font.close()

    result = build_font_catalog([collection_path])

    assert [face.face_index for face in result.faces] == [0, 1]
    assert [face.weight for face in result.faces] == [400, 700]


def test_catalog_reads_archive_members_without_extracting_to_input(tmp_path: Path) -> None:
    font = build_test_ttf(tmp_path / "font.ttf", family="Archive Font")
    archive = tmp_path / "Fonts.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(font, "nested/archive-font.ttf")
    font.unlink()

    result = build_font_catalog([], archives=[archive], media_config=MediaConfig(), font_config=FontConfig())

    assert result.errors == []
    assert len(result.faces) == 1
    face = result.faces[0]
    assert face.source_path is None
    assert face.archive_path == archive.resolve()
    assert face.archive_member == "nested/archive-font.ttf"
    assert face.archive_digest
    assert not (tmp_path / "nested").exists()


def test_normalize_font_name_handles_vertical_and_unicode_forms() -> None:
    assert normalize_font_name(" @Ｆｏｎｔ  Name ") == "font name"
