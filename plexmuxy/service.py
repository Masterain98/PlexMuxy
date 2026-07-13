from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .cleanup import cleanup_successful_results
from .errors import StalePlanError
from .font import prepare_fonts
from .font_catalog import build_font_catalog
from .font_prepare import FontPreparationError, SubsetWorkspace, prepare_subset_plan
from .models import AppConfig, JobReport, MuxPlanSnapshot, MuxResult, PreparedMuxPlan, ProgressEvent
from .muxer import execute_mux_plan, execute_prepared_mux_plan, inspect_source_tracks, resolve_mkvmerge_path
from .planner import build_mux_plans
from .scanner import scan_media_dir
from .snapshot import create_plan_snapshot, validate_plan_snapshot

ProgressCallback = Callable[[ProgressEvent], None]


def build_job_plan(
    input_dir: Path,
    config: AppConfig,
    progress_callback: ProgressCallback | None = None,
) -> JobReport:
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
    emit(progress_callback, ProgressEvent("preparing_fonts"))
    fonts = prepare_fonts(input_dir, config.media, config.font, extract_archives=False, preview_archives=True)
    catalog = build_font_catalog(
        fonts.fonts,
        archives=scan.font_archives,
        media_config=config.media,
        font_config=config.font,
    )
    plan_result = build_mux_plans(
        scan,
        config,
        fonts,
        catalog,
        lambda phase: emit(progress_callback, ProgressEvent(phase)),
    )
    mkvmerge = resolve_mkvmerge_path(config)
    if mkvmerge:
        for plan in plan_result.plans:
            plan.source_tracks = inspect_source_tracks(plan.source_video, mkvmerge)
    snapshot = create_plan_snapshot(input_dir, plan_result.plans, config, extra_inputs=scan.font_archives)
    warnings = [
        *scan.warnings,
        *fonts.warnings,
        *fonts.errors,
        *fonts.conflicts,
        *catalog.warnings,
        *catalog.errors,
    ]
    report = JobReport(
        input_dir=input_dir, plans=plan_result.plans, skipped_files=plan_result.skipped_files,
        snapshot=snapshot, warnings=warnings,
    )
    if config.font.missing_font_action == "fail-job" and any(
        item.stage == "font" for item in plan_result.skipped_files
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
    emit(progress_callback, ProgressEvent("validating_snapshot", total=len(snapshot.plans)))
    try:
        validate_plan_snapshot(snapshot, config)
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
    with SubsetWorkspace(snapshot.plan_id) as workspace:
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
    emit(progress_callback, ProgressEvent(
        "cancelled" if report.cancelled else "completed",
        total, len(report.results), report.success_count, report.failure_count,
    ))
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
) -> JobReport:
    emit(progress_callback, ProgressEvent("planning"))
    report = build_job_plan(input_dir, config, progress_callback=progress_callback)
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
