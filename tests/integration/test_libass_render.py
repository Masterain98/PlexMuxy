from __future__ import annotations

import subprocess

import pytest

from plexmuxy.font_catalog import build_font_catalog
from plexmuxy.font_subset import subset_font_face
from tests.font_test_utils import build_test_ttf

pytestmark = pytest.mark.integration
SCRIPT_SAMPLE = "简繁日本한글العربيةदेवनागरीไทย😀★"


@pytest.mark.parametrize(
    ("style", "weight", "italic", "ass_bold", "ass_italic"),
    [("Regular", 400, False, 0, 0), ("Bold Italic", 700, True, -1, -1)],
)
def test_libass_renders_subset_identically_to_source(
    ffmpeg_tool,
    tmp_path,
    style,
    weight,
    italic,
    ass_bold,
    ass_italic,
):
    ffmpeg = ffmpeg_tool
    source_dir = tmp_path / "source-fonts"
    subset_dir = tmp_path / "subset-fonts"
    source_dir.mkdir()
    subset_dir.mkdir()
    source = build_test_ttf(
        source_dir / "source.ttf",
        family="PlexMuxy Render Source",
        style=style,
        weight=weight,
        italic=italic,
        characters=f" A{SCRIPT_SAMPLE}",
    )
    face = build_font_catalog([source]).faces[0]
    requested = {ord(character) for character in f" A{SCRIPT_SAMPLE}"}
    subset_font_face(face, source, requested, "PMX_RENDER", subset_dir / "subset.ttf")

    original_ass = tmp_path / "original.ass"
    subset_ass = tmp_path / "subset.ass"
    # The subset preserves the ORIGINAL name table (see font_subset.subset_font_face), and the
    # subtitle references that same name -- exactly how a player matches a full embedded font.
    original_ass.write_text(_ass("PlexMuxy Render Source", ass_bold, ass_italic), encoding="utf-8")
    subset_ass.write_text(_ass("PlexMuxy Render Source", ass_bold, ass_italic), encoding="utf-8")
    original = _render(ffmpeg, tmp_path, "original.ass", "source-fonts")
    subset = _render(ffmpeg, tmp_path, "subset.ass", "subset-fonts")

    black_frame = bytes((0, 0, 0, 255)) * (320 * 180)
    assert original != black_frame
    assert subset == original


def _render(ffmpeg: str, cwd, subtitle: str, fonts_dir: str) -> bytes:
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1:r=1",
            "-vf", f"subtitles={subtitle}:fontsdir={fonts_dir}",
            "-frames:v", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "-",
        ],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        pytest.fail(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def _ass(family: str, bold: int, italic: int) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,{bold},{italic},0,0,100,100,0,0,1,0,0,5,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.90,Default,,0,0,0,,{{\fn{family}\frz10\t(0,800,\frz25)}}A{SCRIPT_SAMPLE}{{\rDefault}}
"""
