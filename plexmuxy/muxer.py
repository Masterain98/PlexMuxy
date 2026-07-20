from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import uuid
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from .ass_font_embedder import embed_fonts_into_ass
from .dependencies import resolve_mkvmerge
from .models import (
    AppConfig,
    AttachmentPlan,
    FontMimeMode,
    MuxPlan,
    MuxResult,
    PreparedMuxPlan,
    SourceTrackInfo,
    SubtitleTrackPlan,
    VerificationResult,
    font_mime_type_for_suffix,
)

logger = logging.getLogger(__name__)


def execute_mux_plan(
    plan: MuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None = None,
) -> MuxResult:
    scheme = config.font.embed_scheme
    embedded: list[str | None] = []
    if scheme in ("ass", "both"):
        embedded = _embed_ass_subtitles(
            plan.output_path, plan.subtitle_tracks, plan.attachments
        )
    if scheme == "ass" and any(embedded):
        # Fonts now live inside the subtitle file, so mux that self-contained
        # track and drop the separate MKV font attachments. Only replace tracks
        # that were actually embedded; leave others at their original path.
        subtitle_tracks = [
            replace(track, path=Path(emb)) if emb is not None else track
            for track, emb in zip(plan.subtitle_tracks, embedded, strict=True)
        ]
        runtime = replace(plan, subtitle_tracks=subtitle_tracks, attachments=[])
    else:
        # "attachment" keeps the MKV font attachments; "both" keeps them and
        # additionally writes the self-contained .ass next to the output.
        runtime = plan
    result = _execute_runtime_plan(plan, runtime, config, cancellation_event)
    produced = [p for p in embedded if p is not None]
    if produced:
        result = replace(result, embedded_subtitles=produced)
    return result


def _embed_ass_subtitles(
    output_path: Path,
    subtitle_tracks: list[SubtitleTrackPlan],
    attachments: list[AttachmentPlan],
) -> list[str | None]:
    """EXPERIMENTAL: emit self-contained .ass files with their fonts embedded.

    Complements (or, in "ass" mode, replaces) MKV font attachments so the
    subtitle can be played standalone. Fonts are embedded in a ``[Fonts]``
    section using the Aegisub/libass uuencode scheme.

    Returns a list parallel to *subtitle_tracks*: each entry is the embedded
    output path, or ``None`` when the track was skipped or embedding failed.
    """
    font_paths = [a.path for a in attachments if a.path.suffix.lower() in _FONT_ATTACHMENT_SUFFIXES]
    if not font_paths or not subtitle_tracks:
        return [None] * len(subtitle_tracks)
    parent = output_path.parent
    stem = output_path.stem
    multi = len(subtitle_tracks) > 1
    produced: list[str | None] = []
    for index, track in enumerate(subtitle_tracks):
        if not track.path or not track.path.exists():
            produced.append(None)
            continue
        suffix = f".embedded.{index}.ass" if multi else ".embedded.ass"
        out = parent / f"{stem}{suffix}"
        try:
            embed_fonts_into_ass(track.path, font_paths, out)
            produced.append(str(out))
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Failed to emit embedded ASS %s: %s", out, exc)
            produced.append(None)
    if any(produced):
        logger.info("Emitted %d self-contained subtitle file(s) with embedded fonts", sum(p is not None for p in produced))
    return produced


def execute_prepared_mux_plan(
    prepared: PreparedMuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None = None,
) -> MuxResult:
    scheme = config.font.embed_scheme
    embedded: list[str | None] = []
    if scheme in ("ass", "both"):
        embedded = _embed_ass_subtitles(
            prepared.original_plan.output_path, prepared.subtitle_tracks, prepared.attachments
        )
    if scheme == "ass" and any(embedded):
        # Fonts now live inside the subtitle file, so mux that self-contained
        # track and drop the separate MKV font attachments. Only replace tracks
        # that were actually embedded; leave others at their original path.
        subtitle_tracks = [
            replace(track, path=Path(emb)) if emb is not None else track
            for track, emb in zip(prepared.subtitle_tracks, embedded, strict=True)
        ]
        runtime = replace(
            prepared.original_plan,
            subtitle_tracks=subtitle_tracks,
            attachments=[],
        )
    else:
        runtime = replace(
            prepared.original_plan,
            subtitle_tracks=list(prepared.subtitle_tracks),
            attachments=list(prepared.attachments),
        )
    result = _execute_runtime_plan(
        prepared.original_plan,
        runtime,
        config,
        cancellation_event,
        prepared.subset_warnings,
        prepared,
    )
    produced = [p for p in embedded if p is not None]
    if produced:
        result = replace(result, embedded_subtitles=produced)
    return result


_FONT_ATTACHMENT_SUFFIXES = frozenset({
    ".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2",
})


def _execute_runtime_plan(
    original_plan: MuxPlan,
    runtime_plan: MuxPlan,
    config: AppConfig,
    cancellation_event: threading.Event | None,
    preparation_warnings: list[str] | None = None,
    prepared: PreparedMuxPlan | None = None,
) -> MuxResult:
    def runtime_failure(
        code: str,
        message: str,
        verification: VerificationResult | None = None,
    ) -> MuxResult:
        result = failure(original_plan, code, message, verification=verification)
        result.warnings.extend(preparation_warnings or [])
        return result

    in_place = runtime_plan.output_path.resolve() == runtime_plan.source_video.resolve()
    if not in_place and runtime_plan.output_path.exists() and not config.task.overwrite:
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
    command = build_mkvmerge_command(
        runtime_plan, partial, mkvmerge_path, mime_mode=config.font.mime_mode,
    )
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=windows_no_window_flag(),
        )
        # Use communicate(timeout=...) instead of poll()+wait() so the PIPE
        # buffers are drained while waiting. Without draining, a verbose
        # mkvmerge can fill the OS pipe buffer and block forever.
        stdout: str | None = None
        stderr: str | None = None
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancellation_event is not None and cancellation_event.is_set():
                    terminate_process(process)
                    stdout, stderr = process.communicate()
                    handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
                    return runtime_failure("CANCELLED", "Mux was cancelled")
        stdout = stdout or ""
        stderr = stderr or ""
    except OSError as exc:
        handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
        return runtime_failure("MUX_EXECUTION_FAILED", str(exc))
    if process.returncode not in {0, 1}:  # mkvmerge uses 1 for warnings.
        handle_failed_output(partial, runtime_plan.output_path, config.task.failed_output_action)
        return runtime_failure("MUX_EXECUTION_FAILED", (stderr or stdout or "mkvmerge failed").strip())

    verification = verify_mux_output(runtime_plan, partial, mkvmerge_path, mime_mode=config.font.mime_mode)
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


def build_mkvmerge_command(
    plan: MuxPlan,
    output_path: Path,
    mkvmerge_path: str,
    *,
    mime_mode: FontMimeMode = "legacy",
) -> list[str]:
    command = [mkvmerge_path, "--output", str(output_path)]
    # Keep mkvmerge from rewriting our explicit IETF language tags.
    command.append("--normalize-language-ietf")
    command.append("off")
    # In legacy mode the plan declares the old font MIME types
    # (application/x-truetype-font, application/vnd.ms-opentype). mkvmerge v66+
    # rewrites font attachment MIME types to the modern `font/ttf` / `font/otf`
    # scheme when writing, so ask it to keep the legacy scheme to match the plan.
    # In modern mode the plan declares the modern types and mkvmerge already
    # writes them by default, so no flag is needed. Older mkvmerge already used
    # the legacy types by default, hence the version gate (don't pass an unknown
    # flag to old builds).
    if mime_mode == "legacy" and mkvmerge_supports_legacy_font_mime_types(mkvmerge_path):
        command.append("--enable-legacy-font-mime-types")
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
            "--attachment-mime-type", attachment_mime_type(attachment, mime_mode=mime_mode),
            "--attach-file", str(attachment.path),
        ])
    return command


def verify_mux_output(
    plan: MuxPlan,
    output_path: Path,
    mkvmerge_path: str,
    *,
    mime_mode: FontMimeMode = "legacy",
) -> VerificationResult:
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
        (item.name.casefold(), attachment_mime_type(item, mime_mode=mime_mode).casefold())
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
        _normalize_language(track.language),
        track.title or "",
        track.default_track,
        track.forced_track,
        track.channels,
    )


def output_audio_fingerprint(track: dict[str, Any]) -> tuple[Any, ...]:
    props = track.get("properties", {})
    return (
        str(track.get("codec") or ""),
        _normalize_language(props.get("language_ietf") or props.get("language")),
        str(props.get("track_name") or ""),
        bool(props.get("default_track", False)),
        bool(props.get("forced_track", False)),
        props.get("audio_channels"),
    )


# Common ISO 639-1/639-2 legacy → IETF BCP 47 canonical aliases that mkvmerge
# may rewrite when it adds the LanguageIETF element during muxing.
_LANGUAGE_ALIASES: dict[str, str] = {
    "jpn": "ja",
    "eng": "en",
    "chi": "zh",
    "fre": "fr",
    "ger": "de",
    "ita": "it",
    "spa": "es",
    "por": "pt",
    "rus": "ru",
    "kor": "ko",
    "tha": "th",
    "vie": "vi",
    "ind": "id",
    "zho": "zh",
    "zul": "zu",
}


def _normalize_language(value: str | None) -> str:
    """Normalize a language tag so legacy (ISO 639-2/B) and IETF (BCP 47)
    values compare consistently during mux verification."""
    if not value:
        return ""
    folded = str(value).casefold()
    return _LANGUAGE_ALIASES.get(folded, folded)


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


_MKVMERGE_VERSION_CACHE: dict[str, tuple[int, ...] | None] = {}
_MKVMERGE_VERSION_LOCK = threading.Lock()


def _parse_mkvmerge_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"\bmkvmerge\s+v?(\d+(?:\.\d+)*)", text, re.IGNORECASE)
    if not match:
        return None
    parts: list[int] = []
    for part in match.group(1).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            break
    return tuple(parts)


def mkvmerge_supports_legacy_font_mime_types(mkvmerge_path: str) -> bool:
    """Return True when this mkvmerge build honors --enable-legacy-font-mime-types.

    The option was introduced in MKVToolNix v66. Earlier versions already stored
    the legacy font MIME types by default, so the flag is unnecessary (and would
    be rejected as unknown) for them.
    """
    with _MKVMERGE_VERSION_LOCK:
        if mkvmerge_path in _MKVMERGE_VERSION_CACHE:
            version = _MKVMERGE_VERSION_CACHE[mkvmerge_path]
        else:
            try:
                completed = subprocess.run(
                    [mkvmerge_path, "--version"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=5.0, shell=False, creationflags=windows_no_window_flag(),
                )
                version = _parse_mkvmerge_version(completed.stdout + completed.stderr)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                # Any failure to probe (missing tool, unexpected output, sandbox
                # restrictions) means we cannot confirm support, so stay safe and
                # omit the flag. Old mkvmerge already used legacy MIME types.
                version = None
            _MKVMERGE_VERSION_CACHE[mkvmerge_path] = version
    return version is not None and version >= (66,)


def attachment_mime_type(attachment: AttachmentPlan, *, mime_mode: FontMimeMode = "legacy") -> str:
    if attachment.expected_mime_type:
        return attachment.expected_mime_type
    return font_mime_type_for_suffix(attachment.name, mode=mime_mode)


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
