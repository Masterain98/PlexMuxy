from __future__ import annotations

import os
import shutil
from pathlib import Path

from .font import remove_fonts_dir
from .models import AppConfig, CleanupResult, MuxPlan, MuxResult


def cleanup_successful_results(
    results: list[MuxResult],
    config: AppConfig,
    yes: bool = False,
) -> list[CleanupResult]:
    cleanup_results: list[CleanupResult] = []
    cleaned: set[Path] = set()

    for result in results:
        if not result.success or not result.verified:
            continue
        plan = result.plan
        for candidate in plan.cleanup_candidates:
            resolved = candidate.resolve()
            if resolved in cleaned:
                continue
            action = cleanup_action_for(candidate, plan, config)
            if action == "none":
                cleanup_results.append(CleanupResult(path=candidate, action="none", success=True))
                cleaned.add(resolved)
                continue
            cleanup_results.append(run_cleanup_action(candidate, action, plan, config, yes=yes))
            cleaned.add(resolved)

    if config.font.delete_fonts_after_mux and any(result.success and result.verified for result in results):
        fonts_dir = successful_results_input_dir(results) / "Fonts"
        if not yes:
            cleanup_results.append(
                CleanupResult(
                    path=fonts_dir,
                    action="delete",
                    success=False,
                    error="Deleting Fonts requires --yes",
                )
            )
        else:
            try:
                remove_fonts_dir(fonts_dir)
                cleanup_results.append(CleanupResult(path=fonts_dir, action="delete", success=True))
            except OSError as exc:
                cleanup_results.append(CleanupResult(path=fonts_dir, action="delete", success=False, error=str(exc)))

    return cleanup_results


def cleanup_action_for(path: Path, plan: MuxPlan, config: AppConfig) -> str:
    if config.task.cleanup == "none":
        return "none"
    if config.task.cleanup_overridden:
        return config.task.cleanup
    if path == plan.source_video and config.task.delete_original_video:
        return "delete"
    if path in [track.path for track in plan.audio_tracks] and config.task.delete_original_audio:
        return "delete"
    if path in [track.path for track in plan.subtitle_tracks] and config.task.delete_subtitle:
        return "delete"
    return config.task.cleanup


def run_cleanup_action(
    path: Path,
    action: str,
    plan: MuxPlan,
    config: AppConfig,
    yes: bool = False,
) -> CleanupResult:
    if action == "delete":
        if not yes:
            return CleanupResult(path=path, action="delete", success=False, error="Delete cleanup requires --yes")
        try:
            os.remove(path)
            return CleanupResult(path=path, action="delete", success=True)
        except OSError as exc:
            return CleanupResult(path=path, action="delete", success=False, error=str(exc))

    if action == "move":
        destination_dir = resolve_extra_dir(plan, config)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = unique_destination(destination_dir / path.name)
        try:
            shutil.move(str(path), str(destination))
            return CleanupResult(path=path, action="move", success=True, destination=destination)
        except OSError as exc:
            return CleanupResult(path=path, action="move", success=False, destination=destination, error=str(exc))

    return CleanupResult(path=path, action="none", success=True)


def resolve_extra_dir(plan: MuxPlan, config: AppConfig) -> Path:
    extra_dir = Path(config.task.extra_dir)
    if extra_dir.is_absolute():
        return extra_dir
    return plan.source_video.parent / extra_dir


def unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def successful_results_input_dir(results: list[MuxResult]) -> Path:
    for result in results:
        if result.success and result.verified:
            return result.plan.source_video.parent
    return Path.cwd()
