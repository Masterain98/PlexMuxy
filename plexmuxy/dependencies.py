from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DependencyResolution:
    """Resolved state for one optional or required executable dependency."""

    name: str
    configured_path: str
    resolved_path: str | None
    source: str

    @property
    def available(self) -> bool:
        return self.resolved_path is not None


def resolve_dependency(
    name: str,
    configured_path: str = "",
    *,
    executable_names: Iterable[str],
    environment_variables: Iterable[str] = (),
    local_directory: Path | None = None,
) -> DependencyResolution:
    """Resolve an executable without hiding an invalid explicit override.

    Resolution order is the persisted override, dependency-specific environment
    variables, ``PATH``, then the application working directory.  A configured
    value is authoritative: if it is invalid, callers can surface that error
    instead of silently running a different binary from ``PATH``.
    """

    names = tuple(dict.fromkeys(str(item) for item in executable_names if str(item)))
    if not names:
        raise ValueError("At least one executable name is required")

    configured = str(configured_path or "").strip()
    if configured:
        resolved = _resolve_candidate(configured, names)
        return DependencyResolution(name, configured, resolved, "configured" if resolved else "configured-invalid")

    for variable in environment_variables:
        value = os.environ.get(variable, "").strip()
        if not value:
            continue
        resolved = _resolve_candidate(value, names)
        if resolved:
            return DependencyResolution(name, "", resolved, f"environment:{variable}")

    for executable in names:
        found = shutil.which(executable)
        if found:
            return DependencyResolution(name, "", str(Path(found).resolve()), "path")

    directory = (local_directory or Path.cwd()).expanduser()
    for executable in names:
        candidate = directory / executable
        if candidate.is_file():
            return DependencyResolution(name, "", str(candidate.resolve()), "application-directory")

    return DependencyResolution(name, "", None, "missing")


def resolve_mkvmerge(configured_path: str = "") -> DependencyResolution:
    return resolve_dependency(
        "mkvmerge",
        configured_path,
        executable_names=("mkvmerge.exe", "mkvmerge") if os.name == "nt" else ("mkvmerge", "mkvmerge.exe"),
        environment_variables=("PLEXMUXY_MKVMERGE", "MKVMERGE_PATH"),
    )


def resolve_ffmpeg(configured_path: str = "") -> DependencyResolution:
    return resolve_dependency(
        "ffmpeg",
        configured_path,
        executable_names=("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg", "ffmpeg.exe"),
        environment_variables=("PLEXMUXY_FFMPEG", "FFMPEG_PATH"),
    )


def resolve_unrar(configured_path: str = "") -> DependencyResolution:
    return resolve_dependency(
        "unrar",
        configured_path,
        executable_names=("unrar.exe", "unrar") if os.name == "nt" else ("unrar", "unrar.exe"),
        environment_variables=("PLEXMUXY_UNRAR", "UNRAR_PATH"),
    )


def _resolve_candidate(value: str, executable_names: tuple[str, ...]) -> str | None:
    expanded = os.path.expandvars(value.strip().strip('"'))
    path = Path(expanded).expanduser()
    if path.is_dir():
        for name in executable_names:
            candidate = path / name
            if candidate.is_file():
                return str(candidate.resolve())
        return None
    if path.is_file():
        return str(path.resolve())
    if path.is_absolute() or any(separator in expanded for separator in ("/", "\\")):
        return None
    found = shutil.which(expanded)
    return str(Path(found).resolve()) if found else None
