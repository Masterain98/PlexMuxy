import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from plexmuxy.dependencies import (
    DependencyInspection,
    _iter_mkvtoolnix_registry_candidates,
    _probe_dependency,
    _registry_install_directories,
    collect_dependency_candidates,
    inspect_dependency,
    resolve_dependency,
)


def test_explicit_dependency_path_is_authoritative(tmp_path: Path, monkeypatch) -> None:
    fallback = tmp_path / "fallback" / "tool.exe"
    fallback.parent.mkdir()
    fallback.write_bytes(b"fallback")
    monkeypatch.setattr("plexmuxy.dependencies.shutil.which", lambda _name: str(fallback))

    result = resolve_dependency("tool", str(tmp_path / "missing.exe"), executable_names=("tool.exe",))

    assert result.available is False
    assert result.source == "configured-invalid"


def test_dependency_directory_and_environment_resolution(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "bin" / "tool.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"tool")
    monkeypatch.setenv("TOOL_HOME", str(executable.parent))

    result = resolve_dependency(
        "tool",
        executable_names=("tool.exe",),
        environment_variables=("TOOL_HOME",),
    )

    assert result.resolved_path == str(executable.resolve())
    assert result.source == "environment:TOOL_HOME"


def test_dependency_falls_back_to_application_directory(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "tool"
    executable.write_bytes(b"tool")
    monkeypatch.setattr("plexmuxy.dependencies.shutil.which", lambda _name: None)

    result = resolve_dependency("tool", executable_names=("tool",), local_directory=tmp_path)

    assert result.resolved_path == str(executable.resolve())
    assert result.source == "application-directory"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: reads the registry")
def test_auto_detect_ignores_persisted_override(tmp_path: Path, monkeypatch) -> None:
    detected = tmp_path / "mkvmerge.exe"
    detected.write_bytes(b"candidate")
    monkeypatch.setenv("PLEXMUXY_MKVMERGE", str(detected))
    monkeypatch.setattr("plexmuxy.dependencies._probe_dependency", lambda *_args, **_kwargs: "100.0")

    result = inspect_dependency("mkvmerge", str(tmp_path / "missing.exe"), ignore_configured=True)

    assert result.valid is True
    assert result.path == str(detected.resolve())
    assert result.source == "environment:PLEXMUXY_MKVMERGE"


def test_configured_invalid_path_remains_authoritative(tmp_path: Path, monkeypatch) -> None:
    fallback = tmp_path / "mkvmerge.exe"
    fallback.write_bytes(b"candidate")
    monkeypatch.setattr("plexmuxy.dependencies.shutil.which", lambda _name: str(fallback))

    result = inspect_dependency("mkvmerge", str(tmp_path / "missing.exe"))

    assert result.valid is False
    assert result.source == "configured-invalid"
    assert result.path is None


def test_invalid_high_priority_candidate_falls_back(tmp_path: Path, monkeypatch) -> None:
    invalid = tmp_path / "invalid" / "ffmpeg.exe"
    valid = tmp_path / "valid" / "ffmpeg.exe"
    invalid.parent.mkdir()
    valid.parent.mkdir()
    invalid.write_bytes(b"bad")
    valid.write_bytes(b"good")
    monkeypatch.setenv("PLEXMUXY_FFMPEG", str(invalid))
    monkeypatch.setattr("plexmuxy.dependencies.shutil.which", lambda _name: str(valid))

    def inspect(name, path, *, source, configured_path=""):
        ok = path.resolve() == valid.resolve()
        return DependencyInspection(name, str(path.resolve()), source, ok, ok, version="7.0" if ok else None, error=None if ok else "bad")

    monkeypatch.setattr("plexmuxy.dependencies.inspect_dependency_path", inspect)
    result = inspect_dependency("ffmpeg", ignore_configured=True)

    assert result.valid is True
    assert result.path == str(valid.resolve())
    assert result.source == "path"


def test_application_tools_directory_is_detected(tmp_path: Path, monkeypatch) -> None:
    tool = tmp_path / "tools" / "unrar" / "unrar.exe"
    tool.parent.mkdir(parents=True)
    tool.write_bytes(b"unrar")
    monkeypatch.setattr("plexmuxy.dependencies.platform_tools_path", lambda: tmp_path / "tools")
    monkeypatch.setattr("plexmuxy.dependencies.shutil.which", lambda _name: None)
    candidates = collect_dependency_candidates("unrar", local_directory=tmp_path / "app")

    match = next(candidate for candidate in candidates if candidate.path == tool)
    assert match.source == "application-tools"


def test_command_versions_are_parsed(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "mkvmerge.exe"
    executable.write_bytes(b"stub")
    monkeypatch.setattr(
        "plexmuxy.dependencies.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="mkvmerge v100.0 ('Test') 64-bit\n", stderr=""),
    )

    assert _probe_dependency("mkvmerge", executable) == "100.0"


def test_ffmpeg_probe_uses_supported_single_dash_version_option(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"stub")
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout="ffmpeg version N-121243-g994a368451 Copyright (c) FFmpeg developers\n",
            stderr="",
        )

    monkeypatch.setattr("plexmuxy.dependencies.subprocess.run", run)

    assert _probe_dependency("ffmpeg", executable) == "N-121243-g994a368451"
    assert commands == [[str(executable), "-version"]]


def test_command_probe_timeout_is_handled(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"stub")

    def timeout(*_args, **_kwargs):
        raise __import__("subprocess").TimeoutExpired("ffmpeg", 5)

    monkeypatch.setattr("plexmuxy.dependencies.subprocess.run", timeout)
    with pytest.raises(__import__("subprocess").TimeoutExpired):
        _probe_dependency("ffmpeg", executable)


class _RegistryKey:
    def __init__(self, owner, kind, values=None):
        self.owner = owner
        self.kind = kind
        self.values = values or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeWinreg:
    HKEY_CURRENT_USER = 1
    HKEY_LOCAL_MACHINE = 2
    KEY_READ = 4
    KEY_WOW64_64KEY = 8
    KEY_WOW64_32KEY = 16

    def __init__(self, install_location):
        self.install_location = install_location
        self.accesses = []

    def OpenKey(self, root, path, _reserved=0, access=0):
        if isinstance(root, _RegistryKey):
            return _RegistryKey(self, "entry", {
                "DisplayName": "MKVToolNix",
                "DisplayVersion": "100.0",
                "InstallLocation": self.install_location,
            })
        self.accesses.append((root, access))
        return _RegistryKey(self, "parent")

    def QueryInfoKey(self, _key):
        return (1, 0, 0)

    def EnumKey(self, _key, _index):
        return "MKVToolNix"

    def QueryValueEx(self, key, name):
        if name not in key.values:
            raise OSError(name)
        return key.values[name], 1


def test_registry_discovery_scans_hives_and_bitness(tmp_path: Path) -> None:
    fake = FakeWinreg(str(tmp_path))

    candidates = _iter_mkvtoolnix_registry_candidates(winreg_module=fake)

    assert {candidate.source for candidate in candidates} == {"registry:hkcu:64"}
    assert {root for root, _access in fake.accesses} == {fake.HKEY_CURRENT_USER, fake.HKEY_LOCAL_MACHINE}
    assert len(fake.accesses) == 4
    assert {access for _root, access in fake.accesses} == {fake.KEY_READ | fake.KEY_WOW64_64KEY, fake.KEY_READ | fake.KEY_WOW64_32KEY}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: parses Windows registry paths")
def test_registry_display_icon_and_uninstall_paths_allow_unquoted_spaces() -> None:
    directories = list(_registry_install_directories({
        "InstallLocation": "",
        "DisplayIcon": r"C:\Program Files\MKVToolNix\mkvtoolnix-gui.exe,0",
        "UninstallString": r"C:\Program Files\MKVToolNix\uninst.exe /S",
    }))

    assert directories == [Path(r"C:\Program Files\MKVToolNix"), Path(r"C:\Program Files\MKVToolNix")]
