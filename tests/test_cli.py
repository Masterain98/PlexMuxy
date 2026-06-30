import builtins
import sys
from argparse import Namespace

import pytest

from plexmuxy.cli import run_gui


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
