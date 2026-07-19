from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from plexmuxy.ass_analysis import analyze_ass_file
from plexmuxy.config import default_config
from plexmuxy.font_catalog import build_font_catalog
from plexmuxy.font_prepare import (
    ANALYZER_VERSION,
    FontPreparationError,
    SubsetWorkspace,
    build_subset_intent,
    prepare_subset_plan,
)
from plexmuxy.font_subset import SUBSET_PROFILE_VERSION, FontSubsetError
from plexmuxy.models import (
    FontSubsetIntent,
    FontUsage,
    MuxPlan,
    MuxResult,
    PreparedMuxPlan,
    SubtitleTrackPlan,
)
from plexmuxy.service import execute_plan_snapshot
from plexmuxy.snapshot import create_plan_snapshot
from tests.font_test_utils import build_test_ttf


def _subset_plan(tmp_path: Path) -> tuple[MuxPlan, Path]:
    font = build_test_ttf(
        tmp_path / "source.ttf",
        family="Subset Family",
        characters=" AB\u00a0",
    )
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text(
        "\n".join((
            "[V4+ Styles]",
            "Format: Name, Fontname, Bold, Italic",
            "Style: Default,Subset Family,0,0",
            "[Events]",
            "Format: Style, Text",
            "Dialogue: Default,AB",
            "",
        )),
        encoding="utf-8",
    )
    analysis = analyze_ass_file(subtitle)
    usages = [
        FontUsage(
            item.requested_family,
            item.normalized_family,
            item.weight,
            item.italic,
            item.codepoints,
            item.subtitle_paths,
        )
        for item in analysis.usages
    ]
    intent = build_subset_intent([subtitle], usages, build_font_catalog([font]).faces)
    track = SubtitleTrackPlan(subtitle, "Chinese", "chi", "zh-Hans", True, False, "exact")
    plan = MuxPlan(
        tmp_path / "episode.mkv",
        tmp_path / "episode_Plex.mkv",
        subtitle_tracks=[track],
        font_subset_intent=intent,
    )
    return plan, font


def test_prepare_subset_plan_keeps_original_names_and_creates_valid_attachment(tmp_path: Path) -> None:
    plan, font = _subset_plan(tmp_path)
    original_subtitle = plan.subtitle_tracks[0].path.read_bytes()
    original_font = font.read_bytes()
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()

    with SubsetWorkspace("plan", root=workspace_root) as workspace:
        prepared = prepare_subset_plan(plan, default_config().font, workspace)
        assert prepared.original_plan is plan
        # The subtitle is NOT rewritten: it keeps referencing the original family name, and the
        # subset font keeps that same name, so players match it like a full embedded font.
        assert prepared.subtitle_tracks[0].path == plan.subtitle_tracks[0].path
        subtitle_text = plan.subtitle_tracks[0].path.read_text(encoding="utf-8")
        assert "Subset Family" in subtitle_text
        alias = plan.font_subset_intent.groups[0].alias_family  # type: ignore[union-attr]
        assert alias not in subtitle_text
        assert len(prepared.attachments) == 1
        assert prepared.attachments[0].expected_mime_type == "application/x-truetype-font"
        subset = TTFont(prepared.attachments[0].path)
        try:
            assert {ord("A"), ord("B")}.issubset(subset.getBestCmap())
            # The subset preserves the ORIGINAL family name (not the opaque alias).
            families = {r.toUnicode() for r in subset["name"].names if int(r.nameID) in (1, 16, 21)}
            assert families == {"Subset Family"}
        finally:
            subset.close()

    assert plan.subtitle_tracks[0].path.read_bytes() == original_subtitle
    assert font.read_bytes() == original_font
    assert list(workspace_root.iterdir()) == []


def test_subset_failure_falls_back_to_full_family_without_rewriting(monkeypatch, tmp_path: Path) -> None:
    plan, font = _subset_plan(tmp_path)
    config = default_config().font
    config.subset_failure_action = "fallback-full"
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()

    def reject_subset(*_args, **_kwargs):
        raise FontSubsetError("unsupported test font")

    monkeypatch.setattr("plexmuxy.font_prepare.subset_font_face", reject_subset)
    with SubsetWorkspace("plan", root=workspace_root) as workspace:
        prepared = prepare_subset_plan(plan, config, workspace)
        assert prepared.subtitle_tracks == plan.subtitle_tracks
        assert prepared.attachments[0].path == font.resolve()
        assert prepared.attachments[0].name == font.name
        assert prepared.subset_warnings[0].startswith("subset_fallback_full_font:")


def test_subset_failure_skip_video_is_explicit(monkeypatch, tmp_path: Path) -> None:
    plan, _font = _subset_plan(tmp_path)
    config = default_config().font
    config.subset_failure_action = "skip-video"
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    monkeypatch.setattr(
        "plexmuxy.font_prepare.subset_font_face",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FontSubsetError("boom")),
    )

    with SubsetWorkspace("plan", root=workspace_root) as workspace:
        with pytest.raises(FontPreparationError, match="Cannot subset"):
            prepare_subset_plan(plan, config, workspace)


def test_service_finishes_all_preparation_before_any_mux(monkeypatch, tmp_path: Path) -> None:
    config = default_config()
    config.task.cleanup = "none"
    config.font.mode = "subset"
    plans: list[MuxPlan] = []
    for name in ("One", "Two"):
        video = tmp_path / f"{name}.mkv"
        video.write_bytes(b"video")
        plans.append(MuxPlan(
            video,
            tmp_path / f"{name}_Plex.mkv",
            font_subset_intent=FontSubsetIntent(
                ANALYZER_VERSION,
                SUBSET_PROFILE_VERSION,
                (),
                (),
            ),
        ))
    snapshot = create_plan_snapshot(tmp_path, plans, config)
    prepared_sources: list[str] = []
    mux_sources: list[str] = []
    monkeypatch.setattr(
        "plexmuxy.service.prepare_fonts",
        lambda *_args, **_kwargs: __import__("plexmuxy.models", fromlist=["FontResult"]).FontResult(),
    )

    def prepare(plan, *_args, **_kwargs):
        prepared_sources.append(plan.source_video.name)
        return PreparedMuxPlan.from_original(plan)

    def mux(plan, *_args, **_kwargs):
        assert len(prepared_sources) == len(plans)
        mux_sources.append(plan.source_video.name)
        return MuxResult(plan, True, plan.output_path, verified=True)

    monkeypatch.setattr("plexmuxy.service.prepare_subset_plan", prepare)
    monkeypatch.setattr("plexmuxy.service.execute_mux_plan", mux)

    report = execute_plan_snapshot(snapshot, config)

    assert prepared_sources == ["One.mkv", "Two.mkv"]
    assert mux_sources == ["One.mkv", "Two.mkv"]
    assert report.success_count == 2


def test_fail_job_preparation_error_starts_no_mux(monkeypatch, tmp_path: Path) -> None:
    config = default_config()
    config.task.cleanup = "none"
    config.font.mode = "subset"
    config.font.subset_failure_action = "fail-job"
    video = tmp_path / "One.mkv"
    video.write_bytes(b"video")
    plan = MuxPlan(
        video,
        tmp_path / "One_Plex.mkv",
        font_subset_intent=FontSubsetIntent(ANALYZER_VERSION, SUBSET_PROFILE_VERSION, (), ()),
    )
    snapshot = create_plan_snapshot(tmp_path, [plan], config)
    monkeypatch.setattr(
        "plexmuxy.service.prepare_fonts",
        lambda *_args, **_kwargs: __import__("plexmuxy.models", fromlist=["FontResult"]).FontResult(),
    )
    monkeypatch.setattr(
        "plexmuxy.service.prepare_subset_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FontPreparationError("bad subset")),
    )
    monkeypatch.setattr(
        "plexmuxy.service.execute_mux_plan",
        lambda *_args, **_kwargs: pytest.fail("mux must not start"),
    )

    report = execute_plan_snapshot(snapshot, config)

    assert report.error_code == "FONT_SUBSET_FAILED"
    assert report.results == []
