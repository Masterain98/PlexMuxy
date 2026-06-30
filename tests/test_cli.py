import builtins
from argparse import Namespace

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
    assert "GUI mode requires optional GUI dependencies" in capsys.readouterr().err
