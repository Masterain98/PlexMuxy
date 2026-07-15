from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from .models import (
    PLAN_DIGEST_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    AttachmentPlan,
    AudioTrackPlan,
    CleanupResult,
    FileSnapshot,
    FontFaceRef,
    FontOutlineType,
    FontSubsetGroupIntent,
    FontSubsetIntent,
    FontSubsetIssue,
    FontSubsetSummary,
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


def codepoints_to_ranges(codepoints: Iterable[int]) -> list[list[int]]:
    """Return a compact, deterministic JSON representation of codepoints."""
    values = list(codepoints)
    for codepoint in values:
        if isinstance(codepoint, bool) or not isinstance(codepoint, int) or not 0 <= codepoint <= 0x10FFFF:
            raise ValueError(f"Invalid Unicode codepoint: {codepoint!r}")
    normalized = sorted(set(values))
    if not normalized:
        return []
    ranges: list[list[int]] = []
    start = previous = normalized[0]
    for codepoint in normalized[1:]:
        if codepoint == previous + 1:
            previous = codepoint
            continue
        ranges.append([start, previous])
        start = previous = codepoint
    ranges.append([start, previous])
    return ranges


def ranges_to_codepoints(value: Any, field: str) -> tuple[int, ...]:
    ranges = codepoint_ranges_from_json(value, field)
    return tuple(codepoint for start, end in ranges for codepoint in range(start, end + 1))


def codepoint_ranges_to_json(ranges: Iterable[tuple[int, int]]) -> list[list[int]]:
    return [[start, end] for start, end in validate_codepoint_ranges(list(ranges), "codepoint_ranges")]


def codepoint_ranges_from_json(value: Any, field: str) -> tuple[tuple[int, int], ...]:
    raw_ranges = list_value(value, field)
    parsed: list[tuple[int, int]] = []
    for index, item in enumerate(raw_ranges):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{field}[{index}] must be a [start, end] pair")
        start = integer_value(item[0], f"{field}[{index}][0]")
        end = integer_value(item[1], f"{field}[{index}][1]")
        parsed.append((start, end))
    return validate_codepoint_ranges(parsed, field)


def validate_codepoint_ranges(
    ranges: list[tuple[int, int]], field: str
) -> tuple[tuple[int, int], ...]:
    previous_end = -1
    for index, (start, end) in enumerate(ranges):
        if not 0 <= start <= end <= 0x10FFFF:
            raise ValueError(f"{field}[{index}] is outside the Unicode range")
        if start <= previous_end:
            raise ValueError(f"{field} must be sorted and non-overlapping")
        previous_end = end
    return tuple(ranges)


def font_face_to_dict(face: FontFaceRef) -> dict[str, Any]:
    return {
        "source_path": path_to_str(face.source_path),
        "archive_path": path_to_str(face.archive_path),
        "archive_member": face.archive_member,
        "archive_digest": face.archive_digest,
        "face_index": face.face_index,
        "source_digest": face.source_digest,
        "family_names": list(face.family_names),
        "typographic_family_names": list(face.typographic_family_names),
        "subfamily_names": list(face.subfamily_names),
        "full_names": list(face.full_names),
        "postscript_names": list(face.postscript_names),
        "weight": face.weight,
        "width": face.width,
        "italic": face.italic,
        "unicode_ranges": codepoints_to_ranges(face.unicode_codepoints),
        "outline_type": face.outline_type,
        "is_variable": face.is_variable,
        "has_color": face.has_color,
        "has_bitmap": face.has_bitmap,
        "has_vertical_metrics": face.has_vertical_metrics,
        "table_tags": list(face.table_tags),
    }


def font_face_from_dict(data: dict[str, Any]) -> FontFaceRef:
    require_keys(data, {
        "face_index", "source_digest", "family_names", "typographic_family_names",
        "subfamily_names", "full_names", "postscript_names", "weight", "width",
        "italic", "unicode_ranges",
    }, "font face")
    source_path = optional_absolute_path(data.get("source_path"), "font source_path")
    archive_path = optional_absolute_path(data.get("archive_path"), "font archive_path")
    archive_member = optional_nonempty_string(data.get("archive_member"), "font archive_member")
    archive_digest = optional_sha256(data.get("archive_digest"), "font archive_digest")
    outline_type = str(data.get("outline_type", "unknown"))
    if outline_type not in {"truetype", "cff", "cff2", "unknown"}:
        raise ValueError("font outline_type must be truetype, cff, cff2, or unknown")
    return FontFaceRef(
        source_path=source_path,
        archive_path=archive_path,
        archive_member=archive_member,
        archive_digest=archive_digest,
        face_index=integer_value(data["face_index"], "font face_index", minimum=0),
        source_digest=sha256_value(data["source_digest"], "font source_digest"),
        family_names=string_tuple(data["family_names"], "font family_names"),
        typographic_family_names=string_tuple(
            data["typographic_family_names"], "font typographic_family_names"
        ),
        subfamily_names=string_tuple(data["subfamily_names"], "font subfamily_names"),
        full_names=string_tuple(data["full_names"], "font full_names"),
        postscript_names=string_tuple(data["postscript_names"], "font postscript_names"),
        weight=integer_value(data["weight"], "font weight", minimum=1),
        width=integer_value(data["width"], "font width", minimum=1),
        italic=boolean_value(data["italic"], "font italic"),
        unicode_codepoints=ranges_to_codepoints(data["unicode_ranges"], "font unicode_ranges"),
        outline_type=cast(FontOutlineType, outline_type),
        is_variable=boolean_value(data.get("is_variable", False), "font is_variable"),
        has_color=boolean_value(data.get("has_color", False), "font has_color"),
        has_bitmap=boolean_value(data.get("has_bitmap", False), "font has_bitmap"),
        has_vertical_metrics=boolean_value(
            data.get("has_vertical_metrics", False), "font has_vertical_metrics"
        ),
        table_tags=string_tuple(data.get("table_tags", []), "font table_tags"),
    )


def font_subset_issue_to_dict(issue: FontSubsetIssue) -> dict[str, Any]:
    return {
        "code": issue.code,
        "message": issue.message,
        "requested_family": issue.requested_family,
        "subtitle_path": path_to_str(issue.subtitle_path),
        "codepoint_ranges": codepoints_to_ranges(issue.codepoints),
        "fatal": issue.fatal,
    }


def font_subset_issue_from_dict(data: dict[str, Any]) -> FontSubsetIssue:
    require_keys(data, {"code", "message"}, "font subset issue")
    return FontSubsetIssue(
        code=nonempty_string(data["code"], "font subset issue code"),
        message=str(data["message"]),
        requested_family=optional_nonempty_string(
            data.get("requested_family"), "font subset issue requested_family"
        ),
        subtitle_path=optional_absolute_path(
            data.get("subtitle_path"), "font subset issue subtitle_path"
        ),
        codepoints=ranges_to_codepoints(
            data.get("codepoint_ranges", []), "font subset issue codepoint_ranges"
        ),
        fatal=boolean_value(data.get("fatal", True), "font subset issue fatal"),
    )


def font_subset_summary_to_dict(summary: FontSubsetSummary) -> dict[str, int]:
    return {
        "subtitle_count": summary.subtitle_count,
        "requested_family_count": summary.requested_family_count,
        "matched_face_count": summary.matched_face_count,
        "expected_attachment_count": summary.expected_attachment_count,
        "fallback_family_count": summary.fallback_family_count,
    }


def font_subset_summary_from_dict(data: Any) -> FontSubsetSummary:
    if not isinstance(data, dict):
        raise ValueError("font subset summary must be an object")
    return FontSubsetSummary(
        subtitle_count=integer_value(data.get("subtitle_count", 0), "summary subtitle_count", minimum=0),
        requested_family_count=integer_value(
            data.get("requested_family_count", 0), "summary requested_family_count", minimum=0
        ),
        matched_face_count=integer_value(
            data.get("matched_face_count", 0), "summary matched_face_count", minimum=0
        ),
        expected_attachment_count=integer_value(
            data.get("expected_attachment_count", 0), "summary expected_attachment_count", minimum=0
        ),
        fallback_family_count=integer_value(
            data.get("fallback_family_count", 0), "summary fallback_family_count", minimum=0
        ),
    )


def font_subset_group_to_dict(group: FontSubsetGroupIntent) -> dict[str, Any]:
    return {
        "requested_names": list(group.requested_names),
        "alias_family": group.alias_family,
        "faces": [font_face_to_dict(face) for face in group.faces],
        "codepoint_ranges": codepoint_ranges_to_json(group.codepoint_ranges),
    }


def font_subset_group_from_dict(data: dict[str, Any]) -> FontSubsetGroupIntent:
    require_keys(data, {"requested_names", "alias_family", "faces", "codepoint_ranges"}, "font subset group")
    return FontSubsetGroupIntent(
        requested_names=string_tuple(data["requested_names"], "font subset requested_names"),
        alias_family=nonempty_string(data["alias_family"], "font subset alias_family"),
        faces=tuple(
            font_face_from_dict(object_value(item, "font subset face"))
            for item in list_value(data["faces"], "font subset faces")
        ),
        codepoint_ranges=codepoint_ranges_from_json(
            data["codepoint_ranges"], "font subset codepoint_ranges"
        ),
    )


def font_subset_intent_to_dict(intent: FontSubsetIntent) -> dict[str, Any]:
    return {
        "analyzer_version": intent.analyzer_version,
        "subset_profile_version": intent.subset_profile_version,
        "groups": [font_subset_group_to_dict(group) for group in intent.groups],
        "subtitle_digests": [
            {"path": str(path), "sha256": digest} for path, digest in intent.subtitle_digests
        ],
        "issues": [font_subset_issue_to_dict(issue) for issue in intent.issues],
        "summary": font_subset_summary_to_dict(intent.summary),
    }


def font_subset_intent_from_dict(data: dict[str, Any]) -> FontSubsetIntent:
    require_keys(
        data,
        {"analyzer_version", "subset_profile_version", "groups", "subtitle_digests"},
        "font subset intent",
    )
    subtitle_digests: list[tuple[Path, str]] = []
    for index, item in enumerate(list_value(data["subtitle_digests"], "font subset subtitle_digests")):
        item_data = object_value(item, f"font subset subtitle_digests[{index}]")
        require_keys(item_data, {"path", "sha256"}, f"font subset subtitle_digests[{index}]")
        subtitle_digests.append((
            absolute_path(item_data["path"], "font subset subtitle path"),
            sha256_value(item_data["sha256"], "font subset subtitle digest"),
        ))
    return FontSubsetIntent(
        analyzer_version=integer_value(data["analyzer_version"], "font analyzer_version", minimum=1),
        subset_profile_version=integer_value(
            data["subset_profile_version"], "font subset_profile_version", minimum=1
        ),
        groups=tuple(
            font_subset_group_from_dict(object_value(item, "font subset group"))
            for item in list_value(data["groups"], "font subset groups")
        ),
        subtitle_digests=tuple(subtitle_digests),
        issues=tuple(
            font_subset_issue_from_dict(object_value(item, "font subset issue"))
            for item in list_value(data.get("issues", []), "font subset issues")
        ),
        summary=font_subset_summary_from_dict(data.get("summary", {})),
    )


def subtitle_track_to_dict(track: SubtitleTrackPlan) -> dict[str, Any]:
    return {
        "path": str(track.path), "name": track.path.name, "track_name": track.track_name,
        "mkv_language": track.mkv_language, "ietf_language": track.ietf_language,
        "default_track": track.default_track, "forced_track": track.forced_track,
        "match_reason": track.match_reason,
    }


def audio_track_to_dict(track: AudioTrackPlan) -> dict[str, Any]:
    return {
        "path": str(track.path),
        "name": track.path.name,
        "language": track.language,
        "match_reason": track.match_reason,
        "expected_track_count": track.expected_track_count,
    }


def attachment_to_dict(attachment: AttachmentPlan) -> dict[str, Any]:
    return {
        "path": str(attachment.path),
        "name": attachment.name,
        "expected_name": attachment.expected_name,
        "expected_mime_type": attachment.expected_mime_type,
    }


def source_track_to_dict(track: SourceTrackInfo) -> dict[str, Any]:
    return {
        "id": track.id, "type": track.type, "codec": track.codec, "language": track.language,
        "title": track.title, "default_track": track.default_track, "forced_track": track.forced_track,
        "channels": track.channels, "included": track.included, "decision_reason": track.decision_reason,
        "decision_source": track.decision_source, "matched_rule": track.matched_rule,
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
        "font_subset_intent": (
            font_subset_intent_to_dict(plan.font_subset_intent)
            if plan.font_subset_intent is not None else None
        ),
        "edit_revision": plan.edit_revision,
        "external_track_order": list(plan.external_track_order),
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
            absolute_path(item["path"], "audio path"), item.get("language"), str(item["match_reason"]),
            integer_value(item.get("expected_track_count", 1), "audio expected_track_count", minimum=1),
        ) for item in list_value(data.get("audio_tracks", []), "audio_tracks")],
        attachments=[AttachmentPlan(
            absolute_path(item["path"], "attachment path"),
            expected_name=optional_nonempty_string(item.get("expected_name"), "attachment expected_name"),
            expected_mime_type=optional_nonempty_string(
                item.get("expected_mime_type"), "attachment expected_mime_type"
            ),
        ) for item in list_value(data.get("attachments", []), "attachments")],
        source_tracks=[SourceTrackInfo(**item) for item in list_value(data.get("source_tracks", []), "source_tracks")],
        cleanup_candidates=[absolute_path(item["path"] if isinstance(item, dict) else item, "cleanup path") for item in list_value(data.get("cleanup_candidates", []), "cleanup_candidates")],
        skipped_files=[SkippedFile(absolute_path(item["path"], "skipped path"), str(item["reason"]), str(item.get("stage", "matching"))) for item in list_value(data.get("skipped_files", []), "skipped_files")],
        warnings=[str(item) for item in list_value(data.get("warnings", []), "warnings")],
        font_subset_intent=(
            font_subset_intent_from_dict(object_value(data["font_subset_intent"], "font_subset_intent"))
            if data.get("font_subset_intent") is not None else None
        ),
        edit_revision=integer_value(data.get("edit_revision", 0), "plan edit_revision", minimum=0),
        external_track_order=[
            str(item) for item in list_value(data.get("external_track_order", []), "external_track_order")
        ],
    )


def snapshot_to_dict(snapshot: MuxPlanSnapshot) -> dict[str, Any]:
    if snapshot.schema_version not in {1, PLAN_DIGEST_SCHEMA_VERSION, PLAN_SCHEMA_VERSION}:
        raise ValueError(f"Unsupported plan schema_version: {snapshot.schema_version}")
    file_items = []
    for item in snapshot.files:
        payload = {
            "path": str(item.path), "size": item.size, "modified_time_ns": item.modified_time_ns,
        }
        if snapshot.schema_version >= PLAN_DIGEST_SCHEMA_VERSION:
            payload["sha256"] = item.sha256
        file_items.append(payload)
    return {
        "schema_version": snapshot.schema_version,
        "plan_id": snapshot.plan_id,
        "config_hash": snapshot.config_hash,
        "created_at": snapshot.created_at,
        "input_dir": str(snapshot.input_dir),
        "config": snapshot.config,
        "plans": [mux_plan_to_dict(plan) for plan in snapshot.plans],
        "files": file_items,
        "outputs_existing": [str(path) for path in snapshot.outputs_existing],
    }


def snapshot_from_dict(data: dict[str, Any]) -> MuxPlanSnapshot:
    schema_version = data.get("schema_version")
    if isinstance(schema_version, bool) or schema_version not in {
        1,
        PLAN_DIGEST_SCHEMA_VERSION,
        PLAN_SCHEMA_VERSION,
    }:
        raise ValueError("Unsupported plan schema_version")
    require_keys(data, {"plan_id", "config_hash", "created_at", "input_dir", "config", "plans", "files"}, "plan snapshot")
    if not isinstance(data["config"], dict):
        raise ValueError("Plan config must be an object")
    font_data = data["config"].get("font", {})
    font_mode = font_data.get("mode", "all") if isinstance(font_data, dict) else "all"
    if schema_version == 1 and font_mode == "subset":
        raise ValueError("Plan schema_version 1 cannot execute font.mode=subset; regenerate the plan")
    tracks_data = data["config"].get("tracks", {})
    audio_filter_enabled = (
        tracks_data.get("audio_filter_enabled", False) if isinstance(tracks_data, dict) else False
    )
    if schema_version < PLAN_SCHEMA_VERSION and audio_filter_enabled:
        raise ValueError("Plan schema_version 3 is required for source audio filtering; regenerate the plan")
    plans = [mux_plan_from_dict(item) for item in list_value(data["plans"], "plans")]
    if schema_version >= PLAN_DIGEST_SCHEMA_VERSION and font_mode == "subset" and any(
        plan.font_subset_intent is None for plan in plans
    ):
        raise ValueError("Plan schema_version 2+ subset plans require font_subset_intent")
    files: list[FileSnapshot] = []
    for index, item in enumerate(list_value(data["files"], "files")):
        file_data = object_value(item, f"files[{index}]")
        require_keys(file_data, {"path", "size", "modified_time_ns"}, f"files[{index}]")
        digest = None
        if schema_version >= PLAN_DIGEST_SCHEMA_VERSION:
            if "sha256" not in file_data:
                raise ValueError(f"files[{index}] missing fields: sha256")
            digest = optional_sha256(file_data["sha256"], f"files[{index}].sha256")
        files.append(FileSnapshot(
            absolute_path(file_data["path"], "file snapshot path"),
            integer_value(file_data["size"], "file snapshot size", minimum=0),
            integer_value(file_data["modified_time_ns"], "file snapshot modified_time_ns", minimum=0),
            digest,
        ))
    return MuxPlanSnapshot(
        plan_id=str(data["plan_id"]), config_hash=str(data["config_hash"]), created_at=str(data["created_at"]),
        input_dir=absolute_path(data["input_dir"], "input_dir"), config=data["config"],
        plans=plans,
        files=files,
        outputs_existing=[absolute_path(item, "existing output") for item in list_value(data.get("outputs_existing", []), "outputs_existing")],
        schema_version=schema_version,
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
        "available_subtitles": [
            {"path": str(path), "name": path.name} for path in report.available_subtitles
        ],
        "available_audio": [{"path": str(path), "name": path.name} for path in report.available_audio],
        "post_actions": list(report.post_actions),
    }


def absolute_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field} must be absolute")
    return path


def optional_absolute_path(value: Any, field: str) -> Path | None:
    if value is None:
        return None
    return absolute_path(value, field)


def object_value(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def string_tuple(value: Any, field: str) -> tuple[str, ...]:
    items = list_value(value, field)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{field} must be a list of strings")
    return tuple(items)


def nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def optional_nonempty_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return nonempty_string(value, field)


def boolean_value(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def integer_value(value: Any, field: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def sha256_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field} must be a SHA-256 hex digest") from exc
    return value.casefold()


def optional_sha256(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return sha256_value(value, field)


def list_value(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def require_keys(data: dict[str, Any], keys: set[str], field: str) -> None:
    missing = keys - set(data)
    if missing:
        raise ValueError(f"{field} missing fields: {', '.join(sorted(missing))}")
