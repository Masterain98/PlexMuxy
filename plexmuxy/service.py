from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from .cleanup import cleanup_successful_results
from .config import config_to_dict
from .errors import StalePlanError
from .font import prepare_fonts
from .font_cache import FontSubsetCache
from .font_catalog import build_font_catalog
from .font_prepare import FontPreparationError, SubsetWorkspace, prepare_subset_plan
from .integrations.plex import PlexIntegrationError, refresh_paths
from .models import AppConfig, JobReport, MuxPlanSnapshot, MuxResult, PlanEdit, PreparedMuxPlan, ProgressEvent
from .muxer import execute_mux_plan, execute_prepared_mux_plan, inspect_source_tracks, resolve_mkvmerge_path
from .plan_edit import PlanEditError, apply_plan_edits, source_track_overrides_from_edits
from .planner import build_mux_plans
from .scanner import scan_media_dir
from .snapshot import create_plan_snapshot, validate_plan_snapshot
from .track_policy import TrackPolicyError, decide_source_tracks

ProgressCallback = Callable[[ProgressEvent], None]

# Cache the expensive, edit-independent planning intermediates (filesystem scan,
# font preparation, font catalog, and per-video source-track inspection) so that
# repeated draft edits re-plan in milliseconds instead of re-scanning everything.
_plan_cache: "OrderedDict[str, tuple[str, dict]]" = OrderedDict()
_plan_cache_lock = threading.Lock()
_PLAN_CACHE_LIMIT = 4


def _config_signature(config: AppConfig) -> str:
    try:
        return hashlib.sha256(
            json.dumps(config_to_dict(config), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    except Exception:  # noqa: BLE001 - fall back to a full recompute when signing fails.
        return ""


def _get_plan_intermediates(
    input_dir: Path,
    config: AppConfig,
    use_cache: bool,
    progress_callback: ProgressCallback | None,
    exclusions: list[Path],
) -> dict:
    input_dir = input_dir.expanduser().resolve()
    cache_key = str(input_dir)
    signature = _config_signature(config)
    if use_cache and signature:
        with _plan_cache_lock:
            cached = _plan_cache.get(cache_key)
        if cached is not None and cached[0] == signature:
            return cached[1]
    emit(progress_callback, ProgressEvent("preparing_fonts"))
    scan = scan_media_dir(input_dir, config.media, excluded_dirs=exclusions)
    fonts = prepare_fonts(input_dir, config.media, config.font, extract_archives=False, preview_archives=True)
    catalog = build_font_catalog(
        fonts.fonts,
        archives=scan.font_archives,
        media_config=config.media,
        font_config=config.font,
    )
    intermediates = {"scan": scan, "fonts": fonts, "catalog": catalog, "inspections": {}}
    with _plan_cache_lock:
        _plan_cache[cache_key] = (signature, intermediates)
        _plan_cache.move_to_end(cache_key)
        while len(_plan_cache) > _PLAN_CACHE_LIMIT:
            _plan_cache.popitem(last=False)
    return intermediates


def clear_plan_cache() -> None:
    """Drop all cached planning intermediates (e.g. when the source directory changes)."""
    with _plan_cache_lock:
        _plan_cache.clear()


def build_job_plan(
    input_dir: Path,
    config: AppConfig,
    progress_callback: ProgressCallback | None = None,
    source_track_overrides: Mapping[Path, Mapping[int, bool]] | None = None,
    plan_edits: Mapping[Path, PlanEdit] | None = None,
    use_cache: bool = True,
) -> JobReport:
    started = time.perf_counter()
    input_dir = input_dir.expanduser().resolve()
    logging.info("Planning input directory: %s", input_dir)
    exclusions: list[Path] = []
    extra = Path(config.task.extra_dir).expanduser()
    extra_path = extra if extra.is_absolute() else input_dir / extra
    if extra_path.resolve() != input_dir:
        exclusions.append(extra_path)
    if config.task.output_dir is not None:
        output_dir = config.task.output_dir
        output_path = output_dir if output_dir.is_absolute() else input_dir / output_dir
        if output_path.resolve() != input_dir:
            exclusions.append(output_path)
    intermediates = _get_plan_intermediates(input_dir, config, use_cache, progress_callback, exclusions)
    scan = intermediates["scan"]
    fonts = intermediates["fonts"]
    catalog = intermediates["catalog"]
    plan_result = build_mux_plans(
        scan,
        config,
        fonts,
        catalog,
        lambda phase: emit(progress_callback, ProgressEvent(phase)),
    )
    warnings = [
        *scan.warnings,
        *fonts.warnings,
        *fonts.errors,
        *fonts.conflicts,
        *catalog.warnings,
        *catalog.errors,
    ]
    try:
        plan_result.plans, edit_skips = apply_plan_edits(
            plan_result.plans,
            plan_edits or {},
            scan,
            config,
            fonts,
            catalog,
        )
        plan_result.skipped_files.extend(edit_skips)
        edit_track_overrides = source_track_overrides_from_edits(plan_edits or {})
    except PlanEditError as exc:
        return JobReport(
            input_dir=input_dir,
            plans=plan_result.plans,
            skipped_files=plan_result.skipped_files,
            warnings=warnings,
            error_code=exc.code,
            error=str(exc),
        )
    mkvmerge = resolve_mkvmerge_path(config)
    if config.tracks.audio_filter_enabled and not mkvmerge:
        return JobReport(
            input_dir=input_dir,
            plans=plan_result.plans,
            skipped_files=plan_result.skipped_files,
            warnings=warnings,
            error_code="MKVMERGE_REQUIRED_FOR_TRACK_FILTER",
            error="mkvmerge is required to inspect source tracks when audio filtering is enabled",
        )
    if mkvmerge:
        inspections = intermediates["inspections"]

        def inspect(video: Path) -> list:
            key = Path(video).expanduser().resolve()
            cached = inspections.get(key)
            if cached is not None:
                return cached
            result = inspect_source_tracks(key, mkvmerge)
            inspections[key] = result
            return result

        normalized_overrides = {
            path.expanduser().resolve(): dict(values)
            for path, values in (source_track_overrides or {}).items()
        }
        for path, values in edit_track_overrides.items():
            normalized_overrides.setdefault(path, {}).update(values)
        try:
            for plan in plan_result.plans:
                inspected = inspect(plan.source_video)
                if config.tracks.audio_filter_enabled and not inspected:
                    return JobReport(
                        input_dir=input_dir,
                        plans=plan_result.plans,
                        skipped_files=plan_result.skipped_files,
                        warnings=warnings,
                        error_code="SOURCE_TRACK_INSPECTION_FAILED",
                        error=f"Could not inspect source tracks: {plan.source_video}",
                    )
                plan.source_tracks = decide_source_tracks(
                    inspected,
                    config.tracks,
                    normalized_overrides.get(plan.source_video.resolve()),
                )
                plan.audio_tracks = [
                    replace(
                        track,
                        expected_track_count=sum(
                            item.type == "audio" for item in inspect(track.path)
                        ) or 1,
                    )
                    for track in plan.audio_tracks
                ]
        except TrackPolicyError as exc:
            return JobReport(
                input_dir=input_dir,
                plans=plan_result.plans,
                skipped_files=plan_result.skipped_files,
                warnings=warnings,
                error_code=exc.code,
                error=str(exc),
            )
    snapshot = create_plan_snapshot(input_dir, plan_result.plans, config, extra_inputs=scan.font_archives)
    report = JobReport(
        input_dir=input_dir, plans=plan_result.plans, skipped_files=plan_result.skipped_files,
        snapshot=snapshot, warnings=warnings,
        available_subtitles=list(scan.subtitles), available_audio=list(scan.audios),
    )
    if config.font.missing_font_action == "fail-job" and any(
        item.stage == "font" for item in plan_result.skipped_files
    ):
        report.error_code = "MISSING_REFERENCED_FONT"
        report.error = "A referenced font is missing and font.missing_font_action is fail-job"
    logging.info(
        "Planning completed",
        extra={
            "plan_id": snapshot.plan_id,
            "phase": "planning",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return report


def execute_plan_snapshot(
    snapshot: MuxPlanSnapshot,
    config: AppConfig,
    yes: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancellation_event: threading.Event | None = None,
) -> JobReport:
    started = time.perf_counter()
    cancel = cancellation_event or threading.Event()
    report = JobReport(input_dir=snapshot.input_dir, plans=snapshot.plans, snapshot=snapshot)
    if config.task.overwrite and not yes:
        report.error_code = "OVERWRITE_CONFIRMATION_REQUIRED"
        report.error = "Overwrite requires explicit confirmation"
        return report
    if requires_delete_confirmation(config) and not yes:
        report.error_code = "DELETE_CONFIRMATION_REQUIRED"
        report.error = "Delete cleanup requires explicit confirmation"
        return report
    emit(progress_callback, ProgressEvent("validating_snapshot", total=len(snapshot.plans)))
    try:
        validate_plan_snapshot(snapshot, config)
        validate_source_track_layout(snapshot, config)
    except StalePlanError as exc:
        report.error_code = exc.code
        report.error = str(exc)
        return report

    # Materialize legacy full-font attachments only after the immutable input
    # snapshot has been validated. Subset sources are additionally revalidated
    # by digest when copied into the execution workspace.
    emit(progress_callback, ProgressEvent("preparing_fonts", total=len(snapshot.plans)))
    font_result = prepare_fonts(snapshot.input_dir, config.media, config.font, extract_archives=True)
    report.warnings.extend([*font_result.warnings, *font_result.errors, *font_result.conflicts])
    missing_attachments = sorted({
        attachment.path
        for plan in snapshot.plans
        for attachment in plan.attachments
        if not attachment.path.is_file()
    }, key=str)
    if font_result.errors or missing_attachments:
        report.error_code = "FONT_PREPARATION_FAILED"
        details = [*font_result.errors, *[f"Missing planned attachment: {path}" for path in missing_attachments]]
        report.error = "; ".join(details)
        logging.error("[%s] %s", report.error_code, report.error)
        return report

    total = len(snapshot.plans)
    persistent_font_cache = FontSubsetCache(config.font_cache) if config.font_cache.enabled else None
    with SubsetWorkspace(snapshot.plan_id, persistent_cache=persistent_font_cache) as workspace:
        prepared_plans: list[PreparedMuxPlan] = []
        for index, plan in enumerate(snapshot.plans):
            if cancel.is_set():
                report.cancelled = True
                break
            if config.font.mode != "subset":
                prepared_plans.append(PreparedMuxPlan.from_original(plan))
                continue

            def preparation_progress(
                phase: str,
                total_families: int,
                completed_families: int,
                current_family: str | None,
                *,
                plan_index: int = index,
                current_file: str = plan.source_video.name,
            ) -> None:
                emit(progress_callback, ProgressEvent(
                    phase=phase,
                    total=total,
                    completed=plan_index,
                    succeeded=report.success_count,
                    failed=report.failure_count,
                    current_file=current_file,
                    total_families=total_families,
                    completed_families=completed_families,
                    current_family=current_family,
                ))

            try:
                prepared_plans.append(prepare_subset_plan(
                    plan,
                    config.font,
                    workspace,
                    cancellation_event=cancel,
                    progress_callback=preparation_progress,
                ))
            except FontPreparationError as exc:
                if cancel.is_set():
                    report.cancelled = True
                    break
                if config.font.subset_failure_action == "fail-job":
                    report.error_code = "FONT_SUBSET_FAILED"
                    report.error = str(exc)
                    logging.error("[%s] %s", report.error_code, report.error)
                    return report
                report.results.append(MuxResult(
                    plan=plan,
                    success=False,
                    output_path=plan.output_path,
                    error_code="FONT_SUBSET_FAILED",
                    error=str(exc),
                    verified=False,
                ))

        # No mux subprocess may start until every plan has either been prepared
        # successfully or converted into an explicit per-video failure.
        if not report.cancelled:
            emit(progress_callback, ProgressEvent(
                "running_mux", total, len(report.results), report.success_count, report.failure_count
            ))
            _execute_prepared_plans(
                prepared_plans,
                config,
                cancel,
                report,
                total,
                progress_callback,
            )
        if cancel.is_set():
            report.cancelled = True
    emit(progress_callback, ProgressEvent(
        "cleaning", total, len(report.results), report.success_count, report.failure_count
    ))
    report.cleanup_results = cleanup_successful_results(report.results, config, yes=yes)
    successful_directories = [
        result.output_path.parent for result in report.results if result.success and result.verified
    ]
    if config.plex.enabled and not report.cancelled and successful_directories:
        try:
            plex_results = refresh_paths(config.plex, successful_directories)
            report.post_actions.extend(
                {"type": "plex_refresh", **result.__dict__} for result in plex_results
            )
            report.warnings.extend(
                f"Plex refresh failed for {result.local_path}: {result.error or result.status_code}"
                for result in plex_results if not result.success
            )
        except PlexIntegrationError as exc:
            report.post_actions.append({"type": "plex_refresh", "success": False, "error": str(exc)})
            report.warnings.append(f"Plex refresh was not completed: {exc}")
    emit(progress_callback, ProgressEvent(
        "cancelled" if report.cancelled else "completed",
        total, len(report.results), report.success_count, report.failure_count,
    ))
    logging.info(
        "Plan execution completed",
        extra={
            "plan_id": snapshot.plan_id,
            "phase": "cancelled" if report.cancelled else "completed",
            "error_code": report.error_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return report


def _execute_prepared_plans(
    prepared_plans: list[PreparedMuxPlan],
    config: AppConfig,
    cancel: threading.Event,
    report: JobReport,
    total: int,
    progress_callback: ProgressCallback | None,
) -> None:
    max_workers = config.concurrency.max_parallel_mux_jobs
    if max_workers == 1:
        for prepared in prepared_plans:
            if cancel.is_set():
                report.cancelled = True
                break
            plan = prepared.original_plan
            emit(progress_callback, ProgressEvent(
                "running_mux", total, len(report.results), report.success_count,
                report.failure_count, plan.source_video.name,
            ))
            result = _execute_one_prepared(prepared, config, cancel)
            emit(progress_callback, ProgressEvent(
                "verifying_outputs", total, len(report.results), report.success_count,
                report.failure_count, plan.source_video.name,
            ))
            report.results.append(result)
            logging.info(
                "Mux result source=%s success=%s verified=%s code=%s",
                plan.source_video.name,
                result.success,
                result.verified,
                result.error_code,
            )
        return

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="plexmuxy-mux") as executor:
        future_map = {
            executor.submit(_execute_one_prepared, prepared, config, cancel): prepared.original_plan
            for prepared in prepared_plans
        }
        for future in as_completed(future_map):
            plan = future_map[future]
            emit(progress_callback, ProgressEvent(
                "verifying_outputs", total, len(report.results), report.success_count,
                report.failure_count, plan.source_video.name,
            ))
            report.results.append(future.result())
            if cancel.is_set():
                report.cancelled = True


def _execute_one_prepared(
    prepared: PreparedMuxPlan,
    config: AppConfig,
    cancel: threading.Event,
) -> MuxResult:
    if (
        prepared.subtitle_tracks == prepared.original_plan.subtitle_tracks
        and prepared.attachments == prepared.original_plan.attachments
        and not prepared.generated_files
        and not prepared.subset_warnings
    ):
        return execute_mux_plan(prepared.original_plan, config, cancel)
    return execute_prepared_mux_plan(prepared, config, cancel)


def run_mux_job(
    input_dir: Path,
    config: AppConfig,
    dry_run: bool = False,
    yes: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancellation_event: threading.Event | None = None,
    source_track_overrides: Mapping[Path, Mapping[int, bool]] | None = None,
    plan_edits: Mapping[Path, PlanEdit] | None = None,
    use_cache: bool = True,
) -> JobReport:
    emit(progress_callback, ProgressEvent("planning"))
    report = build_job_plan(
        input_dir,
        config,
        progress_callback=progress_callback,
        source_track_overrides=source_track_overrides,
        plan_edits=plan_edits,
        use_cache=use_cache,
    )
    if dry_run or report.snapshot is None or report.error is not None:
        return report
    executed = execute_plan_snapshot(
        report.snapshot, config, yes=yes, progress_callback=progress_callback,
        cancellation_event=cancellation_event,
    )
    executed.skipped_files = report.skipped_files
    executed.warnings = [*report.warnings, *executed.warnings]
    return executed


def emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - observers cannot break core execution.
            logging.exception("Progress callback failed")


def requires_delete_confirmation(config: AppConfig) -> bool:
    return (
        config.task.cleanup == "delete"
        or config.task.delete_original_video
        or config.task.delete_original_audio
        or config.task.delete_subtitle
        or config.font.delete_fonts_after_mux
    )


def validate_source_track_layout(snapshot: MuxPlanSnapshot, config: AppConfig) -> None:
    """Reject a plan when the source container track layout changed after review."""

    plans = [plan for plan in snapshot.plans if plan.source_tracks]
    if not plans:
        return
    mkvmerge = resolve_mkvmerge_path(config)
    if mkvmerge is None:
        raise StalePlanError("mkvmerge is unavailable for source track revalidation")
    for plan in plans:
        current = inspect_source_tracks(plan.source_video, mkvmerge)
        expected_fingerprints = [source_track_layout_fingerprint(track) for track in plan.source_tracks]
        current_fingerprints = [source_track_layout_fingerprint(track) for track in current]
        if expected_fingerprints != current_fingerprints:
            raise StalePlanError(f"Source track layout changed: {plan.source_video}")


def source_track_layout_fingerprint(track) -> tuple:
    return (
        track.id,
        track.type,
        track.codec,
        track.language,
        track.title,
        track.default_track,
        track.forced_track,
        track.channels,
    )
