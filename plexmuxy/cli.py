from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import (
    ConfigError,
    default_config,
    default_config_dict,
    load_config,
    migrate_config,
    parse_config,
    resolve_config_path,
    write_default_config,
)
from .diagnostics import export_diagnostics
from .errors import PlexMuxyError
from .logging_utils import configure_logging
from .models import AppConfig
from .overrides import apply_job_overrides, overrides_from_namespace
from .report import format_job_report
from .serialization import snapshot_from_dict, snapshot_to_dict
from .service import execute_plan_snapshot, run_mux_job

GUI_EXTRA_MESSAGE = 'PlexMuxy GUI requires optional dependencies. Install with `pip install "plexmuxy[gui]"`.'


def main(argv: list[str] | None = None) -> None:
    configure_console_streams()
    args = parse_args(argv)
    try:
        exit_code = dispatch(args)
    except (ConfigError, PlexMuxyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        exit_code = 2
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(str(exc), file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)


def configure_console_streams() -> None:
    """Avoid crashes when config/file names exceed the active console code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        raise SystemExit(0)
    return parser.parse_args(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plexmuxy", description="Safely plan and batch mux media for Plex.")
    parser.add_argument("--config", help="Path to config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init-config", help="Create a default config file")
    init_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("show-config", help="Print the active config path and JSON")
    migrate_parser = subparsers.add_parser("migrate-config", help="Persist a legacy config in the current format")
    migrate_parser.add_argument("--source")
    migrate_parser.add_argument("--target")
    plan_parser = subparsers.add_parser("plan", help="Generate an immutable dry-run plan")
    add_job_arguments(plan_parser, dry_run_default=True)
    plan_parser.add_argument("--json", dest="json_path", help="Save the executable plan snapshot as JSON")
    mux_parser = subparsers.add_parser("mux", help="Plan and run mux jobs")
    add_job_arguments(mux_parser, dry_run_default=False)
    execute_parser = subparsers.add_parser("execute-plan", help="Execute a saved plan after stale-input checks")
    execute_parser.add_argument("plan_file")
    execute_parser.add_argument("--yes", action="store_true")
    execute_parser.add_argument("--verbose", action="store_true")
    execute_parser.add_argument("--json-log", action="store_true")
    diagnostics_parser = subparsers.add_parser("diagnostics", help="Export a privacy-conscious diagnostic archive")
    diagnostics_parser.add_argument("--output", required=True)
    subparsers.add_parser("gui", help="Start the optional desktop GUI")
    return parser


def add_job_arguments(parser: argparse.ArgumentParser, dry_run_default: bool = False) -> None:
    parser.add_argument("input_dir")
    parser.add_argument("--dry-run", action="store_true", default=dry_run_default)
    parser.add_argument("--cleanup", choices=["none", "move", "delete"])
    parser.add_argument("--extra-dir")
    parser.add_argument("--output-suffix")
    parser.add_argument("--output-dir")
    parser.add_argument("--name-strategy", choices=["suffix", "same-name", "template"])
    parser.add_argument("--name-template")
    parser.add_argument("--font-mode", choices=["all", "referenced", "subset"])
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json-log", action="store_true", help="Also write a structured JSONL task log")


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "init-config":
        return init_config(args)
    if args.command == "show-config":
        return show_config(args)
    if args.command == "migrate-config":
        return migrate_config_command(args)
    if args.command == "execute-plan":
        return execute_plan_command(args)
    if args.command == "diagnostics":
        config = load_cli_config(args)
        print(f"Diagnostics written to: {export_diagnostics(config, Path(args.output))}")
        return 0
    if args.command == "gui":
        return run_gui(args)
    if args.command in {"plan", "mux"}:
        return run_job_command(args)
    raise AssertionError(f"Unknown command: {args.command}")


def init_config(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    if path.exists() and not args.force:
        print(f"Config already exists: {path}\nUse --force to overwrite it.")
        return 1
    print(f"Default config written to: {write_default_config(path)}")
    return 0


def show_config(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    print(f"Config: {path}" if path.exists() else f"Config does not exist yet: {path}")
    print(path.read_text(encoding="utf-8") if path.exists() else json.dumps(default_config_dict(), indent=2, ensure_ascii=False))
    return 0


def migrate_config_command(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser() if args.source else resolve_config_path(args.config)
    target, backup = migrate_config(source, args.target)
    print(f"Migrated config written to: {target}")
    if backup:
        print(f"Backup: {backup}")
    return 0


def run_job_command(args: argparse.Namespace) -> int:
    config = apply_job_overrides(load_cli_config(args), overrides_from_namespace(args))
    configure_logging(verbose=args.verbose, json_log=args.json_log)
    report = run_mux_job(Path(args.input_dir), config, dry_run=args.dry_run, yes=args.yes)
    if getattr(args, "json_path", None):
        if report.snapshot is None:
            raise ValueError("No plan snapshot was generated")
        target = Path(args.json_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(snapshot_to_dict(report.snapshot), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Plan saved to: {target}")
    print(format_job_report(report, dry_run=args.dry_run))
    return 0 if args.dry_run or (report.failure_count == 0 and report.error is None) else 1


def execute_plan_command(args: argparse.Namespace) -> int:
    configure_logging(verbose=args.verbose, json_log=args.json_log)
    data = json.loads(Path(args.plan_file).expanduser().read_text(encoding="utf-8"))
    snapshot = snapshot_from_dict(data)
    config = load_config(args.config, create_if_missing=False) if args.config else parse_config(snapshot.config)
    report = execute_plan_snapshot(snapshot, config, yes=args.yes)
    print(format_job_report(report))
    return 0 if report.failure_count == 0 and report.error is None else 1


def run_gui(args: argparse.Namespace | None = None) -> int:
    try:
        from plexmuxy_gui.app import start
        start()
    except ImportError as exc:
        if exc.name not in {None, "webview"} and "webview" not in str(exc).casefold():
            raise
        print(f"GUI mode is unavailable: {GUI_EXTRA_MESSAGE} ({exc})", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"GUI mode is unavailable: {GUI_EXTRA_MESSAGE} ({exc})", file=sys.stderr)
        return 2
    return 0


def load_cli_config(args: argparse.Namespace) -> AppConfig:
    path = resolve_config_path(getattr(args, "config", None))
    if path.exists():
        return load_config(path, create_if_missing=False)
    config = default_config()
    config.source_path = path
    print(f"Config not found; using built-in defaults. Run `plexmuxy init-config` to create: {path}")
    return config


if __name__ == "__main__":
    main()
