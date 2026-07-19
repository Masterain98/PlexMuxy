from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .ass_analysis import analyze_ass_file
from .font_catalog import FontCatalogResult
from .font_prepare import build_subset_intent
from .font_usage import select_referenced_fonts
from .matcher import assign_candidates
from .models import (
    AppConfig,
    AttachmentPlan,
    AudioTrackPlan,
    FontResult,
    FontUsage,
    MuxPlan,
    PlanBuildResult,
    ScanResult,
    SkippedFile,
    SubtitleTrackPlan,
)
from .subtitle import build_track_name, detect_subtitle_info

WINDOWS_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
FontProgressCallback = Callable[[str], None]


@dataclass
class _UsageAggregate:
    requested: str = ""
    codepoints: set[int] = field(default_factory=set)
    paths: set[Path] = field(default_factory=set)


def build_mux_plans(
    scan: ScanResult,
    config: AppConfig,
    fonts: FontResult | None = None,
    font_catalog: FontCatalogResult | None = None,
    font_progress_callback: FontProgressCallback | None = None,
) -> PlanBuildResult:
    result = PlanBuildResult()
    font_result = fonts or FontResult()
    eligible_videos: list[Path] = []
    suffix = config.task.output_suffix or "_Plex"
    for video in scan.videos:
        if config.task.name_strategy == "suffix" and suffix and video.stem.endswith(suffix):
            result.skipped_files.append(SkippedFile(video, "already_processed", "planning"))
        else:
            eligible_videos.append(video)

    subtitle_assignments, subtitle_skips = assign_candidates(
        eligible_videos, scan.subtitles, config.matching, allow_movie_fallback=True
    )
    audio_assignments, audio_skips = assign_candidates(
        eligible_videos, scan.audios, config.matching, allow_movie_fallback=False
    )
    result.skipped_files.extend([*subtitle_skips, *audio_skips])

    for video in eligible_videos:
        plan_skips: list[SkippedFile] = []
        subtitle_tracks: list[SubtitleTrackPlan] = []
        subtitle_cleanup_candidates: list[Path] = []
        for match in subtitle_assignments[video]:
            info = detect_subtitle_info(match.file, config.subtitle)
            if not info.language:
                skipped = SkippedFile(match.file, "unmatched_language", "subtitle")
                plan_skips.append(skipped)
                result.skipped_files.append(skipped)
                continue
            subtitle_tracks.append(SubtitleTrackPlan(
                path=match.file,
                track_name=build_track_name(info, config.subtitle),
                mkv_language=info.mkv_language,
                ietf_language=info.ietf_language,
                default_track=info.default_language,
                forced_track=False,
                match_reason=match.reason,
            ))
            subtitle_cleanup_candidates.append(match.file)

        audio_tracks = [AudioTrackPlan(match.file, None, match.reason) for match in audio_assignments[video]]
        if not subtitle_tracks and not audio_tracks:
            skipped = SkippedFile(video, "no_mux_inputs", "planning")
            result.skipped_files.append(skipped)
            result.skipped_files.extend(item for item in plan_skips if item not in result.skipped_files)
            continue

        output_path = build_output_path(video, scan.input_dir, config)
        if output_path.resolve() == video.resolve():
            result.skipped_files.append(SkippedFile(video, "invalid_output_path_same_as_input", "planning"))
            continue
        if output_path.exists() and not config.task.overwrite:
            result.skipped_files.append(SkippedFile(video, "output_exists", "planning"))
            continue

        subset_intent = None
        if config.font.mode == "subset":
            selected_fonts, subset_intent, font_warnings, skip_reason = plan_font_subsets(
                [track.path for track in subtitle_tracks],
                font_result.fonts,
                (font_catalog or FontCatalogResult()).faces,
                config,
                font_progress_callback,
            )
        else:
            selected_fonts, font_warnings, skip_for_fonts = select_plan_fonts(
                [track.path for track in subtitle_tracks], font_result.fonts, config
            )
            skip_reason = "missing_referenced_font" if skip_for_fonts else None
        if skip_reason:
            result.skipped_files.append(SkippedFile(video, skip_reason, "font"))
            continue
        cleanup_candidates = unique_paths(
            [video, *subtitle_cleanup_candidates, *(track.path for track in audio_tracks)]
        )
        result.plans.append(MuxPlan(
            source_video=video,
            output_path=output_path,
            subtitle_tracks=subtitle_tracks,
            audio_tracks=audio_tracks,
            attachments=[AttachmentPlan(path) for path in selected_fonts],
            cleanup_candidates=cleanup_candidates,
            skipped_files=plan_skips,
            warnings=font_warnings,
            font_subset_intent=subset_intent,
        ))

    if not scan.videos:
        result.skipped_files.append(SkippedFile(scan.input_dir, "no_video_files", "scan"))
    return result


def select_plan_fonts(
    subtitles: list[Path], fonts: list[Path], config: AppConfig
) -> tuple[list[Path], list[str], bool]:
    if config.font.mode == "all" or not subtitles:
        return fonts, [], False
    selected, missing = select_referenced_fonts(subtitles, fonts)
    warnings: list[str] = []
    if not missing:
        return selected, warnings, False
    warning = f"Missing referenced fonts: {', '.join(sorted(missing))}"
    action = config.font.missing_font_action
    if action == "fallback-all":
        return fonts, [*warnings, warning, "missing_font_fallback_all"], False
    if action in {"skip-video", "fail-job"}:
        return selected, [*warnings, warning], True
    return selected, [*warnings, warning], False


def plan_font_subsets(
    subtitles: list[Path],
    fonts: list[Path],
    catalog: list,
    config: AppConfig,
    progress_callback: FontProgressCallback | None = None,
):
    usages: list[FontUsage] = []
    warnings: list[str] = []
    unsafe = False
    aggregates: dict[tuple[str, int, bool], _UsageAggregate] = defaultdict(_UsageAggregate)
    if progress_callback is not None:
        progress_callback("analyzing_subtitles")
    for subtitle in subtitles:
        try:
            analysis = analyze_ass_file(subtitle)
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append(f"ass_analysis_failed:{subtitle.name}:{exc}")
            unsafe = True
            continue
        for issue in analysis.issues:
            warnings.append(f"{issue.code}:{subtitle.name}:{issue.message}")
        if not analysis.complete or not analysis.safe_to_rewrite:
            unsafe = True
        for item in analysis.usages:
            key = (item.normalized_family, item.weight, item.italic)
            aggregate = aggregates[key]
            aggregate.requested = aggregate.requested or item.requested_family
            aggregate.codepoints.update(item.codepoints)
            aggregate.paths.update(item.subtitle_paths)
    if unsafe:
        return [], None, warnings, "unsafe_ass_for_subset"
    for (normalized, weight, italic), aggregate in sorted(aggregates.items()):
        usages.append(FontUsage(
            requested_family=aggregate.requested,
            normalized_family=normalized,
            weight=weight,
            italic=italic,
            codepoints=tuple(sorted(aggregate.codepoints)),
            subtitle_paths=tuple(sorted(aggregate.paths, key=str)),
        ))
    if progress_callback is not None:
        progress_callback("matching_font_faces")
    intent = build_subset_intent(subtitles, usages, catalog)
    if not intent.issues:
        # The real attachments are materialized later from ``intent.groups`` (as
        # subsets), so the planner's ``attachments`` would otherwise be empty and
        # the plan preview would show zero fonts. Return the distinct source font
        # paths that will be subset-attached so the preview can list them. These
        # paths are display-only here; the muxer ignores them in the subset-success
        # path and only uses ``plan.attachments`` for the fallback-full policy.
        return _subset_preview_fonts(intent), intent, warnings, None


def _subset_preview_fonts(intent: FontSubsetIntent) -> list[Path]:
    """Distinct source font paths that a successful subset plan will attach.

    Used only to populate the planner's attachment list for the plan preview; the
    actual mux inputs are produced from ``intent.groups`` at execution time.
    """
    paths: list[Path] = []
    seen: set[Path] = set()
    for group in intent.groups:
        for face in group.faces:
            if face.source_path is None:
                continue
            resolved = face.source_path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return paths

    warnings.extend(f"{issue.code}:{issue.message}" for issue in intent.issues)
    # Subset failures are governed by subset_failure_action (default "fallback-full"),
    # NOT missing_font_action (which only applies to the "referenced" font mode). Using
    # the wrong field here meant subsetting always skipped the video instead of falling
    # back to the full fonts, even with the default fallback policy.
    if config.font.subset_failure_action == "fallback-full":
        return fonts, intent, [*warnings, "font_subset_fallback_all"], None
    reason = "font_subset_blocked"
    return [], intent, warnings, reason


def build_output_path(video: Path, input_dir: Path, config: AppConfig) -> Path:
    output_dir = resolve_output_dir(video, input_dir, config)
    stem = video.stem
    if config.task.name_strategy == "same-name":
        file_name = f"{stem}.mkv"
    elif config.task.name_strategy == "template" and config.task.name_template:
        file_name = config.task.name_template.format(stem=stem, name=video.name, suffix=config.task.output_suffix)
        if Path(file_name).suffix.lower() != ".mkv":
            file_name = f"{file_name}.mkv"
    else:
        file_name = f"{stem}{config.task.output_suffix or '_Plex'}.mkv"
    return output_dir / sanitize_file_name(file_name)


def resolve_output_dir(video: Path, input_dir: Path, config: AppConfig) -> Path:
    if config.task.output_dir is None:
        return video.parent
    return config.task.output_dir if config.task.output_dir.is_absolute() else input_dir / config.task.output_dir


def sanitize_file_name(file_name: str) -> str:
    sanitized = WINDOWS_ILLEGAL_CHARS_RE.sub("_", file_name).rstrip(" .")
    if not sanitized:
        return "output.mkv"
    if len(sanitized) > 240:
        suffix = Path(sanitized).suffix
        sanitized = f"{Path(sanitized).stem[:240 - len(suffix)]}{suffix}"
    return sanitized


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique
