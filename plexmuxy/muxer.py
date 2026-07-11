from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from .models import AppConfig, MuxPlan, MuxResult, SourceTrackInfo, VerificationResult


def execute_mux_plan(
    plan: MuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None = None,
) -> MuxResult:
    if plan.output_path.resolve() == plan.source_video.resolve():
        return failure(plan, "OUTPUT_EQUALS_INPUT", "Output path is the same as the source video; refusing in-place mux.")
    if plan.output_path.exists() and not config.task.overwrite:
        return failure(plan, "OUTPUT_EXISTS", f"Output file already exists: {plan.output_path}")
    mkvmerge_path = resolve_mkvmerge_path(config)
    if mkvmerge_path is None:
        return failure(plan, "MKVMERGE_NOT_FOUND", "mkvmerge was not found. Set mkvmerge.path or add it to PATH.")
    if cancellation_event is not None and cancellation_event.is_set():
        return failure(plan, "CANCELLED", "Mux was cancelled before starting")

    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = plan.output_path.with_name(f".{plan.output_path.name}.{uuid.uuid4().hex}.plexmuxy-part")
    command = build_mkvmerge_command(plan, partial, mkvmerge_path)
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=windows_no_window_flag(),
        )
        while process.poll() is None:
            if cancellation_event is not None and cancellation_event.wait(0.2):
                terminate_process(process)
                handle_failed_output(partial, plan.output_path, config.task.failed_output_action)
                return failure(plan, "CANCELLED", "Mux was cancelled")
            if cancellation_event is None:
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
        stdout, stderr = process.communicate()
    except OSError as exc:
        handle_failed_output(partial, plan.output_path, config.task.failed_output_action)
        return failure(plan, "MUX_EXECUTION_FAILED", str(exc))
    if process.returncode not in {0, 1}:  # mkvmerge uses 1 for warnings.
        handle_failed_output(partial, plan.output_path, config.task.failed_output_action)
        return failure(plan, "MUX_EXECUTION_FAILED", (stderr or stdout or "mkvmerge failed").strip())

    verification = verify_mux_output(plan, partial, mkvmerge_path)
    if not verification.success:
        handled = handle_failed_output(partial, plan.output_path, config.task.failed_output_action)
        warnings = [f"Failed output retained as: {handled}"] if handled else []
        return MuxResult(
            plan=plan, success=False, output_path=plan.output_path,
            error_code=verification.error_code, error=verification.error,
            warnings=warnings, verified=False, verification=verification,
        )
    try:
        os.replace(partial, plan.output_path)
    except OSError as exc:
        handle_failed_output(partial, plan.output_path, config.task.failed_output_action)
        return failure(plan, "OUTPUT_REPLACE_FAILED", str(exc), verification=verification)
    warnings = []
    if process.returncode == 1:
        warnings.append((stderr or stdout or "mkvmerge completed with warnings").strip())
    return MuxResult(
        plan=plan, success=True, output_path=plan.output_path, warnings=warnings,
        verified=True, verification=verification,
    )


def build_mkvmerge_command(plan: MuxPlan, output_path: Path, mkvmerge_path: str) -> list[str]:
    command = [mkvmerge_path, "--output", str(output_path), str(plan.source_video)]
    for track in plan.subtitle_tracks:
        command.extend([
            "--track-name", f"0:{track.track_name}",
            "--language", f"0:{track.mkv_language}",
            "--language-ietf", f"0:{track.ietf_language}",
            "--default-track-flag", f"0:{'yes' if track.default_track else 'no'}",
            "--forced-display-flag", f"0:{'yes' if track.forced_track else 'no'}",
            str(track.path),
        ])
    command.extend(str(track.path) for track in plan.audio_tracks)
    for attachment in plan.attachments:
        mime = mimetypes.guess_type(attachment.path.name)[0]
        if attachment.path.suffix.casefold() == ".ttf":
            mime = "application/x-truetype-font"
        elif attachment.path.suffix.casefold() in {".otf", ".ttc"}:
            mime = "application/vnd.ms-opentype"
        command.extend(["--attachment-mime-type", mime or "application/octet-stream", "--attach-file", str(attachment.path)])
    return command


def verify_mux_output(plan: MuxPlan, output_path: Path, mkvmerge_path: str) -> VerificationResult:
    basic_error = verify_output(output_path)
    if basic_error:
        code = "OUTPUT_NOT_CREATED" if not output_path.exists() else "OUTPUT_EMPTY"
        return VerificationResult(False, code, basic_error)
    try:
        completed = subprocess.run(
            [mkvmerge_path, "-J", str(output_path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, creationflags=windows_no_window_flag(),
        )
    except OSError as exc:
        return VerificationResult(False, "OUTPUT_INVALID_CONTAINER", str(exc))
    if completed.returncode != 0:
        return VerificationResult(False, "OUTPUT_INVALID_CONTAINER", completed.stderr.strip() or "mkvmerge could not parse output")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return VerificationResult(False, "OUTPUT_INVALID_CONTAINER", f"Invalid mkvmerge JSON: {exc}")
    tracks = data.get("tracks", []) if isinstance(data, dict) else []
    attachments = data.get("attachments", []) if isinstance(data, dict) else []
    video_tracks = [item for item in tracks if item.get("type") == "video"]
    subtitle_tracks = [item for item in tracks if item.get("type") == "subtitles"]
    if not video_tracks:
        return VerificationResult(False, "TRACK_COUNT_MISMATCH", "Output contains no video track", data)
    if len(subtitle_tracks) < len(plan.subtitle_tracks):
        return VerificationResult(False, "TRACK_COUNT_MISMATCH", "Output has fewer subtitle tracks than planned", data)
    if len(attachments) < len(plan.attachments):
        return VerificationResult(False, "ATTACHMENT_COUNT_MISMATCH", "Output has fewer attachments than planned", data)
    for expected in plan.subtitle_tracks:
        if not any(subtitle_matches(expected, actual) for actual in subtitle_tracks):
            return VerificationResult(
                False, "TRACK_PROPERTY_MISMATCH",
                f"Subtitle track properties were not preserved: {expected.track_name}", data,
            )
    expected_names = {item.path.name.casefold() for item in plan.attachments}
    actual_names = {str(item.get("file_name", "")).casefold() for item in attachments}
    if not expected_names.issubset(actual_names):
        return VerificationResult(False, "ATTACHMENT_COUNT_MISMATCH", "Planned font attachments are missing", data)
    return VerificationResult(True, details={
        "video_tracks": len(video_tracks), "subtitle_tracks": len(subtitle_tracks),
        "attachments": len(attachments), "container": data.get("container", {}),
    })


def subtitle_matches(expected: Any, actual: dict[str, Any]) -> bool:
    props = actual.get("properties", {})
    languages = {str(props.get("language", "")).casefold(), str(props.get("language_ietf", "")).casefold()}
    language_ok = expected.mkv_language.casefold() in languages or expected.ietf_language.casefold() in languages
    return (
        language_ok
        and str(props.get("track_name", "")) == expected.track_name
        and bool(props.get("default_track", False)) is expected.default_track
        and bool(props.get("forced_track", False)) is expected.forced_track
    )


def inspect_source_tracks(source: Path, mkvmerge_path: str) -> list[SourceTrackInfo]:
    completed = subprocess.run(
        [mkvmerge_path, "-J", str(source)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, creationflags=windows_no_window_flag(),
    )
    if completed.returncode != 0:
        return []
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    result: list[SourceTrackInfo] = []
    for item in data.get("tracks", []):
        props = item.get("properties", {})
        result.append(SourceTrackInfo(
            id=int(item.get("id", -1)), type=str(item.get("type", "unknown")), codec=item.get("codec"),
            language=props.get("language_ietf") or props.get("language"), title=props.get("track_name"),
            default_track=bool(props.get("default_track", False)), forced_track=bool(props.get("forced_track", False)),
            channels=props.get("audio_channels"),
        ))
    return result


def resolve_mkvmerge_path(config: AppConfig) -> str | None:
    configured = config.mkvmerge.path.strip()
    if configured:
        path = Path(configured)
        if path.is_dir():
            path = path / ("mkvmerge.exe" if os.name == "nt" else "mkvmerge")
        if path.is_file():
            return str(path)
        return shutil.which(configured)
    found = shutil.which("mkvmerge")
    if found:
        return found
    for name in ("mkvmerge.exe", "mkvmerge"):
        local = Path.cwd() / name
        if local.is_file():
            return str(local)
    return None


def verify_output(output_path: Path, started_at: float | None = None) -> str | None:
    if not output_path.exists():
        return f"Output file was not created: {output_path}"
    if output_path.stat().st_size <= 0:
        return f"Output file is empty: {output_path}"
    if started_at is not None and output_path.stat().st_mtime + 1 < started_at:
        return f"Output file timestamp is older than the mux task: {output_path}"
    return None


def handle_failed_output(partial: Path, final_path: Path, action: str) -> Path | None:
    if not partial.exists():
        return None
    if action == "delete":
        partial.unlink(missing_ok=True)
        return None
    if action == "rename":
        target = unique_failed_path(final_path.with_name(f"{final_path.name}.failed"))
        os.replace(partial, target)
        return target
    return partial


def unique_failed_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.name}.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def terminate_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def windows_no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def failure(
    plan: MuxPlan, code: str, message: str, verification: VerificationResult | None = None
) -> MuxResult:
    return MuxResult(
        plan=plan, success=False, output_path=plan.output_path, error_code=code,
        error=message, verified=False, verification=verification,
    )
