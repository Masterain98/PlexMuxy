from __future__ import annotations

import json
import platform
import subprocess
import sys
import zipfile
from importlib import metadata
from pathlib import Path

from . import __version__
from .config import config_to_dict, platform_config_path
from .models import AppConfig
from .muxer import resolve_mkvmerge_path, windows_no_window_flag


def export_diagnostics(config: AppConfig, output: Path) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    config_data = redact_config(config_to_dict(config))
    payload = {
        "plexmuxy_version": __version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependencies": dependency_versions(),
        "mkvmerge": mkvmerge_info(config),
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.json", json.dumps(payload, indent=2, ensure_ascii=False))
        archive.writestr("config.redacted.json", json.dumps(config_data, indent=2, ensure_ascii=False))
        archive.writestr("README.txt", "No media files or full home-directory paths are included.\n")
        latest_log = find_latest_log()
        if latest_log is not None:
            text = latest_log.read_text(encoding="utf-8", errors="replace")[-200_000:]
            text = text.replace(str(Path.home()), "<HOME>")
            archive.writestr("latest.log", text)
    return output


def redact_config(data: dict) -> dict:
    redacted = json.loads(json.dumps(data))
    if redacted.get("task", {}).get("output_dir"):
        redacted["task"]["output_dir"] = f"<PATH>/{Path(redacted['task']['output_dir']).name}"
    if redacted.get("mkvmerge", {}).get("path"):
        redacted["mkvmerge"]["path"] = f"<PATH>/{Path(redacted['mkvmerge']['path']).name}"
    if redacted.get("font", {}).get("unrar_path"):
        redacted["font"]["unrar_path"] = f"<PATH>/{Path(redacted['font']['unrar_path']).name}"
    return redacted


def dependency_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("pymkv2", "py7zr", "patool", "rich", "fonttools", "pywebview"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "not installed"
    return result


def mkvmerge_info(config: AppConfig) -> dict[str, str | None]:
    path = resolve_mkvmerge_path(config)
    if path is None:
        return {"path": None, "version": None}
    completed = subprocess.run(
        [path, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, creationflags=windows_no_window_flag(),
    )
    return {"path": f"<PATH>/{Path(path).name}", "version": (completed.stdout or completed.stderr).strip()}


def find_latest_log() -> Path | None:
    log_dir = platform_config_path().parent / "logs"
    if not log_dir.is_dir():
        return None
    logs = sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    return logs[0] if logs else None
