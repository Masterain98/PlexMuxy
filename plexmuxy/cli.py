from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

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
from .i18n import Messages, requested_language
from .logging_utils import configure_logging
from .models import AppConfig
from .overrides import apply_job_overrides, overrides_from_namespace
from .report import format_job_report
from .serialization import job_report_to_dict, snapshot_from_dict, snapshot_to_dict
from .service import execute_plan_snapshot, run_mux_job
from .update_check import check_for_updates

GUI_EXTRA_MESSAGE = 'PlexMuxy GUI requires optional dependencies. Install with `pip install "plexmuxy[gui]"`.'


class StableArgumentParser(argparse.ArgumentParser):
    """Preserve the machine-readable error contract for parser failures."""

    _active_argv: list[str] = []
    _active_language: str = "en"

    def parse_args(  # type: ignore[override]
        self,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        if self.prog == "plexmuxy":
            raw = list(sys.argv[1:] if args is None else args)
            type(self)._active_argv = raw
            type(self)._active_language = requested_language(raw)
        return super().parse_args(args, namespace)

    def error(self, message: str) -> NoReturn:
        if "--output-format" in self._active_argv:
            index = self._active_argv.index("--output-format")
            json_requested = index + 1 < len(self._active_argv) and self._active_argv[index + 1] == "json"
        else:
            json_requested = False
        if json_requested:
            localized = Messages(self._active_language).get(
                "message.error", error_code="INVALID_ARGUMENT", message=message
            )
            print(json.dumps({
                "status": "error",
                "error": {
                    "error_code": "INVALID_ARGUMENT",
                    "technical_message": message,
                    "localized_message": localized,
                    "details": {"parser": self.prog},
                },
            }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            raise SystemExit(2)
        super().error(message)


def main(argv: list[str] | None = None) -> None:
    configure_console_streams()
    raw_argv = sys.argv[1:] if argv is None else argv
    args = parse_args(raw_argv)
    try:
        exit_code = dispatch(args)
    except (ConfigError, PlexMuxyError, ValueError) as exc:
        emit_error(args, getattr(exc, "code", "INVALID_ARGUMENT"), str(exc), exc)
        exit_code = 2
    except (FileNotFoundError, NotADirectoryError) as exc:
        emit_error(args, "INPUT_NOT_FOUND", str(exc), exc)
        exit_code = 2
    raise SystemExit(exit_code)


def configure_console_streams() -> None:
    """Avoid crashes when config/file names exceed the active console code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = sys.argv[1:] if argv is None else argv
    language = requested_language(argv)
    parser = build_parser(language)
    if not argv:
        parser.print_help()
        raise SystemExit(0)
    args = parser.parse_args(argv)
    args._messages = Messages(args.language)
    return args


def build_parser(language: str = "en") -> argparse.ArgumentParser:
    messages = Messages(language)
    parser = StableArgumentParser(prog="plexmuxy", description=messages.get("cli.description"))
    parser.add_argument("--config", help=messages.get("cli.config"))
    parser.add_argument("--language", choices=["system", "en", "zh-CN"], default=language, help=messages.get("cli.language"))
    parser.add_argument("--output-format", choices=["human", "json"], default="human", help=messages.get("cli.outputFormat"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init-config", help=messages.get("cli.init"))
    init_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("show-config", help=messages.get("cli.show"))
    migrate_parser = subparsers.add_parser("migrate-config", help=messages.get("cli.migrate"))
    migrate_parser.add_argument("--source")
    migrate_parser.add_argument("--target")
    plan_parser = subparsers.add_parser("plan", help=messages.get("cli.plan"))
    add_job_arguments(plan_parser, dry_run_default=True, messages=messages)
    plan_parser.add_argument("--json", dest="json_path", help="Save the executable plan snapshot as JSON")
    mux_parser = subparsers.add_parser("mux", help=messages.get("cli.mux"))
    add_job_arguments(mux_parser, dry_run_default=False, messages=messages)
    execute_parser = subparsers.add_parser("execute-plan", help=messages.get("cli.execute"))
    execute_parser.add_argument("plan_file")
    execute_parser.add_argument("--yes", action="store_true")
    execute_parser.add_argument("--verbose", action="store_true")
    execute_parser.add_argument("--json-log", action="store_true")
    diagnostics_parser = subparsers.add_parser("diagnostics", help=messages.get("cli.diagnostics"))
    diagnostics_parser.add_argument("--output", required=True)
    subparsers.add_parser("gui", help=messages.get("cli.gui"))
    update_parser = subparsers.add_parser("check-updates", help=messages.get("cli.checkUpdates"))
    update_parser.add_argument("--force", action="store_true")
    return parser


def add_job_arguments(
    parser: argparse.ArgumentParser,
    dry_run_default: bool = False,
    messages: Messages | None = None,
) -> None:
    messages = messages or Messages("en")
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
    parser.add_argument("--json-log", action="store_true", help=messages.get("cli.jsonLog"))


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
        path = export_diagnostics(config, Path(args.output))
        emit_output(args, {"command": "diagnostics", "status": "ok", "path": str(path)}, msg(args, "message.diagnostics", path=path))
        return 0
    if args.command == "gui":
        return run_gui(args)
    if args.command == "check-updates":
        return check_updates_command(args)
    if args.command in {"plan", "mux"}:
        return run_job_command(args)
    raise AssertionError(f"Unknown command: {args.command}")


def init_config(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    if path.exists() and not args.force:
        emit_output(args, {"command": "init-config", "status": "exists", "path": str(path)}, msg(args, "message.configExists", path=path))
        return 1
    written = write_default_config(path)
    emit_output(args, {"command": "init-config", "status": "ok", "path": str(written)}, msg(args, "message.configWritten", path=written))
    return 0


def show_config(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else default_config_dict()
    human = msg(args, "message.configPath" if path.exists() else "message.configMissing", path=path)
    human += "\n" + json.dumps(data, indent=2, ensure_ascii=False)
    emit_output(args, {"command": "show-config", "status": "ok", "path": str(path), "exists": path.exists(), "config": data}, human)
    return 0


def migrate_config_command(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser() if args.source else resolve_config_path(args.config)
    target, backup = migrate_config(source, args.target)
    lines = [msg(args, "message.migrated", path=target)]
    if backup:
        lines.append(msg(args, "message.backup", path=backup))
    emit_output(args, {"command": "migrate-config", "status": "ok", "path": str(target), "backup": str(backup) if backup else None}, "\n".join(lines))
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
        if args.output_format == "human":
            print(msg(args, "message.planSaved", path=target))
    emit_output(args, {"command": args.command, "status": "ok" if report.error is None else "error", "report": job_report_to_dict(report)}, format_job_report(report, dry_run=args.dry_run, translate=args._messages.get))
    return 0 if (args.dry_run and report.error is None) or (report.failure_count == 0 and report.error is None) else 1


def execute_plan_command(args: argparse.Namespace) -> int:
    configure_logging(verbose=args.verbose, json_log=args.json_log)
    data = json.loads(Path(args.plan_file).expanduser().read_text(encoding="utf-8"))
    snapshot = snapshot_from_dict(data)
    config = load_config(args.config, create_if_missing=False) if args.config else parse_config(snapshot.config)
    report = execute_plan_snapshot(snapshot, config, yes=args.yes)
    emit_output(args, {"command": "execute-plan", "status": "ok" if report.error is None else "error", "report": job_report_to_dict(report)}, format_job_report(report, translate=args._messages.get))
    return 0 if report.failure_count == 0 and report.error is None else 1


def run_gui(args: argparse.Namespace | None = None) -> int:
    try:
        from plexmuxy_gui.app import start
        start()
    except ImportError as exc:
        if exc.name not in {None, "webview"} and "webview" not in str(exc).casefold():
            raise
        print(msg(args, "message.guiUnavailable", message=GUI_EXTRA_MESSAGE, error=exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(msg(args, "message.guiUnavailable", message=GUI_EXTRA_MESSAGE, error=exc), file=sys.stderr)
        return 2
    return 0


def load_cli_config(args: argparse.Namespace) -> AppConfig:
    path = resolve_config_path(getattr(args, "config", None))
    if path.exists():
        return load_config(path, create_if_missing=False)
    config = default_config()
    config.source_path = path
    if getattr(args, "output_format", "human") == "human":
        print(msg(args, "message.defaultConfig", path=path))
    return config


def check_updates_command(args: argparse.Namespace) -> int:
    from . import __version__

    config = load_cli_config(args)
    result = check_for_updates(__version__, config.updates, force=bool(args.force))
    if not result.checked:
        human = msg(args, "message.updateDisabled")
    elif result.error:
        human = msg(args, "message.updateFailed", error=result.error)
    elif result.update_available:
        human = msg(args, "message.updateAvailable", latest=result.latest_version, url=result.release_url or "")
    else:
        human = msg(args, "message.updateCurrent", current=result.current_version)
    emit_output(args, {"command": "check-updates", "status": "ok", "update": asdict(result)}, human)
    return 0


def msg(args: argparse.Namespace | None, key: str, **values) -> str:
    messages = getattr(args, "_messages", None)
    return (messages if isinstance(messages, Messages) else Messages("en")).get(key, **values)


def emit_output(args: argparse.Namespace, payload: dict, human: str) -> None:
    if getattr(args, "output_format", "human") == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(human)


def emit_error(args: argparse.Namespace, error_code: str, technical_message: str, exc: Exception) -> None:
    localized = msg(args, "message.error", error_code=error_code, message=technical_message)
    if getattr(args, "output_format", "human") == "json":
        print(json.dumps({
            "status": "error",
            "error": {
                "error_code": error_code,
                "technical_message": technical_message,
                "localized_message": localized,
                "details": {"exception_type": type(exc).__name__},
            },
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    else:
        print(localized, file=sys.stderr)


if __name__ == "__main__":
    main()
