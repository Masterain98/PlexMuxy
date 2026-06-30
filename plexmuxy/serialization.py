from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import (
    AttachmentPlan,
    AudioTrackPlan,
    CleanupResult,
    JobReport,
    MuxPlan,
    MuxResult,
    SkippedFile,
    SubtitleTrackPlan,
)


def path_to_str(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path)


def subtitle_track_to_dict(track: SubtitleTrackPlan) -> dict[str, Any]:
    return {
        "path": path_to_str(track.path),
        "name": track.path.name,
        "track_name": track.track_name,
        "mkv_language": track.mkv_language,
        "ietf_language": track.ietf_language,
        "default_track": track.default_track,
        "forced_track": track.forced_track,
        "match_reason": track.match_reason,
    }


def audio_track_to_dict(track: AudioTrackPlan) -> dict[str, Any]:
    return {
        "path": path_to_str(track.path),
        "name": track.path.name,
        "language": track.language,
        "match_reason": track.match_reason,
    }


def attachment_to_dict(attachment: AttachmentPlan) -> dict[str, Any]:
    return {
        "path": path_to_str(attachment.path),
        "name": attachment.path.name,
    }


def skipped_file_to_dict(skipped: SkippedFile) -> dict[str, Any]:
    return {
        "path": path_to_str(skipped.path),
        "name": skipped.path.name,
        "reason": skipped.reason,
        "stage": skipped.stage,
    }


def mux_plan_to_dict(plan: MuxPlan) -> dict[str, Any]:
    return {
        "source_video": path_to_str(plan.source_video),
        "source_video_name": plan.source_video.name,
        "output_path": path_to_str(plan.output_path),
        "output_name": plan.output_path.name,
        "subtitle_tracks": [subtitle_track_to_dict(track) for track in plan.subtitle_tracks],
        "audio_tracks": [audio_track_to_dict(track) for track in plan.audio_tracks],
        "attachments": [attachment_to_dict(attachment) for attachment in plan.attachments],
        "cleanup_candidates": [
            {"path": path_to_str(path), "name": path.name}
            for path in plan.cleanup_candidates
        ],
        "skipped_files": [skipped_file_to_dict(skipped) for skipped in plan.skipped_files],
    }


def mux_result_to_dict(result: MuxResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "output_path": path_to_str(result.output_path),
        "output_name": result.output_path.name,
        "error": result.error,
        "warnings": [*result.warnings],
        "verified": result.verified,
        "plan": mux_plan_to_dict(result.plan),
    }


def cleanup_result_to_dict(result: CleanupResult) -> dict[str, Any]:
    return {
        "path": path_to_str(result.path),
        "name": result.path.name,
        "action": result.action,
        "success": result.success,
        "destination": path_to_str(result.destination),
        "destination_name": result.destination.name if result.destination is not None else None,
        "error": result.error,
    }


def job_report_to_dict(report: JobReport) -> dict[str, Any]:
    return {
        "input_dir": path_to_str(report.input_dir),
        "plans": [mux_plan_to_dict(plan) for plan in report.plans],
        "results": [mux_result_to_dict(result) for result in report.results],
        "skipped_files": [skipped_file_to_dict(skipped) for skipped in report.skipped_files],
        "cleanup_results": [cleanup_result_to_dict(result) for result in report.cleanup_results],
        "success_count": report.success_count,
        "failure_count": report.failure_count,
    }
