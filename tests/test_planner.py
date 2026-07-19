from pathlib import Path

from plexmuxy.config import default_config
from plexmuxy.font import prepare_fonts
from plexmuxy.models import FontFaceRef, FontSubsetGroupIntent, FontSubsetIntent
from plexmuxy.planner import build_mux_plans, build_output_path
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
    assert plan.subtitle_tracks[0].default_track is True
    assert plan.subtitle_tracks[0].forced_track is False
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


def test_already_processed_check_only_applies_to_suffix_strategy(tmp_path):
    video = tmp_path / "Movie_PlexCut.mkv"
    subtitle = tmp_path / "Movie_PlexCut.chs.ass"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")

    config = default_config()
    scan = scan_media_dir(tmp_path, config.media)
    plan_result = build_mux_plans(scan, config)

    assert len(plan_result.plans) == 1
    assert all(skipped.reason != "already_processed" for skipped in plan_result.skipped_files)


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


def test_same_name_mkv_without_output_dir_is_rejected(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")

    config = default_config()
    config.task.name_strategy = "same-name"
    scan = scan_media_dir(tmp_path, config.media)
    plan_result = build_mux_plans(scan, config)

    assert plan_result.plans == []
    assert any(skipped.reason == "invalid_output_path_same_as_input" for skipped in plan_result.skipped_files)


def test_same_name_strategy_uses_source_stem_in_output_dir(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")

    config = default_config()
    config.task.name_strategy = "same-name"
    config.task.output_dir = tmp_path / "PlexReady"
    scan = scan_media_dir(tmp_path, config.media)
    plan_result = build_mux_plans(scan, config)

    assert len(plan_result.plans) == 1
    assert plan_result.plans[0].output_path == tmp_path / "PlexReady" / "Example.mkv"


def test_template_name_strategy_uses_name_template(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    video.write_text("", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")

    config = default_config()
    config.task.name_strategy = "template"
    config.task.name_template = "{stem}.plex"
    scan = scan_media_dir(tmp_path, config.media)
    plan_result = build_mux_plans(scan, config)

    assert plan_result.plans[0].output_path.name == "Example.plex.mkv"


def test_output_dir_relative_and_absolute_paths(tmp_path):
    config = default_config()
    video = tmp_path / "Example.mp4"

    config.task.output_dir = tmp_path / "absolute_out"
    assert build_output_path(video, tmp_path, config).parent == tmp_path / "absolute_out"

    config.task.output_dir = Path("relative_out")
    assert build_output_path(video, tmp_path, config).parent == tmp_path / "relative_out"


def test_existing_output_is_skipped_without_overwrite(tmp_path):
    (tmp_path / "Example.mkv").write_text("source", encoding="utf-8")
    (tmp_path / "Example.chs.ass").write_text("subtitle", encoding="utf-8")
    (tmp_path / "Example_Plex.mkv").write_text("existing", encoding="utf-8")
    config = default_config()
    scan = scan_media_dir(tmp_path, config.media)
    result = build_mux_plans(scan, config)
    assert not result.plans
    assert any(item.reason == "output_exists" for item in result.skipped_files)


def _make_face(source_path: Path, family: str, face_index: int = 0) -> FontFaceRef:
    return FontFaceRef(
        source_path=source_path,
        face_index=face_index,
        source_digest="d" * 64,
        family_names=(family,),
        typographic_family_names=(),
        subfamily_names=("Regular",),
        full_names=(f"{family} Regular",),
        postscript_names=(family.replace(" ", ""),),
        weight=400,
        width=100,
        italic=False,
        unicode_codepoints=(0x41, 0x42),
    )


def test_subset_preview_fonts_deduplicates_source_paths(tmp_path):
    from plexmuxy.planner import _subset_preview_fonts

    yahei = tmp_path / "msyh.ttc"
    simhei = tmp_path / "simhei.ttf"
    # Two faces from the SAME font file plus one from a different file.
    group_a = FontSubsetGroupIntent(
        requested_names=("Microsoft YaHei",),
        alias_family="PMX_AAAAAAAA",
        faces=(_make_face(yahei, "Microsoft YaHei", 0), _make_face(yahei, "Microsoft YaHei", 1)),
        codepoint_ranges=((0x41, 0x42),),
    )
    group_b = FontSubsetGroupIntent(
        requested_names=("SimHei",),
        alias_family="PMX_BBBBBBBB",
        faces=(_make_face(simhei, "SimHei"),),
        codepoint_ranges=((0x42, 0x43),),
    )
    intent = FontSubsetIntent(
        analyzer_version=1,
        subset_profile_version=1,
        groups=(group_a, group_b),
        subtitle_digests=(),
    )

    fonts = _subset_preview_fonts(intent)
    # The two YaHei faces share one source file, so only two distinct paths.
    assert len(fonts) == 2
    assert yahei.resolve() in {p.resolve() for p in fonts}
    assert simhei.resolve() in {p.resolve() for p in fonts}
