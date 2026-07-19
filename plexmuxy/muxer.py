from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import threading
import uuid
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from .dependencies import resolve_mkvmerge
from .models import (
    AppConfig,
    AttachmentPlan,
    MuxPlan,
    MuxResult,
    PreparedMuxPlan,
    SourceTrackInfo,
    VerificationResult,
)


def execute_mux_plan(
    plan: MuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None = None,
) -> MuxResult:
    return _execute_runtime_plan(plan, plan, config, cancellation_event)


def execute_prepared_mux_plan(
    prepared: PreparedMuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None = None,
) -> MuxResult:
    runtime = replace(
        prepared.original_plan,
        subtitle_tracks=list(prepared.subtitle_tracks),
        attachments=list(prepared.attachments),
    )
    return _execute_runtime_plan(
        prepared.original_plan,
        runtime,
        config,
        cancellation_event,
        prepared.subset_warnings,
    )


def _execute_runtime_plan(
    original_plan: MuxPlan,
    runtime_plan: MuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None,
    preparation_warnings: list[str] | None = None,
) -> MuxResult:
    def runtime_failure(
        code: str,
        message: str,
        verification: VerificationResult | None = None,
    ) -> MuxResult:
        result = failure(original_plan, code, message, verification=verification)
        result.warnings.extend(preparation_warnings or [])
        return result

    if runtime_plan.output_path.resolve() == runtime_plan.source_video.resolve():
        return runtime_failure("OUTPUT_EQUALS_INPUT", "Output path is the same as the source video; refusing in-place mux.")
    if runtime_plan.output_path.exists() and not config.task.overwrite:
        return runtime_failure("OUTPUT_EXISTS", f"Output file already exists: {runtime_plan.output_path}")
    mkvmerge_path = resolve_mkvmerge_path(config)
    if mkvmerge_path is None:
        return runtime_failure("MKVMERGE_NOT_FOUND", "mkvmerge was not found. Set mkvmerge.path or add it to PATH.")
    if cancellation_event is not None and cancellation_event.is_set():
        return runtime_failure("CANCELLED", "Mux was cancelled before starting")

    runtime_plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = runtime_plan.output_path.with_name(
        f".{runtime_plan.output_path.name}.{uuid.uuid4().hex}.plexmuxy-part"
    )
    command = build_mkvmerge_command(runtime_plan, partial, mkvmerge_path)
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=windows_no_window_flag(),
        )
        while process.poll() is None:
            if cancellation_event is not None and cancellation_event.wait(0.2):
                terminate_process(process)
                handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
                return runtime_failure("CANCELLED", "Mux was cancelled")
            if cancellation_event is None:
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
        stdout, stderr = process.communicate()
    except OSError as exc:
        handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
        return runtime_failure("MUX_EXECUTION_FAILED", str(exc))
    if process.returncode not in {0, 1}:  # mkvmerge uses 1 for warnings.
        handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
        return runtime_failure("MUX_EXECUTION_FAILED", (stderr or stdout or "mkvmerge failed").strip())

    verification = verify_mux_output(runtime_plan, partial, mkvmerge_path)
    if not verification.success:
        handled = handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
        warnings = [f"Failed output retained as: {handled}"] if handled else []
        return MuxResult(
            plan=original_plan, success=False, output_path=runtime_plan.output_path,
            error_code=verification.error_code, error=verification.error,
            warnings=[*(preparation_warnings or []), *warnings], verified=False, verification=verification,
        )
    try:
        os.replace(partial, runtime_plan.output_path)
    except OSError as exc:
        handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
        return runtime_failure("OUTPUT_REPLACE_FAILED", str(exc), verification=verification)
    warnings = list(preparation_warnings or [])
    if process.returncode == 1:
        warnings.append((stderr or stdout or "mkvmerge completed with warnings").strip())
    return MuxResult(
        plan=original_plan, success=True, output_path=runtime_plan.output_path, warnings=warnings,
        verified=True, verification=verification,
    )


def build_mkvmerge_command(plan: MuxPlan, output_path: Path, mkvmerge_path: str) -> list[str]:
    command = [mkvmerge_path, "--output", str(output_path)]
    # Keep mkvmerge from rewriting our explicit IETF language tags.
    command.append("--normalize-language-ietf")
    command.append("off")
    source_audio = [track for track in plan.source_tracks if track.type == "audio"]
    included_audio_ids = [track.id for track in source_audio if track.included]
    if source_audio and not included_audio_ids:
        command.append("--no-audio")
    elif source_audio and len(included_audio_ids) != len(source_audio):
        command.extend(["--audio-tracks", ",".join(str(track_id) for track_id in included_audio_ids)])
    command.append(str(plan.source_video))
    subtitle_by_path = {str(track.path): track for track in plan.subtitle_tracks}
    audio_by_path = {str(track.path): track for track in plan.audio_tracks}
    order = plan.external_track_order or [
        *[f"subtitle:{track.path}" for track in plan.subtitle_tracks],
        *[f"audio:{track.path}" for track in plan.audio_tracks],
    ]
    expected = {*[f"subtitle:{path}" for path in subtitle_by_path], *[f"audio:{path}" for path in audio_by_path]}
    if len(order) != len(expected) or set(order) != expected:
        raise ValueError("Invalid external track order in mux plan")
    for item in order:
        kind, path = item.split(":", 1)
        if kind == "subtitle":
            track = subtitle_by_path[path]
            command.extend([
                "--track-name", f"0:{track.track_name}",
                # mkvmerge's --language option accepts IETF BCP 47 tags and
                # writes both LanguageIETF and the compatible legacy Language
                # element. There is no separate --language-ietf input option.
                "--language", f"0:{track.ietf_language}",
                "--default-track-flag", f"0:{'yes' if track.default_track else 'no'}",
                "--forced-display-flag", f"0:{'yes' if track.forced_track else 'no'}",
                str(track.path),
            ])
        else:
            command.append(str(audio_by_path[path].path))
    for attachment in plan.attachments:
        command.extend([
            "--attachment-name", attachment.name,
            "--attachment-mime-type", attachment_mime_type(attachment),
            "--attach-file", str(attachment.path),
        ])
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
    audio_tracks = [item for item in tracks if item.get("type") == "audio"]
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
    expected_source_audio = [
        track for track in plan.source_tracks if track.type == "audio" and track.included
    ]
    if plan.source_tracks:
        expected_audio_count = len(expected_source_audio) + sum(
            track.expected_track_count for track in plan.audio_tracks
        )
        if len(audio_tracks) != expected_audio_count:
            return VerificationResult(
                False,
                "TRACK_COUNT_MISMATCH",
                f"Output has {len(audio_tracks)} audio tracks; planned {expected_audio_count}",
                data,
            )
        expected_audio_properties = Counter(source_audio_fingerprint(track) for track in expected_source_audio)
        actual_audio_properties = Counter(output_audio_fingerprint(track) for track in audio_tracks)
        if any(actual_audio_properties[value] < count for value, count in expected_audio_properties.items()):
            return VerificationResult(
                False,
                "TRACK_PROPERTY_MISMATCH",
                "A retained source audio track is missing or has unexpected properties",
                data,
            )
    expected_names = Counter(item.name.casefold() for item in plan.attachments)
    actual_names = Counter(str(item.get("file_name", "")).casefold() for item in attachments)
    if any(actual_names[name] < count for name, count in expected_names.items()):
        return VerificationResult(False, "ATTACHMENT_COUNT_MISMATCH", "Planned font attachments are missing", data)
    expected_properties = Counter(
        (item.name.casefold(), attachment_mime_type(item).casefold())
        for item in plan.attachments
    )
    actual_properties = Counter(
        (
            str(item.get("file_name", "")).casefold(),
            str(item.get("content_type", "")).casefold(),
        )
        for item in attachments
    )
    if any(actual_properties[value] < count for value, count in expected_properties.items()):
        return VerificationResult(
            False,
            "ATTACHMENT_PROPERTY_MISMATCH",
            "A planned font attachment has an unexpected name or MIME type",
            data,
        )
    return VerificationResult(True, details={
        "video_tracks": len(video_tracks), "audio_tracks": len(audio_tracks),
        "subtitle_tracks": len(subtitle_tracks),
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


def source_audio_fingerprint(track: SourceTrackInfo) -> tuple[Any, ...]:
    return (
        track.codec or "",
        (track.language or "").casefold(),
        track.title or "",
        track.default_track,
        track.forced_track,
        track.channels,
    )


def output_audio_fingerprint(track: dict[str, Any]) -> tuple[Any, ...]:
    props = track.get("properties", {})
    return (
        str(track.get("codec") or ""),
        str(props.get("language_ietf") or props.get("language") or "").casefold(),
        str(props.get("track_name") or ""),
        bool(props.get("default_track", False)),
        bool(props.get("forced_track", False)),
        props.get("audio_channels"),
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
    return resolve_mkvmerge(config.mkvmerge.path).resolved_path


def attachment_mime_type(attachment: AttachmentPlan) -> str:
    if attachment.expected_mime_type:
        return attachment.expected_mime_type
    mime = mimetypes.guess_type(attachment.name)[0]
    suffix = Path(attachment.name).suffix.casefold()
    if suffix == ".ttf":
        return "application/x-truetype-font"
    if suffix in {".otf", ".ttc", ".otc"}:
        return "application/vnd.ms-opentype"
    return mime or "application/octet-stream"


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
