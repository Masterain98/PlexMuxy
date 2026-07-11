from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .config import config_to_dict
from .errors import StalePlanError
from .models import AppConfig, FileSnapshot, MuxPlan, MuxPlanSnapshot


def calculate_config_hash(config_data: dict) -> str:
    canonical = json.dumps(config_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_plan_snapshot(
    input_dir: Path,
    plans: list[MuxPlan],
    config: AppConfig,
    extra_inputs: list[Path] | None = None,
) -> MuxPlanSnapshot:
    config_data = config_to_dict(config)
    paths: list[Path] = list(extra_inputs or [])
    for plan in plans:
        paths.extend([plan.source_video, *[item.path for item in plan.subtitle_tracks],
                      *[item.path for item in plan.audio_tracks], *[item.path for item in plan.attachments]])
    files: list[FileSnapshot] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        stat = resolved.stat()
        files.append(FileSnapshot(resolved, stat.st_size, stat.st_mtime_ns))
    outputs_existing = [plan.output_path.resolve() for plan in plans if plan.output_path.exists()]
    return MuxPlanSnapshot(
        plan_id=str(uuid.uuid4()), config_hash=calculate_config_hash(config_data),
        created_at=MuxPlanSnapshot.timestamp(), input_dir=input_dir.resolve(), config=config_data,
        plans=plans, files=files, outputs_existing=outputs_existing,
    )


def validate_plan_snapshot(snapshot: MuxPlanSnapshot, config: AppConfig) -> None:
    if calculate_config_hash(config_to_dict(config)) != snapshot.config_hash:
        raise StalePlanError("Configuration has changed since the plan was created")
    if not snapshot.input_dir.is_dir():
        raise StalePlanError(f"Input directory no longer exists: {snapshot.input_dir}")
    for item in snapshot.files:
        if not item.path.is_file():
            raise StalePlanError(f"Planned input no longer exists: {item.path}")
        stat = item.path.stat()
        if stat.st_size != item.size or stat.st_mtime_ns != item.modified_time_ns:
            raise StalePlanError(f"Planned input changed: {item.path}")
    tracked = {item.path.resolve() for item in snapshot.files}
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
            if attachment_path not in tracked and fonts_root not in attachment_path.parents:
                raise StalePlanError(f"Untrusted attachment path in plan: {attachment.path}")
        if output.exists() and output not in existed:
            raise StalePlanError(f"Output appeared after planning: {output}")
        if output == plan.source_video.resolve():
            raise StalePlanError(f"Output path equals source path: {output}")
