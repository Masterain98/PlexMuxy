from __future__ import annotations

import logging
from pathlib import Path

from .cleanup import cleanup_successful_results
from .font import prepare_fonts
from .models import AppConfig, JobReport
from .muxer import execute_mux_plan
from .planner import build_mux_plans
from .scanner import scan_media_dir


def run_mux_job(input_dir: Path, config: AppConfig, dry_run: bool = False, yes: bool = False) -> JobReport:
    input_dir = input_dir.expanduser().resolve()
    logging.info("Using input directory: %s", input_dir)

    scan = scan_media_dir(input_dir, config.media)
    font_result = prepare_fonts(
        input_dir,
        config.media,
        config.font,
        extract_archives=not dry_run,
        preview_archives=dry_run,
    )
    for error in font_result.errors:
        logging.error("Font preparation failed: %s", error)

    plan_result = build_mux_plans(scan, config, font_result)
    report = JobReport(
        input_dir=input_dir,
        plans=plan_result.plans,
        skipped_files=plan_result.skipped_files,
    )
    if dry_run:
        return report

    report.results = [execute_mux_plan(plan, config) for plan in report.plans]
    report.cleanup_results = cleanup_successful_results(report.results, config, yes=yes)
    return report
