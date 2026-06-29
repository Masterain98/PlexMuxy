import sys
import types
import zipfile

import pytest

from plexmuxy.config import default_config
from plexmuxy.font import extract_7z, prepare_fonts


def test_prepare_fonts_preview_archives_reports_future_font_paths_without_extracting(tmp_path):
    archive = tmp_path / "Fonts.zip"
    with zipfile.ZipFile(archive, "w") as this_zip:
        this_zip.writestr("font.ttf", "font")

    config = default_config()
    result = prepare_fonts(
        tmp_path,
        config.media,
        config.font,
        extract_archives=False,
        preview_archives=True,
    )

    assert result.fonts == [tmp_path / "Fonts" / "font.ttf"]
    assert not (tmp_path / "Fonts").exists()


def test_extract_7z_rejects_unsafe_member_before_extracting(tmp_path, monkeypatch):
    extracted = False

    class FakeSevenZipFile:
        def __init__(self, archive, mode):
            self.archive = archive
            self.mode = mode

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def getnames(self):
            return ["../evil.ttf"]

        def extractall(self, destination, targets=None):
            nonlocal extracted
            extracted = True

    fake_py7zr = types.SimpleNamespace(SevenZipFile=FakeSevenZipFile)
    monkeypatch.setitem(sys.modules, "py7zr", fake_py7zr)

    with pytest.raises(ValueError, match="escapes destination"):
        extract_7z(tmp_path / "Fonts.7z", tmp_path / "Fonts")

    assert extracted is False


def test_prepare_fonts_reports_fonts_path_that_is_not_directory(tmp_path):
    (tmp_path / "Fonts").write_text("not a directory", encoding="utf-8")
    config = default_config()

    result = prepare_fonts(tmp_path, config.media, config.font)

    assert result.fonts == []
    assert result.errors == [f"Fonts path exists but is not a directory: {tmp_path / 'Fonts'}"]


def test_prepare_fonts_rar_preview_reports_unsupported_error(tmp_path):
    (tmp_path / "Fonts.rar").write_text("rar", encoding="utf-8")
    config = default_config()
    config.font.unrar_path = "unrar"

    result = prepare_fonts(
        tmp_path,
        config.media,
        config.font,
        extract_archives=False,
        preview_archives=True,
    )

    assert result.fonts == []
    assert result.errors == ["Fonts.rar: RAR archive preview is not supported; run without dry-run to extract it"]


def test_extract_7z_uses_extract_with_validated_targets(tmp_path, monkeypatch):
    calls = []

    class FakeSevenZipFile:
        def __init__(self, archive, mode):
            self.archive = archive
            self.mode = mode

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def getnames(self):
            return ["font.ttf"]

        def extract(self, path=None, targets=None):
            calls.append((path, targets))

        def extractall(self, *args, **kwargs):
            raise AssertionError("extractall should not be called")

    fake_py7zr = types.SimpleNamespace(SevenZipFile=FakeSevenZipFile)
    monkeypatch.setitem(sys.modules, "py7zr", fake_py7zr)

    extracted = extract_7z(tmp_path / "Fonts.7z", tmp_path / "Fonts")

    assert extracted == [tmp_path / "Fonts" / "font.ttf"]
    assert calls == [(tmp_path / "Fonts", ["font.ttf"])]
