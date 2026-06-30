from __future__ import annotations

import re
from pathlib import Path

from .matcher import match_audios, match_subtitles
from .models import (
    AppConfig,
    AttachmentPlan,
    AudioTrackPlan,
    FontResult,
    MuxPlan,
    PlanBuildResult,
    ScanResult,
    SkippedFile,
    SubtitleTrackPlan,
)
from .subtitle import build_track_name, detect_subtitle_info


WINDOWS_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*]')


def build_mux_plans(scan: ScanResult, config: AppConfig, fonts: FontResult | None = None) -> PlanBuildResult:
    result = PlanBuildResult()
    font_result = fonts or FontResult()
    attachments = [AttachmentPlan(path=path) for path in font_result.fonts]
    suffix = config.task.output_suffix or "_Plex"

    for video in scan.videos:
        if config.task.name_strategy == "suffix" and suffix and video.stem.endswith(suffix):
            result.skipped_files.append(SkippedFile(path=video, reason="already_processed", stage="planning"))
            continue

        subtitle_matches, subtitle_skips = match_subtitles(video, scan.subtitles)
        audio_matches, audio_skips = match_audios(video, scan.audios)
        plan_skips = [*subtitle_skips, *audio_skips]

        subtitle_tracks: list[SubtitleTrackPlan] = []
        subtitle_cleanup_candidates: list[Path] = []
        for match in subtitle_matches:
            info = detect_subtitle_info(match.file, config.subtitle)
            if not info.language:
                plan_skips.append(SkippedFile(path=match.file, reason="unmatched_language", stage="subtitle"))
                continue
            subtitle_tracks.append(
                SubtitleTrackPlan(
                    path=match.file,
                    track_name=build_track_name(info, config.subtitle),
                    mkv_language=info.mkv_language,
                    ietf_language=info.ietf_language,
                    default_track=info.default_language,
                    forced_track=False,
                    match_reason=match.reason,
                )
            )
            subtitle_cleanup_candidates.append(match.file)

        audio_tracks = [
            AudioTrackPlan(path=match.file, language=None, match_reason=match.reason)
            for match in audio_matches
        ]

        if not subtitle_tracks and not audio_tracks:
            result.skipped_files.append(SkippedFile(path=video, reason="no_mux_inputs", stage="planning"))
            result.skipped_files.extend(plan_skips)
            continue

        output_path = build_output_path(video, scan.input_dir, config)
        if output_path.resolve() == video.resolve():
            result.skipped_files.append(
                SkippedFile(path=video, reason="invalid_output_path_same_as_input", stage="planning")
            )
            result.skipped_files.extend(plan_skips)
            continue

        cleanup_candidates = unique_paths([video, *subtitle_cleanup_candidates, *(track.path for track in audio_tracks)])
        result.plans.append(
            MuxPlan(
                source_video=video,
                output_path=output_path,
                subtitle_tracks=subtitle_tracks,
                audio_tracks=audio_tracks,
                attachments=attachments,
                cleanup_candidates=cleanup_candidates,
                skipped_files=plan_skips,
            )
        )

    if not scan.videos:
        result.skipped_files.append(SkippedFile(path=scan.input_dir, reason="no_video_files", stage="scan"))

    return result


def build_output_path(video: Path, input_dir: Path, config: AppConfig) -> Path:
    output_dir = resolve_output_dir(video, input_dir, config)
    stem = video.stem
    strategy = config.task.name_strategy
    if strategy == "same-name":
        file_name = f"{stem}.mkv"
    elif strategy == "template" and config.task.name_template:
        file_name = config.task.name_template.format(stem=stem, name=video.name, suffix=config.task.output_suffix)
        if Path(file_name).suffix.lower() != ".mkv":
            file_name = f"{file_name}.mkv"
    else:
        file_name = f"{stem}{config.task.output_suffix or '_Plex'}.mkv"
    return output_dir / sanitize_file_name(file_name)


def resolve_output_dir(video: Path, input_dir: Path, config: AppConfig) -> Path:
    if config.task.output_dir is None:
        return video.parent
    if config.task.output_dir.is_absolute():
        return config.task.output_dir
    return input_dir / config.task.output_dir


def sanitize_file_name(file_name: str) -> str:
    sanitized = WINDOWS_ILLEGAL_CHARS_RE.sub("_", file_name)
    return sanitized.strip() or "output.mkv"


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique
