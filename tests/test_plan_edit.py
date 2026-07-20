from __future__ import annotations

from pathlib import Path

import pytest

from plexmuxy.config import default_config
from plexmuxy.font_catalog import FontCatalogResult
from plexmuxy.models import (
    AudioTrackPlan,
    FontResult,
    MuxPlan,
    PlanEdit,
    ScanResult,
    SubtitleOverride,
    SubtitleTrackPlan,
)
from plexmuxy.plan_edit import PlanEditError, apply_plan_edits


def subtitle(path: Path, name: str = "Original") -> SubtitleTrackPlan:
    return SubtitleTrackPlan(path, name, "chi", "zh-Hans", True, False, "exact")


def fixture_plan(tmp_path: Path):
    video_a = tmp_path / "Show.S01E01.mkv"
    video_b = tmp_path / "Show.S01E02.mkv"
    sub_a = tmp_path / "Show.S01E01.chs.ass"
    sub_b = tmp_path / "Show.S01E02.chs.ass"
    audio_a = tmp_path / "Show.S01E01.mka"
    for path in (video_a, video_b, sub_a, sub_b, audio_a):
        path.write_bytes(b"fixture")
    plans = [
        MuxPlan(
            video_a,
            tmp_path / "Show.S01E01_Plex.mkv",
            subtitle_tracks=[subtitle(sub_a)],
            audio_tracks=[AudioTrackPlan(audio_a, None, "exact")],
            cleanup_candidates=[video_a, sub_a, audio_a],
        ),
        MuxPlan(
            video_b,
            tmp_path / "Show.S01E02_Plex.mkv",
            subtitle_tracks=[subtitle(sub_b)],
            cleanup_candidates=[video_b, sub_b],
        ),
    ]
    scan = ScanResult(
        input_dir=tmp_path,
        videos=[video_a, video_b],
        audios=[audio_a],
        subtitles=[sub_a, sub_b],
    )
    return plans, scan, video_a, video_b, sub_a, sub_b, audio_a


def test_edit_excludes_inputs_updates_metadata_order_and_cleanup(tmp_path):
    plans, scan, video_a, _, sub_a, _, audio_a = fixture_plan(tmp_path)
    token_audio = f"audio:{audio_a.resolve()}"
    token_subtitle = f"subtitle:{sub_a.resolve()}"
    edit = PlanEdit(
        source_video=video_a,
        revision=2,
        included_subtitles=(sub_a,),
        included_external_audio=(audio_a,),
        subtitle_metadata_overrides=(SubtitleOverride(
            sub_a,
            track_name="Chinese edited",
            mkv_language="chi",
            ietf_language="zh-Hans",
            default_track=False,
            forced_track=True,
        ),),
        external_track_order=(token_audio, token_subtitle),
    )

    edited, skipped = apply_plan_edits(
        plans,
        {video_a: edit},
        scan,
        default_config(),
        FontResult(),
        FontCatalogResult(),
    )

    first = edited[0]
    assert skipped == []
    assert first.edit_revision == 2
    assert first.subtitle_tracks[0].track_name == "Chinese edited"
    assert first.subtitle_tracks[0].default_track is False
    assert first.subtitle_tracks[0].forced_track is True
    assert first.external_track_order == [token_audio, token_subtitle]
    assert set(first.cleanup_candidates) == {video_a, sub_a.resolve(), audio_a.resolve()}


def test_edit_can_disable_video_and_reassign_known_subtitle(tmp_path):
    plans, scan, video_a, video_b, sub_a, sub_b, _ = fixture_plan(tmp_path)
    edits = {
        video_a: PlanEdit(video_a, enabled=False),
        video_b: PlanEdit(video_b, included_subtitles=(sub_a, sub_b)),
    }

    edited, skipped = apply_plan_edits(
        plans, edits, scan, default_config(), FontResult(), FontCatalogResult()
    )

    assert [plan.source_video for plan in edited] == [video_b]
    assert [track.path for track in edited[0].subtitle_tracks] == [sub_a.resolve(), sub_b.resolve()]
    assert edited[0].subtitle_tracks[0].match_reason == "manual_assignment"
    assert skipped[0].reason == "disabled_by_user"


def test_edit_rejects_unknown_paths_duplicate_assignment_and_inconsistent_order(tmp_path):
    plans, scan, video_a, video_b, sub_a, _, _ = fixture_plan(tmp_path)
    outside = tmp_path.parent / "outside.ass"

    with pytest.raises(PlanEditError, match="unknown subtitle"):
        apply_plan_edits(
            plans,
            {video_a: PlanEdit(video_a, included_subtitles=(outside,))},
            scan,
            default_config(),
            FontResult(),
            FontCatalogResult(),
        )

    with pytest.raises(PlanEditError, match="multiple videos"):
        apply_plan_edits(
            plans,
            {
                video_a: PlanEdit(video_a, included_subtitles=(sub_a,)),
                video_b: PlanEdit(video_b, included_subtitles=(sub_a,)),
            },
            scan,
            default_config(),
            FontResult(),
            FontCatalogResult(),
        )

    with pytest.raises(PlanEditError, match="external_track_order"):
        apply_plan_edits(
            plans,
            {video_a: PlanEdit(video_a, external_track_order=("subtitle:wrong",))},
            scan,
            default_config(),
            FontResult(),
            FontCatalogResult(),
        )


def test_subtitle_selection_recomputes_subset_intent(monkeypatch, tmp_path):
    plans, scan, video_a, _, _, _, _ = fixture_plan(tmp_path)
    config = default_config()
    config.font.mode = "subset"
    observed = []

    def fake_subset(subtitles, *args, **kwargs):
        observed.append(list(subtitles))
        return [], "new-intent", ["recomputed"], None

    monkeypatch.setattr("plexmuxy.plan_edit.plan_font_subsets", fake_subset)

    edited, _ = apply_plan_edits(
        plans,
        {video_a: PlanEdit(video_a, included_subtitles=())},
        scan,
        config,
        FontResult(),
        FontCatalogResult(),
    )

    assert observed[0] == []
    assert edited[0].font_subset_intent == "new-intent"
    assert edited[0].warnings == ["recomputed"]
