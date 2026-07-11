from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .cleanup import cleanup_successful_results
from .errors import StalePlanError
from .font import prepare_fonts
from .models import AppConfig, JobReport, MuxPlanSnapshot, ProgressEvent
from .muxer import execute_mux_plan, inspect_source_tracks, resolve_mkvmerge_path
from .planner import build_mux_plans
from .scanner import scan_media_dir
from .snapshot import create_plan_snapshot, validate_plan_snapshot

ProgressCallback = Callable[[ProgressEvent], None]


def build_job_plan(input_dir: Path, config: AppConfig) -> JobReport:
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
    scan = scan_media_dir(input_dir, config.media, excluded_dirs=exclusions)
    fonts = prepare_fonts(input_dir, config.media, config.font, extract_archives=False, preview_archives=True)
    plan_result = build_mux_plans(scan, config, fonts)
    mkvmerge = resolve_mkvmerge_path(config)
    if mkvmerge:
        for plan in plan_result.plans:
            plan.source_tracks = inspect_source_tracks(plan.source_video, mkvmerge)
    snapshot = create_plan_snapshot(input_dir, plan_result.plans, config, extra_inputs=scan.font_archives)
    warnings = [*scan.warnings, *fonts.warnings, *fonts.errors, *fonts.conflicts]
    report = JobReport(
        input_dir=input_dir, plans=plan_result.plans, skipped_files=plan_result.skipped_files,
        snapshot=snapshot, warnings=warnings,
    )
    if config.font.missing_font_action == "fail-job" and any(
        item.reason == "missing_referenced_font" for item in plan_result.skipped_files
    ):
        report.error_code = "MISSING_REFERENCED_FONT"
        report.error = "A referenced font is missing and font.missing_font_action is fail-job"
    return report


def execute_plan_snapshot(
    snapshot: MuxPlanSnapshot,
    config: AppConfig,
    yes: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancellation_event: threading.Event | None = None,
) -> JobReport:
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
    try:
        validate_plan_snapshot(snapshot, config)
    except StalePlanError as exc:
        report.error_code = exc.code
        report.error = str(exc)
        return report

    # Materialize archive-backed fonts after the immutable input snapshot has
    # been validated and before any mux subprocess starts.
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
    emit(progress_callback, ProgressEvent("running", total=total))
    max_workers = config.concurrency.max_parallel_mux_jobs
    if max_workers == 1:
        for index, plan in enumerate(snapshot.plans):
            if cancel.is_set():
                report.cancelled = True
                break
            emit(progress_callback, ProgressEvent(
                "running", total, index, report.success_count, report.failure_count, plan.source_video.name
            ))
            report.results.append(execute_mux_plan(plan, config, cancel))
            logging.info(
                "Mux result source=%s success=%s verified=%s code=%s",
                plan.source_video.name,
                report.results[-1].success,
                report.results[-1].verified,
                report.results[-1].error_code,
            )
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="plexmuxy-mux") as executor:
            future_map = {
                executor.submit(execute_mux_plan, plan, config, cancel): plan for plan in snapshot.plans
            }
            for future in as_completed(future_map):
                report.results.append(future.result())
                emit(progress_callback, ProgressEvent(
                    "running", total, len(report.results), report.success_count, report.failure_count,
                    future_map[future].source_video.name,
                ))
                if cancel.is_set():
                    report.cancelled = True
    if cancel.is_set():
        report.cancelled = True
    emit(progress_callback, ProgressEvent(
        "cleaning", total, len(report.results), report.success_count, report.failure_count
    ))
    report.cleanup_results = cleanup_successful_results(report.results, config, yes=yes)
    emit(progress_callback, ProgressEvent(
        "cancelled" if report.cancelled else "completed",
        total, len(report.results), report.success_count, report.failure_count,
    ))
    return report


def run_mux_job(
    input_dir: Path,
    config: AppConfig,
    dry_run: bool = False,
    yes: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancellation_event: threading.Event | None = None,
) -> JobReport:
    emit(progress_callback, ProgressEvent("planning"))
    report = build_job_plan(input_dir, config)
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
