import json

from plexmuxy.models import (
    AttachmentPlan,
    AudioTrackPlan,
    CleanupResult,
    JobReport,
    MuxPlan,
    MuxResult,
    SkippedFile,
    SubtitleTrackPlan,
)
from plexmuxy.serialization import job_report_to_dict, mux_plan_to_dict


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
        attachments=[AttachmentPlan(path=font)],
        cleanup_candidates=[video, subtitle, audio],
        skipped_files=[SkippedFile(path=tmp_path / "unrelated.ass", reason="unmatched", stage="matching")],
    )

    data = mux_plan_to_dict(plan)

    json.dumps(data)
    assert data["source_video"] == str(video)
    assert data["source_video_name"] == "Example.mkv"
    assert data["subtitle_tracks"][0]["path"] == str(subtitle)
    assert data["skipped_files"][0]["reason"] == "unmatched"


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
