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
