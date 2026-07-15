import subprocess
from pathlib import Path

from plexmuxy.windows_metadata import read_windows_file_metadata, verify_authenticode


def test_missing_version_resource_returns_none(tmp_path: Path):
    executable = tmp_path / "empty.exe"
    executable.write_bytes(b"not a PE file")

    metadata = read_windows_file_metadata(executable)

    assert metadata.file_version is None
    assert metadata.product_name is None


def test_authenticode_uses_inbox_security_module_and_parses_json(monkeypatch, tmp_path: Path):
    executable = tmp_path / "installer.exe"
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"Valid","publisher":"CN=win.rar GmbH"}',
            stderr="",
        )

    monkeypatch.setattr("plexmuxy.windows_metadata.subprocess.run", fake_run)

    result = verify_authenticode(executable, allowed_publishers=("win.rar GmbH",))

    assert result.valid is True
    assert result.publisher == "CN=win.rar GmbH"
    script = captured["command"][-1]
    assert "WindowsPowerShell\\v1.0\\Modules\\Microsoft.PowerShell.Security" in script
    assert captured["kwargs"]["encoding"] == "utf-8"


def test_authenticode_reports_powershell_module_failure(monkeypatch, tmp_path: Path):
    executable = tmp_path / "installer.exe"

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="security module could not be loaded")

    monkeypatch.setattr("plexmuxy.windows_metadata.subprocess.run", fake_run)

    result = verify_authenticode(executable)

    assert result.valid is False
    assert result.error == "Signature verification failed: security module could not be loaded"
