from plexmuxy.config import default_config
from plexmuxy.font import prepare_fonts
from plexmuxy.planner import build_mux_plans
from plexmuxy.scanner import scan_media_dir


def test_build_mux_plan_contains_tracks_attachments_and_cleanup_candidates(tmp_path):
    video = tmp_path / "[VCB-Studio] Example Show [01][Ma10p_1080p].mkv"
    subtitle = tmp_path / "[Kamigami] Example Show [01].chs.ass"
    audio = tmp_path / "Example Show [01].mka"
    fonts = tmp_path / "Fonts"
    font = fonts / "font.ttf"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")
    audio.write_text("", encoding="utf-8")
    fonts.mkdir()
    font.write_text("", encoding="utf-8")

    config = default_config()
    scan = scan_media_dir(tmp_path, config.media)
    font_result = prepare_fonts(tmp_path, config.media, config.font, extract_archives=False)
    plan_result = build_mux_plans(scan, config, font_result)

    assert len(plan_result.plans) == 1
    plan = plan_result.plans[0]
    assert plan.source_video == video
    assert plan.output_path.name == "[VCB-Studio] Example Show [01][Ma10p_1080p]_Plex.mkv"
    assert plan.subtitle_tracks[0].track_name == "chs Kamigami"
    assert plan.subtitle_tracks[0].match_reason == "normalized_title"
    assert plan.audio_tracks[0].path == audio
    assert plan.attachments[0].path == font
    assert set(plan.cleanup_candidates) == {video, subtitle, audio}


def test_planner_skips_already_processed_outputs(tmp_path):
    video = tmp_path / "Example_Plex.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")

    config = default_config()
    scan = scan_media_dir(tmp_path, config.media)
    plan_result = build_mux_plans(scan, config)

    assert plan_result.plans == []
    assert plan_result.skipped_files[0].reason == "already_processed"


def test_unrecognized_subtitle_language_is_reported_and_not_planned(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.unknown.ass"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")

    config = default_config()
    scan = scan_media_dir(tmp_path, config.media)
    plan_result = build_mux_plans(scan, config)

    assert plan_result.plans == []
    assert any(skipped.reason == "unmatched_language" for skipped in plan_result.skipped_files)
    assert any(skipped.reason == "no_mux_inputs" for skipped in plan_result.skipped_files)
