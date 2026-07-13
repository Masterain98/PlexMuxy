from pathlib import Path

from plexmuxy.config import default_config
from plexmuxy.font import prepare_fonts
from plexmuxy.font_catalog import build_font_catalog
from plexmuxy.planner import build_mux_plans
from plexmuxy.scanner import scan_media_dir
from plexmuxy.service import build_job_plan
from tests.font_test_utils import build_test_ttf

ASS_SAMPLE = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic
Style: Default,Subset Family,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0
Style: Emphasis,Subset Family,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,-1

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,Hello {\\b1}A{\\b0} world
Dialogue: 0,0:00:01.00,0:00:02.00,Emphasis,{\\fnSubset Family}中
"""


def make_subset_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    fonts = tmp_path / "Fonts"
    fonts.mkdir()
    font = build_test_ttf(
        fonts / "subset-family.ttf",
        family="Subset Family",
        characters=" HeloAwrd中\u00a0",
    )
    video.write_bytes(b"video")
    subtitle.write_text(ASS_SAMPLE, encoding="utf-8")
    return video, subtitle, font


def test_subset_mode_builds_real_intent_without_placeholder_warning(tmp_path: Path) -> None:
    _video, _subtitle, _font = make_subset_tree(tmp_path)
    config = default_config()
    config.font.mode = "subset"
    scan = scan_media_dir(tmp_path, config.media)
    fonts = prepare_fonts(tmp_path, config.media, config.font, extract_archives=False)
    catalog = build_font_catalog(fonts.fonts)

    result = build_mux_plans(scan, config, fonts, catalog)

    assert len(result.plans) == 1
    plan = result.plans[0]
    assert plan.attachments == []
    assert plan.font_subset_intent is not None
    assert plan.font_subset_intent.issues == ()
    assert plan.font_subset_intent.summary.subtitle_count == 1
    assert plan.font_subset_intent.summary.requested_family_count == 1
    assert plan.font_subset_intent.summary.matched_face_count == 1
    assert "font_subset_unavailable_fell_back_to_referenced_fonts" not in plan.warnings


def test_subset_job_snapshot_tracks_subtitle_and_font_digests(tmp_path: Path) -> None:
    _video, subtitle, font = make_subset_tree(tmp_path)
    config = default_config()
    config.font.mode = "subset"

    report = build_job_plan(tmp_path, config)

    assert report.error is None
    assert report.snapshot is not None and report.snapshot.schema_version == 2
    assert report.plans[0].font_subset_intent is not None
    snapshots = {item.path: item for item in report.snapshot.files}
    assert snapshots[subtitle.resolve()].sha256
    assert snapshots[font.resolve()].sha256


def test_subset_mode_blocks_unsafe_unclosed_override(tmp_path: Path) -> None:
    _video, subtitle, _font = make_subset_tree(tmp_path)
    subtitle.write_text(ASS_SAMPLE.replace("{\\b1}A{\\b0}", "{\\b1 A"), encoding="utf-8")
    config = default_config()
    config.font.mode = "subset"
    scan = scan_media_dir(tmp_path, config.media)
    fonts = prepare_fonts(tmp_path, config.media, config.font, extract_archives=False)

    result = build_mux_plans(scan, config, fonts, build_font_catalog(fonts.fonts))

    assert result.plans == []
    assert any(item.reason == "unsafe_ass_for_subset" for item in result.skipped_files)
