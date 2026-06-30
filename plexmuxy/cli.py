from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

from .cleanup import cleanup_successful_results
from .config import ConfigError, default_config, default_config_dict, load_config, resolve_config_path, write_default_config
from .font import prepare_fonts
from .logging_utils import configure_logging
from .models import AppConfig, JobReport
from .muxer import execute_mux_plan
from .planner import build_mux_plans
from .report import format_job_report
from .scanner import scan_media_dir


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        exit_code = dispatch(args)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        exit_code = 2
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(str(exc), file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["gui"]
    return parser.parse_args(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plexmuxy", description="Batch mux media, subtitles, audio, and fonts.")
    parser.add_argument("--config", help="Path to config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config", help="Create a default config file")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config file")

    subparsers.add_parser("show-config", help="Print the active config path and JSON")

    plan_parser = subparsers.add_parser("plan", help="Generate a dry-run mux plan")
    add_job_arguments(plan_parser, dry_run_default=True)

    mux_parser = subparsers.add_parser("mux", help="Run mux jobs")
    add_job_arguments(mux_parser, dry_run_default=False)

    gui_parser = subparsers.add_parser("gui", help="Choose a directory with a native folder picker")
    add_job_arguments(gui_parser, include_input=False, dry_run_default=False)
    return parser


def add_job_arguments(
    parser: argparse.ArgumentParser,
    include_input: bool = True,
    dry_run_default: bool = False,
) -> None:
    if include_input:
        parser.add_argument("input_dir", help="Directory containing media files")
    parser.add_argument("--dry-run", action="store_true", default=dry_run_default, help="Only generate and print a plan")
    parser.add_argument("--cleanup", choices=["none", "move", "delete"], help="Override cleanup policy")
    parser.add_argument("--extra-dir", help="Directory used by move cleanup")
    parser.add_argument("--output-suffix", help="Suffix appended to output files")
    parser.add_argument("--output-dir", help="Directory for output files")
    parser.add_argument("--name-strategy", choices=["suffix", "same-name", "template"], help="Output naming strategy")
    parser.add_argument("--name-template", help="Template used when --name-strategy template is selected")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing output files")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive cleanup actions")
    parser.add_argument("--verbose", action="store_true", help="Write debug logs")


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "init-config":
        return init_config(args)
    if args.command == "show-config":
        return show_config(args)
    if args.command == "gui":
        return run_gui(args)
    if args.command in {"plan", "mux"}:
        return run_job_command(args)
    raise AssertionError(f"Unknown command: {args.command}")


def init_config(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    if path.exists() and not args.force:
        print(f"Config already exists: {path}")
        print("Use --force to overwrite it.")
        return 1
    created = write_default_config(path)
    print(f"Default config written to: {created}")
    return 0


def show_config(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        print(f"Config does not exist yet: {config_path}")
        print(json.dumps(default_config_dict(), indent=2, ensure_ascii=False))
        return 0
    print(f"Config: {config_path}")
    print(config_path.read_text(encoding="utf-8"))
    return 0


def run_gui(args: argparse.Namespace) -> int:
    try:
        from tkinter import TclError, filedialog
    except ImportError as exc:
        print(f"GUI mode is unavailable in this environment: {exc}", file=sys.stderr)
        print("Use `plexmuxy mux <directory>` or `plexmuxy plan <directory>` instead.", file=sys.stderr)
        return 2

    try:
        folder_selected = filedialog.askdirectory()
    except (OSError, TclError) as exc:
        print(f"GUI mode is unavailable in this environment: {exc}", file=sys.stderr)
        print("Use `plexmuxy mux <directory>` or `plexmuxy plan <directory>` instead.", file=sys.stderr)
        return 2
    if not folder_selected:
        print("No directory selected.")
        return 1
    args.input_dir = folder_selected
    return run_job_command(args)


def run_job_command(args: argparse.Namespace) -> int:
    config = load_cli_config(args)
    config = apply_job_overrides(config, args)
    configure_logging(verbose=args.verbose)
    report = run_mux_job(Path(args.input_dir), config, dry_run=args.dry_run, yes=args.yes)
    print(format_job_report(report, dry_run=args.dry_run))
    if args.dry_run:
        return 0
    return 0 if report.failure_count == 0 else 1


def load_cli_config(args: argparse.Namespace) -> AppConfig:
    path = resolve_config_path(args.config)
    if path.exists():
        return load_config(path, create_if_missing=False)
    config = default_config()
    config.source_path = path
    print(f"Config not found; using built-in defaults. Run `plexmuxy init-config` to create: {path}")
    return config


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


def apply_job_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    updated = copy.deepcopy(config)
    if getattr(args, "cleanup", None) is not None:
        updated.task.cleanup = args.cleanup
        updated.task.cleanup_overridden = True
    if getattr(args, "extra_dir", None):
        updated.task.extra_dir = args.extra_dir
    if getattr(args, "output_suffix", None) is not None:
        updated.task.output_suffix = args.output_suffix or "_Plex"
    if getattr(args, "output_dir", None):
        updated.task.output_dir = Path(args.output_dir).expanduser()
    if getattr(args, "name_strategy", None):
        updated.task.name_strategy = args.name_strategy
    if getattr(args, "name_template", None):
        updated.task.name_template = args.name_template
    if getattr(args, "overwrite", False):
        updated.task.overwrite = True
    return updated


if __name__ == "__main__":
    main()
