from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, default_config, default_config_dict, load_config, resolve_config_path, write_default_config
from .logging_utils import configure_logging
from .models import AppConfig
from .overrides import apply_job_overrides, overrides_from_namespace
from .report import format_job_report
from .service import run_mux_job


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
        parser.print_help()
        raise SystemExit(0)
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

    subparsers.add_parser("gui", help="Start the optional desktop GUI")
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
        from plexmuxy_gui.app import main as gui_main
    except ImportError as exc:
        print(f"GUI mode requires optional GUI dependencies: {exc}", file=sys.stderr)
        print('Install with `pip install -e ".[gui]"` or use `plexmuxy mux <directory>`.', file=sys.stderr)
        return 2

    try:
        gui_main()
    except RuntimeError as exc:
        print(f"GUI mode is unavailable in this environment: {exc}", file=sys.stderr)
        return 2
    return 0


def run_job_command(args: argparse.Namespace) -> int:
    config = load_cli_config(args)
    config = apply_job_overrides(config, overrides_from_namespace(args))
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


if __name__ == "__main__":
    main()
