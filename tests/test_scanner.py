import pytest

from plexmuxy.config import default_config
from plexmuxy.scanner import scan_media_dir


def test_scan_media_dir_classifies_files_case_insensitively(tmp_path):
    (tmp_path / "Video.MP4").write_text("", encoding="utf-8")
    (tmp_path / "Audio.MKA").write_text("", encoding="utf-8")
    (tmp_path / "Subtitle.SSA").write_text("", encoding="utf-8")
    (tmp_path / "Fonts.zip").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / "Fonts").mkdir()

    scan = scan_media_dir(tmp_path, default_config().media)

    assert [path.name for path in scan.videos] == ["Video.MP4"]
    assert [path.name for path in scan.audios] == ["Audio.MKA"]
    assert [path.name for path in scan.subtitles] == ["Subtitle.SSA"]
    assert [path.name for path in scan.font_archives] == ["Fonts.zip"]
    assert [path.name for path in scan.others] == ["notes.txt"]
    assert scan.fonts_dir == tmp_path / "Fonts"


def test_scan_media_dir_recurses_when_enabled(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "NestedVideo.mkv").write_text("", encoding="utf-8")
    (nested / "NestedAudio.mka").write_text("", encoding="utf-8")
    (nested / "NestedSubtitle.ass").write_text("", encoding="utf-8")
    (nested / "NestedFonts.zip").write_text("", encoding="utf-8")
    (nested / "nested-notes.txt").write_text("", encoding="utf-8")

    media = default_config().media
    media.recursive = True
    scan = scan_media_dir(tmp_path, media)

    assert [path.name for path in scan.videos] == ["NestedVideo.mkv"]
    assert [path.name for path in scan.audios] == ["NestedAudio.mka"]
    assert [path.name for path in scan.subtitles] == ["NestedSubtitle.ass"]
    assert [path.name for path in scan.font_archives] == ["NestedFonts.zip"]
    assert [path.name for path in scan.others] == ["nested-notes.txt"]


def test_scan_media_dir_raises_for_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_media_dir(tmp_path / "missing", default_config().media)


def test_scan_media_dir_raises_for_file_path(tmp_path):
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        scan_media_dir(file_path, default_config().media)
