from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .models import AppConfig, MuxPlan, MuxResult


def execute_mux_plan(plan: MuxPlan, config: AppConfig) -> MuxResult:
    if plan.output_path.resolve() == plan.source_video.resolve():
        return MuxResult(
            plan=plan,
            success=False,
            output_path=plan.output_path,
            error="Output path is the same as the source video; refusing in-place mux.",
        )

    if plan.output_path.exists() and not config.task.overwrite:
        return MuxResult(
            plan=plan,
            success=False,
            output_path=plan.output_path,
            error=f"Output file already exists: {plan.output_path}",
        )

    mkvmerge_path = resolve_mkvmerge_path(config)
    if mkvmerge_path is None:
        return MuxResult(
            plan=plan,
            success=False,
            output_path=plan.output_path,
            error="mkvmerge was not found. Set mkvmerge.path in config or add mkvmerge to PATH.",
        )

    try:
        from pymkv import MKVFile, MKVTrack
    except ImportError as exc:
        return MuxResult(
            plan=plan,
            success=False,
            output_path=plan.output_path,
            error=f"pymkv is not installed: {exc}",
        )

    started_at = datetime.now().timestamp()
    try:
        plan.output_path.parent.mkdir(parents=True, exist_ok=True)
        mux_file = MKVFile(str(plan.source_video), mkvmerge_path=mkvmerge_path)

        for track in plan.subtitle_tracks:
            mux_file.add_track(
                MKVTrack(
                    str(track.path),
                    track_name=track.track_name,
                    default_track=track.default_track,
                    forced_track=track.forced_track,
                    language=track.mkv_language,
                    language_ietf=track.ietf_language,
                    mkvmerge_path=mkvmerge_path,
                )
            )
        for track in plan.audio_tracks:
            mux_file.add_track(str(track.path))
        for attachment in plan.attachments:
            mux_file.add_attachment(str(attachment.path))

        mux_file.mux(str(plan.output_path), silent=True, ignore_warning=True)
    except Exception as exc:  # noqa: BLE001 - pymkv surfaces subprocess and parsing errors directly.
        return MuxResult(plan=plan, success=False, output_path=plan.output_path, error=str(exc))

    verification_error = verify_output(plan.output_path, started_at)
    if verification_error is not None:
        return MuxResult(
            plan=plan,
            success=False,
            output_path=plan.output_path,
            error=verification_error,
            verified=False,
        )
    return MuxResult(plan=plan, success=True, output_path=plan.output_path, verified=True)


def resolve_mkvmerge_path(config: AppConfig) -> str | None:
    configured = config.mkvmerge.path.strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return str(configured_path)
        found_configured = shutil.which(configured)
        if found_configured:
            return found_configured
        return None
    found = shutil.which("mkvmerge")
    if found:
        return found
    for local_name in ("mkvmerge.exe", "mkvmerge"):
        local_path = Path.cwd() / local_name
        if local_path.exists():
            return str(local_path)
    return None


def verify_output(output_path: Path, started_at: float | None = None) -> str | None:
    if not output_path.exists():
        return f"Output file was not created: {output_path}"
    if output_path.stat().st_size <= 0:
        return f"Output file is empty: {output_path}"
    if started_at is not None and output_path.stat().st_mtime + 1 < started_at:
        return f"Output file timestamp is older than the mux task: {output_path}"
    return None
