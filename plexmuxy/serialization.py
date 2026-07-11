from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import (
    AttachmentPlan,
    AudioTrackPlan,
    CleanupResult,
    FileSnapshot,
    JobReport,
    MuxPlan,
    MuxPlanSnapshot,
    MuxResult,
    SkippedFile,
    SourceTrackInfo,
    SubtitleTrackPlan,
)


def path_to_str(path: Path | None) -> str | None:
    return None if path is None else str(path)


def subtitle_track_to_dict(track: SubtitleTrackPlan) -> dict[str, Any]:
    return {
        "path": str(track.path), "name": track.path.name, "track_name": track.track_name,
        "mkv_language": track.mkv_language, "ietf_language": track.ietf_language,
        "default_track": track.default_track, "forced_track": track.forced_track,
        "match_reason": track.match_reason,
    }


def audio_track_to_dict(track: AudioTrackPlan) -> dict[str, Any]:
    return {"path": str(track.path), "name": track.path.name, "language": track.language, "match_reason": track.match_reason}


def attachment_to_dict(attachment: AttachmentPlan) -> dict[str, Any]:
    return {"path": str(attachment.path), "name": attachment.path.name}


def source_track_to_dict(track: SourceTrackInfo) -> dict[str, Any]:
    return {
        "id": track.id, "type": track.type, "codec": track.codec, "language": track.language,
        "title": track.title, "default_track": track.default_track, "forced_track": track.forced_track,
        "channels": track.channels, "included": track.included, "decision_reason": track.decision_reason,
    }


def skipped_file_to_dict(skipped: SkippedFile) -> dict[str, Any]:
    return {"path": str(skipped.path), "name": skipped.path.name, "reason": skipped.reason, "stage": skipped.stage}


def mux_plan_to_dict(plan: MuxPlan) -> dict[str, Any]:
    return {
        "source_video": str(plan.source_video), "source_video_name": plan.source_video.name,
        "output_path": str(plan.output_path), "output_name": plan.output_path.name,
        "subtitle_tracks": [subtitle_track_to_dict(item) for item in plan.subtitle_tracks],
        "audio_tracks": [audio_track_to_dict(item) for item in plan.audio_tracks],
        "attachments": [attachment_to_dict(item) for item in plan.attachments],
        "source_tracks": [source_track_to_dict(item) for item in plan.source_tracks],
        "cleanup_candidates": [{"path": str(path), "name": path.name} for path in plan.cleanup_candidates],
        "skipped_files": [skipped_file_to_dict(item) for item in plan.skipped_files],
        "warnings": list(plan.warnings),
    }


def mux_plan_from_dict(data: dict[str, Any]) -> MuxPlan:
    require_keys(data, {"source_video", "output_path"}, "mux plan")
    return MuxPlan(
        source_video=absolute_path(data["source_video"], "source_video"),
        output_path=absolute_path(data["output_path"], "output_path"),
        subtitle_tracks=[SubtitleTrackPlan(
            path=absolute_path(item["path"], "subtitle path"), track_name=str(item["track_name"]),
            mkv_language=str(item["mkv_language"]), ietf_language=str(item["ietf_language"]),
            default_track=bool(item["default_track"]), forced_track=bool(item["forced_track"]),
            match_reason=str(item["match_reason"]),
        ) for item in list_value(data.get("subtitle_tracks", []), "subtitle_tracks")],
        audio_tracks=[AudioTrackPlan(
            absolute_path(item["path"], "audio path"), item.get("language"), str(item["match_reason"])
        ) for item in list_value(data.get("audio_tracks", []), "audio_tracks")],
        attachments=[AttachmentPlan(absolute_path(item["path"], "attachment path")) for item in list_value(data.get("attachments", []), "attachments")],
        source_tracks=[SourceTrackInfo(**item) for item in list_value(data.get("source_tracks", []), "source_tracks")],
        cleanup_candidates=[absolute_path(item["path"] if isinstance(item, dict) else item, "cleanup path") for item in list_value(data.get("cleanup_candidates", []), "cleanup_candidates")],
        skipped_files=[SkippedFile(absolute_path(item["path"], "skipped path"), str(item["reason"]), str(item.get("stage", "matching"))) for item in list_value(data.get("skipped_files", []), "skipped_files")],
        warnings=[str(item) for item in list_value(data.get("warnings", []), "warnings")],
    )


def snapshot_to_dict(snapshot: MuxPlanSnapshot) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plan_id": snapshot.plan_id,
        "config_hash": snapshot.config_hash,
        "created_at": snapshot.created_at,
        "input_dir": str(snapshot.input_dir),
        "config": snapshot.config,
        "plans": [mux_plan_to_dict(plan) for plan in snapshot.plans],
        "files": [
            {"path": str(item.path), "size": item.size, "modified_time_ns": item.modified_time_ns}
            for item in snapshot.files
        ],
        "outputs_existing": [str(path) for path in snapshot.outputs_existing],
    }


def snapshot_from_dict(data: dict[str, Any]) -> MuxPlanSnapshot:
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported plan schema_version")
    require_keys(data, {"plan_id", "config_hash", "created_at", "input_dir", "config", "plans", "files"}, "plan snapshot")
    if not isinstance(data["config"], dict):
        raise ValueError("Plan config must be an object")
    return MuxPlanSnapshot(
        plan_id=str(data["plan_id"]), config_hash=str(data["config_hash"]), created_at=str(data["created_at"]),
        input_dir=absolute_path(data["input_dir"], "input_dir"), config=data["config"],
        plans=[mux_plan_from_dict(item) for item in list_value(data["plans"], "plans")],
        files=[FileSnapshot(absolute_path(item["path"], "file snapshot path"), int(item["size"]), int(item["modified_time_ns"])) for item in list_value(data["files"], "files")],
        outputs_existing=[absolute_path(item, "existing output") for item in list_value(data.get("outputs_existing", []), "outputs_existing")],
    )


def mux_result_to_dict(result: MuxResult) -> dict[str, Any]:
    return {
        "success": result.success, "output_path": str(result.output_path), "output_name": result.output_path.name,
        "error_code": result.error_code, "error": result.error, "warnings": list(result.warnings),
        "verified": result.verified,
        "verification": None if result.verification is None else {
            "success": result.verification.success, "error_code": result.verification.error_code,
            "error": result.verification.error, "details": result.verification.details,
        },
        "plan": mux_plan_to_dict(result.plan),
    }


def cleanup_result_to_dict(result: CleanupResult) -> dict[str, Any]:
    return {
        "path": str(result.path), "name": result.path.name, "action": result.action,
        "success": result.success, "destination": path_to_str(result.destination),
        "destination_name": result.destination.name if result.destination else None, "error": result.error,
    }


def job_report_to_dict(report: JobReport) -> dict[str, Any]:
    return {
        "input_dir": str(report.input_dir), "plans": [mux_plan_to_dict(item) for item in report.plans],
        "results": [mux_result_to_dict(item) for item in report.results],
        "skipped_files": [skipped_file_to_dict(item) for item in report.skipped_files],
        "cleanup_results": [cleanup_result_to_dict(item) for item in report.cleanup_results],
        "success_count": report.success_count, "failure_count": report.failure_count,
        "snapshot": snapshot_to_dict(report.snapshot) if report.snapshot else None,
        "warnings": list(report.warnings), "cancelled": report.cancelled,
        "error_code": report.error_code, "error": report.error,
    }


def absolute_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field} must be absolute")
    return path


def list_value(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def require_keys(data: dict[str, Any], keys: set[str], field: str) -> None:
    missing = keys - set(data)
    if missing:
        raise ValueError(f"{field} missing fields: {', '.join(sorted(missing))}")
