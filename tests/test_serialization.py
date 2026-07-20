import json

import pytest

from plexmuxy.config import default_config
from plexmuxy.models import (
    AttachmentPlan,
    AudioTrackPlan,
    CleanupResult,
    FontFaceRef,
    FontSubsetGroupIntent,
    FontSubsetIntent,
    FontSubsetIssue,
    FontSubsetSummary,
    JobReport,
    MuxPlan,
    MuxResult,
    SkippedFile,
    SubtitleTrackPlan,
)
from plexmuxy.serialization import (
    job_report_to_dict,
    mux_plan_from_dict,
    mux_plan_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)
from plexmuxy.snapshot import create_plan_snapshot


def test_mux_plan_serialization_is_json_compatible(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    audio = tmp_path / "Example.mka"
    font = tmp_path / "Fonts" / "font.ttf"
    plan = MuxPlan(
        source_video=video,
        output_path=output,
        subtitle_tracks=[
            SubtitleTrackPlan(
                path=subtitle,
                track_name="chs",
                mkv_language="chi",
                ietf_language="zh-Hans",
                default_track=True,
                forced_track=False,
                match_reason="normalized_title",
            )
        ],
        audio_tracks=[AudioTrackPlan(path=audio, language=None, match_reason="normalized_title")],
        attachments=[AttachmentPlan(
            path=font,
            expected_name="PMX_TEST-Regular.ttf",
            expected_mime_type="application/x-truetype-font",
        )],
        cleanup_candidates=[video, subtitle, audio],
        skipped_files=[SkippedFile(path=tmp_path / "unrelated.ass", reason="unmatched", stage="matching")],
    )

    data = mux_plan_to_dict(plan)

    json.dumps(data)
    assert data["source_video"] == str(video)
    assert data["source_video_name"] == "Example.mkv"
    assert data["subtitle_tracks"][0]["path"] == str(subtitle)
    assert data["attachments"][0]["expected_name"] == "PMX_TEST-Regular.ttf"
    assert data["skipped_files"][0]["reason"] == "unmatched"

    restored = mux_plan_from_dict(json.loads(json.dumps(data)))
    assert restored.attachments[0].name == "PMX_TEST-Regular.ttf"
    assert restored.attachments[0].expected_mime_type == "application/x-truetype-font"


def test_job_report_serialization_includes_results_and_cleanup(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    plan = MuxPlan(source_video=video, output_path=output, cleanup_candidates=[video])
    report = JobReport(
        input_dir=tmp_path,
        plans=[plan],
        results=[MuxResult(plan=plan, success=True, output_path=output, verified=True)],
        skipped_files=[SkippedFile(path=tmp_path / "other.ass", reason="unmatched")],
        cleanup_results=[
            CleanupResult(
                path=video,
                action="move",
                success=True,
                destination=tmp_path / "Extra" / "Example.mkv",
            )
        ],
    )

    data = job_report_to_dict(report)

    json.dumps(data)
    assert data["success_count"] == 1
    assert data["failure_count"] == 0
    assert data["results"][0]["verified"] is True
    assert data["cleanup_results"][0]["destination"] == str(tmp_path / "Extra" / "Example.mkv")


def test_font_subset_intent_round_trip_compresses_unicode_ranges(tmp_path):
    subtitle = tmp_path / "Example.chs.ass"
    font = tmp_path / "Fonts" / "Demo.ttf"
    face = FontFaceRef(
        source_path=font,
        face_index=0,
        source_digest="a" * 64,
        family_names=("Demo",),
        typographic_family_names=("Demo Sans",),
        subfamily_names=("Regular",),
        full_names=("Demo Regular",),
        postscript_names=("Demo-Regular",),
        weight=400,
        width=5,
        italic=False,
        unicode_codepoints=(0x20, 0x21, 0x22, 0x4E00),
        outline_type="truetype",
        has_vertical_metrics=True,
        table_tags=("cmap", "glyf", "name"),
    )
    intent = FontSubsetIntent(
        analyzer_version=1,
        subset_profile_version=1,
        groups=(FontSubsetGroupIntent(
            requested_names=("Demo",),
            alias_family="PMX_123456789ABC",
            faces=(face,),
            codepoint_ranges=((0x20, 0x22), (0x4E00, 0x4E00)),
        ),),
        subtitle_digests=((subtitle, "b" * 64),),
        issues=(FontSubsetIssue(
            code="subset_warning",
            message="warning",
            requested_family="Demo",
            subtitle_path=subtitle,
            codepoints=(0x20, 0x21),
            fatal=False,
        ),),
        summary=FontSubsetSummary(
            subtitle_count=1,
            requested_family_count=1,
            matched_face_count=1,
            expected_attachment_count=1,
        ),
    )
    plan = MuxPlan(tmp_path / "Example.mkv", tmp_path / "Example_Plex.mkv", font_subset_intent=intent)

    data = mux_plan_to_dict(plan)
    serialized_face = data["font_subset_intent"]["groups"][0]["faces"][0]
    assert serialized_face["unicode_ranges"] == [[0x20, 0x22], [0x4E00, 0x4E00]]

    restored = mux_plan_from_dict(json.loads(json.dumps(data)))
    assert restored.font_subset_intent == intent


def test_schema1_is_compatible_only_outside_subset_mode(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)
    data = snapshot_to_dict(snapshot)
    data["schema_version"] = 1
    for item in data["files"]:
        item.pop("sha256")

    restored = snapshot_from_dict(json.loads(json.dumps(data)))
    assert restored.schema_version == 1
    assert restored.files[0].sha256 is None

    data["config"]["font"]["mode"] = "subset"
    with pytest.raises(ValueError, match="schema_version 1"):
        snapshot_from_dict(data)


def test_schema2_subset_requires_intent_and_valid_ranges(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    config.font.mode = "subset"
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)
    data = snapshot_to_dict(snapshot)

    with pytest.raises(ValueError, match="font_subset_intent"):
        snapshot_from_dict(data)
