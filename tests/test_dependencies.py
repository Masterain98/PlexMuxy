from pathlib import Path

from plexmuxy.dependencies import resolve_dependency


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
