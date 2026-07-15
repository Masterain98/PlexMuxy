import builtins
import json
import sys
from argparse import Namespace

import pytest

from plexmuxy.cli import build_parser, parse_args, run_gui
from plexmuxy.i18n import Messages
from plexmuxy.models import JobReport
from plexmuxy.report import format_job_report


def test_job_commands_accept_font_mode_override():
    args = build_parser().parse_args(["plan", "media", "--font-mode", "subset"])

    assert args.font_mode == "subset"


def test_cli_help_is_localized_and_json_contract_is_language_independent(capsys):
    with pytest.raises(SystemExit):
        build_parser("zh-CN").parse_args(["--help"])
    assert "按照 Plex 的识别偏好封装" in capsys.readouterr().out

    en = parse_args(["--language", "en", "--output-format", "json", "show-config"])
    zh = parse_args(["--language", "zh-CN", "--output-format", "json", "show-config"])
    assert vars(en).keys() == vars(zh).keys()
    assert en.output_format == zh.output_format == "json"


def test_cli_parser_errors_use_stable_localized_json(capsys):
    with pytest.raises(SystemExit) as exc_info:
        build_parser("zh-CN").parse_args([
            "--language", "zh-CN", "--output-format", "json", "plan", "media", "--cleanup", "invalid"
        ])

    payload = json.loads(capsys.readouterr().err)
    assert exc_info.value.code == 2
    assert payload["status"] == "error"
    assert payload["error"]["error_code"] == "INVALID_ARGUMENT"
    assert "invalid choice" in payload["error"]["technical_message"]
    assert payload["error"]["localized_message"].startswith("错误：")
    assert set(payload["error"]) == {
        "error_code", "technical_message", "localized_message", "details"
    }


def test_cli_human_report_labels_are_localized_without_translating_paths(tmp_path):
    report = format_job_report(JobReport(tmp_path), dry_run=True, translate=Messages("zh-CN").get)
    assert "试运行完成" in report
    assert "输入目录" in report
    assert str(tmp_path) in report


def test_run_gui_reports_clean_error_when_pywebview_is_unavailable(monkeypatch, capsys):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "webview":
            raise ImportError("no webview")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    exit_code = run_gui(Namespace())

    assert exit_code == 2
    assert "PlexMuxy GUI requires optional dependencies" in capsys.readouterr().err


def test_plexmuxy_gui_entrypoint_exits_cleanly_when_pywebview_is_unavailable(monkeypatch, capsys):
    from plexmuxy_gui.app import main

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "webview":
            raise ImportError("no webview", name="webview")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "PlexMuxy GUI requires optional dependencies" in capsys.readouterr().err


def test_run_gui_reraises_non_webview_import_errors(monkeypatch):
    sys.modules.pop("plexmuxy_gui.app", None)
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "plexmuxy_gui.app":
            raise ImportError("broken transitive import", name="broken_dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError, match="broken transitive import"):
        run_gui(Namespace())
