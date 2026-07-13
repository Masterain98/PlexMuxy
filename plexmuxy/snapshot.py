from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .config import config_to_dict, parse_config
from .errors import StalePlanError
from .models import PLAN_SCHEMA_VERSION, AppConfig, FileSnapshot, MuxPlan, MuxPlanSnapshot


def calculate_config_hash(config_data: dict) -> str:
    canonical = json.dumps(config_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def calculate_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_plan_snapshot(
    input_dir: Path,
    plans: list[MuxPlan],
    config: AppConfig,
    extra_inputs: list[Path] | None = None,
) -> MuxPlanSnapshot:
    config_data = config_to_dict(config)
    paths: list[Path] = []
    digest_paths: set[Path] = set()

    def include(path: Path, *, digest: bool = False) -> None:
        paths.append(path)
        if digest:
            digest_paths.add(path.resolve())

    for path in extra_inputs or []:
        # extra_inputs currently carries font archives. Their content identity
        # must survive planning even when their future extraction path does not.
        include(path, digest=True)
    for plan in plans:
        include(plan.source_video)
        for subtitle_track in plan.subtitle_tracks:
            include(subtitle_track.path, digest=True)
        for audio_track in plan.audio_tracks:
            include(audio_track.path)
        for attachment in plan.attachments:
            include(attachment.path, digest=True)
        if plan.font_subset_intent is not None:
            for subtitle_path, _ in plan.font_subset_intent.subtitle_digests:
                include(subtitle_path, digest=True)
            for group in plan.font_subset_intent.groups:
                for face in group.faces:
                    include(face.stable_source_path, digest=True)
    files: list[FileSnapshot] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        stat = resolved.stat()
        digest = calculate_file_sha256(resolved) if resolved in digest_paths else None
        files.append(FileSnapshot(resolved, stat.st_size, stat.st_mtime_ns, digest))
    outputs_existing = [plan.output_path.resolve() for plan in plans if plan.output_path.exists()]
    return MuxPlanSnapshot(
        plan_id=str(uuid.uuid4()), config_hash=calculate_config_hash(config_data),
        created_at=MuxPlanSnapshot.timestamp(), input_dir=input_dir.resolve(), config=config_data,
        plans=plans, files=files, outputs_existing=outputs_existing, schema_version=PLAN_SCHEMA_VERSION,
    )


def validate_plan_snapshot(snapshot: MuxPlanSnapshot, config: AppConfig) -> None:
    if snapshot.schema_version not in {1, PLAN_SCHEMA_VERSION}:
        raise StalePlanError(f"Unsupported plan schema_version: {snapshot.schema_version}")
    font_data = snapshot.config.get("font", {})
    font_mode = font_data.get("mode", "all") if isinstance(font_data, dict) else "all"
    if snapshot.schema_version == 1 and font_mode == "subset":
        raise StalePlanError("Plan schema_version 1 cannot execute font.mode=subset; regenerate the plan")
    if calculate_config_hash(snapshot.config) != snapshot.config_hash:
        raise StalePlanError("Saved plan configuration hash is invalid")
    try:
        normalized_saved_config = config_to_dict(parse_config(snapshot.config))
    except Exception as exc:  # ConfigError is intentionally converted to a stale-plan result.
        raise StalePlanError(f"Saved plan configuration is invalid: {exc}") from exc
    if normalized_saved_config != config_to_dict(config):
        raise StalePlanError("Configuration has changed since the plan was created")
    if not snapshot.input_dir.is_dir():
        raise StalePlanError(f"Input directory no longer exists: {snapshot.input_dir}")
    digest_extensions = {
        *config.media.subtitle_extensions,
        *config.media.font_extensions,
        *config.media.font_archive_extensions,
    }
    for file_snapshot in snapshot.files:
        if not file_snapshot.path.is_file():
            raise StalePlanError(f"Planned input no longer exists: {file_snapshot.path}")
        if (
            snapshot.schema_version >= PLAN_SCHEMA_VERSION
            and file_snapshot.path.suffix.casefold() in digest_extensions
            and file_snapshot.sha256 is None
        ):
            raise StalePlanError(f"Planned content-sensitive input has no digest: {file_snapshot.path}")
        stat = file_snapshot.path.stat()
        if stat.st_size != file_snapshot.size or stat.st_mtime_ns != file_snapshot.modified_time_ns:
            raise StalePlanError(f"Planned input changed: {file_snapshot.path}")
        if (
            file_snapshot.sha256 is not None
            and calculate_file_sha256(file_snapshot.path) != file_snapshot.sha256
        ):
            raise StalePlanError(f"Planned input digest changed: {file_snapshot.path}")
    tracked_snapshots = {file_snapshot.path.resolve(): file_snapshot for file_snapshot in snapshot.files}
    tracked = set(tracked_snapshots)
    existed = {path.resolve() for path in snapshot.outputs_existing}
    from .planner import build_output_path

    for plan in snapshot.plans:
        output = plan.output_path.resolve()
        if plan.source_video.resolve() not in tracked:
            raise StalePlanError(f"Untracked source video in plan: {plan.source_video}")
        required_inputs = {
            *[item.path.resolve() for item in plan.subtitle_tracks],
            *[item.path.resolve() for item in plan.audio_tracks],
            *[item.resolve() for item in plan.cleanup_candidates],
        }
        if not required_inputs.issubset(tracked):
            raise StalePlanError("Plan contains an input or cleanup path not captured by the snapshot")
        expected_output = build_output_path(plan.source_video, snapshot.input_dir, config).resolve()
        if output != expected_output:
            raise StalePlanError(f"Plan output does not match the saved configuration: {output}")
        fonts_root = (snapshot.input_dir / "Fonts").resolve()
        for attachment in plan.attachments:
            attachment_path = attachment.path.resolve()
            if attachment_path in tracked:
                attachment_snapshot = tracked_snapshots[attachment_path]
                if snapshot.schema_version >= 2 and attachment_snapshot.sha256 is None:
                    raise StalePlanError(f"Planned attachment has no digest: {attachment.path}")
            elif font_mode == "subset" or fonts_root not in attachment_path.parents:
                raise StalePlanError(f"Untrusted attachment path in plan: {attachment.path}")
        intent = plan.font_subset_intent
        if font_mode == "subset" and intent is None:
            raise StalePlanError("Subset plan is missing font_subset_intent; regenerate the plan")
        if intent is not None:
            subtitle_digests: dict[Path, str] = {}
            for subtitle_path, digest in intent.subtitle_digests:
                resolved_subtitle = subtitle_path.resolve()
                normalized_digest = digest.casefold()
                previous_digest = subtitle_digests.get(resolved_subtitle)
                if previous_digest is not None and previous_digest != normalized_digest:
                    raise StalePlanError(
                        f"Subset intent has conflicting subtitle digests: {resolved_subtitle}"
                    )
                subtitle_digests[resolved_subtitle] = normalized_digest
            planned_subtitles = {track.path.resolve() for track in plan.subtitle_tracks}
            if not planned_subtitles.issubset(subtitle_digests):
                raise StalePlanError("Subset intent does not contain every planned subtitle digest")
            for subtitle_path, intended_digest in subtitle_digests.items():
                subtitle_snapshot = tracked_snapshots.get(subtitle_path)
                if subtitle_snapshot is None or subtitle_snapshot.sha256 is None:
                    raise StalePlanError(f"Subset subtitle is not digest-tracked: {subtitle_path}")
                if subtitle_snapshot.sha256 != intended_digest:
                    raise StalePlanError(f"Subset subtitle digest does not match the snapshot: {subtitle_path}")
            for group in intent.groups:
                for face in group.faces:
                    stable_source = face.stable_source_path.resolve()
                    font_snapshot = tracked_snapshots.get(stable_source)
                    if font_snapshot is None or font_snapshot.sha256 is None:
                        raise StalePlanError(f"Font source is not digest-tracked: {stable_source}")
                    if face.is_archive_backed:
                        if (
                            face.archive_digest is None
                            or font_snapshot.sha256 != face.archive_digest.casefold()
                        ):
                            raise StalePlanError(f"Font archive digest does not match the snapshot: {stable_source}")
                    elif font_snapshot.sha256 != face.source_digest.casefold():
                        raise StalePlanError(f"Direct font digest does not match the snapshot: {stable_source}")
        if output.exists() and output not in existed:
            raise StalePlanError(f"Output appeared after planning: {output}")
        if output == plan.source_video.resolve():
            raise StalePlanError(f"Output path equals source path: {output}")
