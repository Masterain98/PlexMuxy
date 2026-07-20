from pathlib import Path

from plexmuxy.config import default_config
from plexmuxy.models import AttachmentPlan, MuxPlan, MuxResult, PreparedMuxPlan, SubtitleTrackPlan
from plexmuxy.muxer import execute_mux_plan, execute_prepared_mux_plan
from tests.font_test_utils import build_test_ttf


def test_execute_mux_plan_allows_in_place_output(monkeypatch, tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_text("source", encoding="utf-8")
    config = default_config()
    config.task.overwrite = True
    plan = MuxPlan(source_video=video, output_path=video)

    captured = {}

    def fake_runtime(original_plan, runtime_plan, cfg, cancellation_event, preparation_warnings=None, prepared=None):
        # In-place muxing is supported: the muxer writes to a temp file and
        # swaps it into place, so an output path equal to the source must not
        # be refused (even with overwrite enabled).
        captured["runtime_plan"] = runtime_plan
        return MuxResult(plan=runtime_plan, success=True, output_path=runtime_plan.output_path)

    monkeypatch.setattr("plexmuxy.muxer._execute_runtime_plan", fake_runtime)
    result = execute_mux_plan(plan, config)

    assert result.success is True
    assert captured["runtime_plan"].output_path.resolve() == video.resolve()


def test_embed_scheme_emits_self_contained_ass(monkeypatch, tmp_path):
    font = build_test_ttf(tmp_path / "FZYaSong-B-GBK.ttf", family="FZYaSong-B-GBK")
    subtitle = tmp_path / "sub.ass"
    subtitle.write_text(
        "[Script Info]\nTitle: x\n\n[Events]\nFormat: L, T\nDialogue: 0,Hi\n",
        encoding="utf-8",
    )
    output = tmp_path / "movie_Plex.mkv"
    output.write_text("mkv", encoding="utf-8")

    plan = MuxPlan(
        source_video=tmp_path / "movie.mkv",
        output_path=output,
        subtitle_tracks=[SubtitleTrackPlan(path=subtitle, track_name="", mkv_language="eng", ietf_language="en", default_track=False, forced_track=False, match_reason="")],
        attachments=[AttachmentPlan(path=font)],
    )
    config = default_config()
    config.font.embed_scheme = "both"

    captured = {}

    def fake_runtime(original_plan, runtime_plan, cfg, cancellation_event, preparation_warnings=None, prepared=None):
        captured["runtime_attachments"] = list(runtime_plan.attachments)
        return MuxResult(plan=runtime_plan, success=True, output_path=output)

    monkeypatch.setattr("plexmuxy.muxer._execute_runtime_plan", fake_runtime)

    result = execute_mux_plan(plan, config)

    assert result.success is True
    assert len(result.embedded_subtitles) == 1
    embedded = result.embedded_subtitles[0]
    assert embedded.endswith(".embedded.ass")
    assert "[Fonts]" in (tmp_path / embedded).read_text(encoding="utf-8")
    # "both" keeps MKV font attachments.
    assert captured["runtime_attachments"]


def test_embed_scheme_ass_mode_drops_mkv_attachments(monkeypatch, tmp_path):
    font = build_test_ttf(tmp_path / "FZ.ttf", family="FZTest")
    subtitle = tmp_path / "sub.ass"
    subtitle.write_text("[Script Info]\nT: x\n\n[Events]\nFormat: L, T\nDialogue: 0,Hi\n", encoding="utf-8")
    output = tmp_path / "movie_Plex.mkv"
    output.write_text("mkv", encoding="utf-8")
    plan = MuxPlan(
        source_video=tmp_path / "movie.mkv",
        output_path=output,
        subtitle_tracks=[SubtitleTrackPlan(path=subtitle, track_name="", mkv_language="eng", ietf_language="en", default_track=False, forced_track=False, match_reason="")],
        attachments=[AttachmentPlan(path=font)],
    )
    config = default_config()
    config.font.embed_scheme = "ass"

    captured = {}

    def fake_runtime(original_plan, runtime_plan, cfg, cancellation_event, preparation_warnings=None, prepared=None):
        captured["runtime_attachments"] = list(runtime_plan.attachments)
        captured["runtime_subtitles"] = [t.path for t in runtime_plan.subtitle_tracks]
        return MuxResult(plan=runtime_plan, success=True, output_path=output)

    monkeypatch.setattr("plexmuxy.muxer._execute_runtime_plan", fake_runtime)
    result = execute_mux_plan(plan, config)

    assert result.success is True
    assert len(result.embedded_subtitles) == 1
    # "ass" mode must NOT attach fonts to the MKV.
    assert captured["runtime_attachments"] == []
    # "ass" mode must mux the self-contained .ass (with embedded fonts) as the
    # subtitle track, not the original subtitle that has no fonts.
    assert captured["runtime_subtitles"] == [Path(result.embedded_subtitles[0])]


def test_prepared_plan_ass_mode_uses_embedded_subtitle(monkeypatch, tmp_path):
    font = build_test_ttf(tmp_path / "FZ.ttf", family="FZTest")
    subtitle = tmp_path / "sub.ass"
    subtitle.write_text("[Script Info]\nT: x\n\n[Events]\nFormat: L, T\nDialogue: 0,Hi\n", encoding="utf-8")
    output = tmp_path / "movie_Plex.mkv"
    output.write_text("mkv", encoding="utf-8")
    plan = MuxPlan(
        source_video=tmp_path / "movie.mkv",
        output_path=output,
        subtitle_tracks=[SubtitleTrackPlan(path=subtitle, track_name="", mkv_language="eng", ietf_language="en", default_track=False, forced_track=False, match_reason="")],
        attachments=[AttachmentPlan(path=font)],
    )
    prepared = PreparedMuxPlan.from_original(plan)
    config = default_config()
    config.font.embed_scheme = "ass"

    captured = {}

    def fake_runtime(original_plan, runtime_plan, cfg, cancellation_event, preparation_warnings=None, prepared=None):
        captured["runtime_attachments"] = list(runtime_plan.attachments)
        captured["runtime_subtitles"] = [t.path for t in runtime_plan.subtitle_tracks]
        return MuxResult(plan=runtime_plan, success=True, output_path=output)

    monkeypatch.setattr("plexmuxy.muxer._execute_runtime_plan", fake_runtime)
    result = execute_prepared_mux_plan(prepared, config)

    assert result.success is True
    assert len(result.embedded_subtitles) == 1
    assert captured["runtime_attachments"] == []
    assert captured["runtime_subtitles"] == [Path(result.embedded_subtitles[0])]




