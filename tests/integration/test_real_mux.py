import json
import subprocess

import pytest

from plexmuxy.config import default_config
from plexmuxy.service import run_mux_job

from .conftest import run_checked

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("extension", ["mkv", "mp4", "avi", "flv"])
@pytest.mark.parametrize("subtitle_extension", ["ass", "ssa"])
def test_real_formats_mux_and_validate(media_tools, tmp_path, extension, subtitle_extension):
    ffmpeg, mkvmerge = media_tools
    video = tmp_path / f"Sample.{extension}"
    codec = "flv1" if extension == "flv" else "mpeg4"
    run_checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1", "-c:v", codec, "-y", str(video)])
    run_checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "flac", "-y", str(tmp_path / "Sample.mka")])
    (tmp_path / f"Sample.chs.{subtitle_extension}").write_text(
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H0,&H0,&H0,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,测试\n",
        encoding="utf-8",
    )
    config = default_config()
    config.task.cleanup = "none"
    config.mkvmerge.path = mkvmerge
    report = run_mux_job(tmp_path, config)
    assert report.failure_count == 0
    assert report.success_count == 1
    data = json.loads(subprocess.run([mkvmerge, "-J", str(report.results[0].output_path)], capture_output=True, text=True, check=True).stdout)
    assert any(track["type"] == "video" for track in data["tracks"])
    assert any(track["type"] == "subtitles" for track in data["tracks"])
    assert any(track["type"] == "audio" for track in data["tracks"])


@pytest.mark.parametrize("archive_type", ["zip", "7z"])
def test_real_font_archives_become_attachments(media_tools, tmp_path, archive_type):
    import zipfile

    import py7zr

    ffmpeg, mkvmerge = media_tools
    video = tmp_path / "Archive.mkv"
    run_checked([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1", "-c:v", "mpeg4", "-y", str(video)])
    (tmp_path / "Archive.chs.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,font,20\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,test\n",
        encoding="utf-8",
    )
    source_font = tmp_path / "font.ttf"
    source_font.write_bytes(b"test font attachment")
    archive = tmp_path / f"Fonts.{archive_type}"
    if archive_type == "zip":
        with zipfile.ZipFile(archive, "w") as output:
            output.write(source_font, "font.ttf")
    else:
        with py7zr.SevenZipFile(archive, "w") as output:
            output.write(source_font, "font.ttf")
    source_font.unlink()
    config = default_config()
    config.task.cleanup = "none"
    config.mkvmerge.path = mkvmerge
    report = run_mux_job(tmp_path, config)
    assert report.success_count == 1
    details = report.results[0].verification.details
    assert details["attachments"] == 1
