from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .platform_paths import platform_tools_path
from .windows_metadata import WindowsFileMetadata, read_windows_file_metadata


@dataclass(frozen=True)
class DependencyResolution:
    name: str
    configured_path: str
    resolved_path: str | None
    source: str

    @property
    def available(self) -> bool:
        return self.resolved_path is not None


@dataclass(frozen=True)
class DependencyCandidate:
    path: Path
    source: str
    priority: int
    source_detail: str | None = None
    advertised_version: str | None = None


@dataclass(frozen=True)
class DependencyInspection:
    name: str
    path: str | None
    source: str
    available: bool
    valid: bool
    version: str | None = None
    file_version: str | None = None
    product_name: str | None = None
    original_filename: str | None = None
    error: str | None = None
    configured_path: str = ""
    version_warning: str | None = None


DEPENDENCY_SPECS: dict[str, dict[str, Any]] = {
    "mkvmerge": {
        "names": ("mkvmerge.exe", "mkvmerge") if os.name == "nt" else ("mkvmerge", "mkvmerge.exe"),
        "environment": ("PLEXMUXY_MKVMERGE", "MKVMERGE_PATH"),
    },
    "ffmpeg": {
        "names": ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg", "ffmpeg.exe"),
        "environment": ("PLEXMUXY_FFMPEG", "FFMPEG_PATH"),
    },
    "unrar": {
        "names": ("unrar.exe", "unrar") if os.name == "nt" else ("unrar", "unrar.exe"),
        "environment": ("PLEXMUXY_UNRAR", "UNRAR_PATH"),
    },
}


def resolve_dependency(
    name: str,
    configured_path: str = "",
    *,
    executable_names: Iterable[str],
    environment_variables: Iterable[str] = (),
    local_directory: Path | None = None,
) -> DependencyResolution:
    """Resolve a dependency while keeping an explicit override authoritative."""

    names = tuple(dict.fromkeys(str(item) for item in executable_names if str(item)))
    if not names:
        raise ValueError("At least one executable name is required")
    configured = str(configured_path or "").strip()
    if configured:
        resolved = _resolve_candidate(configured, names)
        return DependencyResolution(name, configured, resolved, "configured" if resolved else "configured-invalid")
    for variable in environment_variables:
        value = os.environ.get(variable, "").strip()
        if value:
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
    return _resolve_named("mkvmerge", configured_path)


def resolve_ffmpeg(configured_path: str = "") -> DependencyResolution:
    return _resolve_named("ffmpeg", configured_path)


def resolve_unrar(configured_path: str = "") -> DependencyResolution:
    return _resolve_named("unrar", configured_path)


def _resolve_named(name: str, configured_path: str) -> DependencyResolution:
    spec = DEPENDENCY_SPECS[name]
    return resolve_dependency(
        name,
        configured_path,
        executable_names=spec["names"],
        environment_variables=spec["environment"],
    )


def inspect_dependency(name: str, configured_path: str = "", *, ignore_configured: bool = False) -> DependencyInspection:
    if name not in DEPENDENCY_SPECS:
        raise ValueError(f"Unsupported dependency: {name}")
    configured = str(configured_path or "").strip()
    if configured and not ignore_configured:
        resolved = _resolve_candidate(configured, DEPENDENCY_SPECS[name]["names"])
        if not resolved:
            return DependencyInspection(
                name, None, "configured-invalid", False, False,
                error=f"The configured {name} executable could not be found", configured_path=configured,
            )
        return inspect_dependency_path(name, Path(resolved), source="configured", configured_path=configured)

    last_error: str | None = None
    for candidate in collect_dependency_candidates(name):
        inspected = inspect_dependency_path(name, candidate.path, source=candidate.source)
        if inspected.valid:
            if not inspected.version and candidate.advertised_version:
                inspected = DependencyInspection(**{**inspected.__dict__, "version": candidate.advertised_version})
            logging.info("Detected %s from %s: %s", name, candidate.source, candidate.path)
            return inspected
        last_error = inspected.error
        logging.info("Rejected %s candidate from %s (%s): %s", name, candidate.source, candidate.path, last_error)
    return DependencyInspection(name, None, "missing", False, False, error=last_error or f"No valid {name} executable found")


def collect_dependency_candidates(name: str, *, local_directory: Path | None = None) -> tuple[DependencyCandidate, ...]:
    spec = DEPENDENCY_SPECS[name]
    names = spec["names"]
    candidates: list[DependencyCandidate] = []
    priority = 0
    for variable in spec["environment"]:
        value = os.environ.get(variable, "").strip()
        if value:
            for path in _candidate_paths(value, names):
                candidates.append(DependencyCandidate(path, f"environment:{variable}", priority))
        priority += 1
    if name == "mkvmerge":
        candidates.extend(_iter_mkvtoolnix_registry_candidates(priority))
        priority += 10
    for executable in names:
        found = shutil.which(executable)
        if found:
            candidates.append(DependencyCandidate(Path(found), "path", priority))
    priority += 1
    if name == "unrar":
        candidates.append(DependencyCandidate(platform_tools_path() / "unrar" / "unrar.exe", "application-tools", priority))
        priority += 1
    directory = (local_directory or Path.cwd()).expanduser()
    candidates.extend(DependencyCandidate(directory / executable, "application-directory", priority) for executable in names)
    priority += 1
    if os.name == "nt" and name == "mkvmerge":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable)
            if root:
                candidates.append(DependencyCandidate(Path(root) / "MKVToolNix" / "mkvmerge.exe", "program-files", priority))
    if os.name == "nt" and name == "unrar":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable)
            if root:
                candidates.append(DependencyCandidate(Path(root) / "WinRAR" / "UnRAR.exe", "program-files", priority))
    return _deduplicate_candidates(candidates)


def inspect_dependency_path(
    name: str,
    path: Path,
    *,
    source: str,
    configured_path: str = "",
) -> DependencyInspection:
    resolved = path.expanduser().resolve()
    names = {item.casefold() for item in DEPENDENCY_SPECS[name]["names"]}
    if not resolved.is_file():
        return _invalid_inspection(name, resolved, source, "Executable does not exist", configured_path)
    if resolved.name.casefold() not in names:
        return _invalid_inspection(name, resolved, source, f"Unexpected executable name: {resolved.name}", configured_path)
    if os.name != "nt" and not os.access(resolved, os.X_OK):
        return _invalid_inspection(name, resolved, source, "File is not executable", configured_path)
    metadata = read_windows_file_metadata(resolved)
    if name == "mkvmerge" and metadata.product_name and metadata.product_name.casefold() != "mkvtoolnix":
        return _invalid_inspection(name, resolved, source, "ProductName is not MKVToolNix", configured_path, metadata)
    try:
        version = _probe_dependency(name, resolved)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return _invalid_inspection(name, resolved, source, str(exc), configured_path, metadata)
    warning = None
    if version and metadata.file_version and _normalized_version(version) != _normalized_version(metadata.file_version):
        warning = "Command and file version information do not match"
    return DependencyInspection(
        name=name,
        path=str(resolved),
        source=source,
        available=True,
        valid=True,
        version=version,
        file_version=metadata.file_version,
        product_name=metadata.product_name,
        original_filename=metadata.original_filename,
        configured_path=configured_path,
        version_warning=warning,
    )


def _probe_dependency(name: str, path: Path, *, timeout: float = 5.0) -> str | None:
    if name == "ffmpeg":
        command = [str(path), "-version"]
    elif name == "mkvmerge":
        command = [str(path), "--version"]
    else:
        command = [str(path)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    result = subprocess.run(
        command, capture_output=True, text=True, errors="replace", timeout=timeout,
        shell=False, creationflags=flags,
    )
    output = (result.stdout + "\n" + result.stderr)[:16384]
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if name == "mkvmerge":
        if result.returncode != 0 or "mkvmerge" not in output.casefold():
            raise ValueError("mkvmerge --version did not return a valid response")
        match = re.search(r"\bmkvmerge\s+v?([^\s(]+)", output, re.IGNORECASE)
    elif name == "ffmpeg":
        if result.returncode != 0 or "ffmpeg version" not in first_line.casefold():
            raise ValueError("ffmpeg -version did not return a valid response")
        match = re.search(r"\bffmpeg version\s+([^\s]+)", first_line, re.IGNORECASE)
    else:
        if "unrar" not in output.casefold():
            raise ValueError("UnRAR did not return recognizable help or version output")
        match = re.search(r"\bUNRAR\s+([\d.]+)", output, re.IGNORECASE)
    return match.group(1) if match else None


def _invalid_inspection(
    name: str,
    path: Path,
    source: str,
    error: str,
    configured_path: str = "",
    metadata: WindowsFileMetadata | None = None,
) -> DependencyInspection:
    metadata = metadata or WindowsFileMetadata()
    return DependencyInspection(
        name, str(path), source, False, False,
        file_version=metadata.file_version, product_name=metadata.product_name,
        original_filename=metadata.original_filename, error=error, configured_path=configured_path,
    )


def _normalized_version(value: str) -> tuple[int, ...] | str:
    numbers = re.match(r"^[vV]?(\d+(?:\.\d+)*)", value.strip())
    if not numbers:
        return value.strip().casefold()
    parts = [int(part) for part in numbers.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _iter_mkvtoolnix_registry_candidates(base_priority: int = 0, winreg_module=None) -> tuple[DependencyCandidate, ...]:
    if os.name != "nt" and winreg_module is None:
        return ()
    try:
        winreg = winreg_module or __import__("winreg")
    except ImportError:
        return ()
    uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    candidates: list[DependencyCandidate] = []
    roots = ((winreg.HKEY_CURRENT_USER, "hkcu"), (winreg.HKEY_LOCAL_MACHINE, "hklm"))
    views = ((getattr(winreg, "KEY_WOW64_64KEY", 0), "64"), (getattr(winreg, "KEY_WOW64_32KEY", 0), "32"))
    for root, root_name in roots:
        for view_flag, view_name in views:
            source = f"registry:{root_name}:{view_name}"
            try:
                with winreg.OpenKey(root, uninstall, 0, winreg.KEY_READ | view_flag) as parent:
                    count = winreg.QueryInfoKey(parent)[0]
                    for index in range(count):
                        try:
                            with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as entry:
                                values = {key: _registry_value(winreg, entry, key) for key in (
                                    "DisplayName", "DisplayVersion", "InstallLocation", "DisplayIcon", "UninstallString",
                                )}
                            normalized = " ".join(str(values["DisplayName"] or "").casefold().split())
                            if normalized != "mkvtoolnix" and not normalized.startswith("mkvtoolnix "):
                                continue
                            for directory in _registry_install_directories(values):
                                candidates.append(DependencyCandidate(
                                    directory / "mkvmerge.exe", source, base_priority,
                                    source_detail=f"Windows registry · {root_name.upper()} · {view_name}-bit",
                                    advertised_version=str(values["DisplayVersion"] or "") or None,
                                ))
                        except (OSError, ValueError):
                            continue
            except OSError:
                continue
    return _deduplicate_candidates(candidates)


def _registry_value(winreg, key, name: str):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def _registry_install_directories(values: dict[str, Any]) -> Iterator[Path]:
    location = str(values.get("InstallLocation") or "").strip().strip('"')
    if location:
        yield Path(os.path.expandvars(location))
    for key in ("DisplayIcon", "UninstallString"):
        raw = str(values.get(key) or "").strip()
        if not raw:
            continue
        executable_end = raw.casefold().find(".exe")
        if executable_end >= 0:
            token = raw[:executable_end + 4].strip().strip('"')
        else:
            try:
                token = shlex.split(raw, posix=False)[0].strip('"')
            except (ValueError, IndexError):
                continue
        path = Path(os.path.expandvars(token))
        if path.suffix.casefold() == ".exe":
            yield path.parent


def _candidate_paths(value: str, names: tuple[str, ...]) -> Iterator[Path]:
    expanded = os.path.expandvars(value.strip().strip('"'))
    path = Path(expanded).expanduser()
    if not path.is_absolute() and not any(separator in expanded for separator in ("/", "\\")):
        found = shutil.which(expanded)
        if found:
            yield Path(found)
            return
    if path.is_dir() or not path.suffix:
        for name in names:
            yield path / name
    else:
        yield path


def _deduplicate_candidates(candidates: Iterable[DependencyCandidate]) -> tuple[DependencyCandidate, ...]:
    unique: dict[str, DependencyCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: item.priority):
        key = os.path.normcase(str(candidate.path.expanduser().absolute()))
        unique.setdefault(key, candidate)
    return tuple(unique.values())


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
