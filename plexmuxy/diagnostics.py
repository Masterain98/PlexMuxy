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


def export_diagnostics(config: AppConfig, output: Path, job_context: dict | None = None) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = collect_diagnostic_payload(config, job_context)
    config_data = payload["config"]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.json", json.dumps(payload, indent=2, ensure_ascii=False))
        archive.writestr("config.redacted.json", json.dumps(config_data, indent=2, ensure_ascii=False))
        archive.writestr(
            "README.txt",
            "No media file contents are included and configuration is redacted. "
            "Job diagnostics additionally include the media root path to help troubleshooting agents locate the original resources.\n",
        )
        if job_context is not None:
            archive.writestr(
                "job.redacted.json",
                json.dumps(redact_paths(job_context), indent=2, ensure_ascii=False),
            )
        latest_log = find_latest_log()
        if latest_log is not None:
            text = latest_log.read_text(encoding="utf-8", errors="replace")[-200_000:]
            text = text.replace(str(Path.home()), "<HOME>")
            archive.writestr("latest.log", text)
    return output


def _extract_media_root(job_context: dict | None) -> Path | None:
    """Best-effort full path to the media/project root a job operated on.

    Must run *before* path redaction: the job context is otherwise scrubbed to
    ``<PATH>/name`` so troubleshooting agents can no longer resolve the original
    media resources. Prefers ``report.input_dir`` over ``job.input_dir``.
    """
    if not isinstance(job_context, dict):
        return None
    for key in ("report", "job"):
        candidate = job_context.get(key)
        if isinstance(candidate, dict):
            root = candidate.get("input_dir")
            if isinstance(root, (str, Path)) and str(root).strip():
                try:
                    return Path(root).expanduser().resolve()
                except (OSError, RuntimeError):
                    return Path(root)
    return None


def collect_diagnostic_payload(config: AppConfig, job_context: dict | None = None) -> dict:
    config_data = redact_config(config_to_dict(config))
    media_root = _extract_media_root(job_context)
    payload: dict = {
        "plexmuxy_version": __version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependencies": dependency_versions(),
        "mkvmerge": mkvmerge_info(config),
        "config": config_data,
    }
    if job_context is not None:
        payload["job"] = redact_paths(job_context)
    if media_root is not None:
        payload["media_root"] = str(media_root)
    return payload


def format_diagnostic_payload(payload: dict) -> str:
    lines = []
    lines.append("PlexMuxy Diagnostics")
    lines.append("=" * 32)
    lines.append(f"PlexMuxy version: {payload.get('plexmuxy_version', 'unknown')}")
    lines.append(f"Python version: {payload.get('python_version', 'unknown')}")
    lines.append(f"Platform: {payload.get('platform', 'unknown')}")
    dependencies = payload.get("dependencies") or {}
    if dependencies:
        lines.append("Dependencies: " + ", ".join(f"{name}={version}" for name, version in dependencies.items()))
    mkvmerge = payload.get("mkvmerge") or {}
    if mkvmerge.get("version"):
        lines.append(f"mkvmerge: {mkvmerge.get('version')}")
    media_root = payload.get("media_root")
    if media_root:
        lines.append(f"Media root: {media_root}")
    lines.append("")
    config = payload.get("config")
    if config is not None:
        lines.append("Configuration:")
        lines.append(json.dumps(config, indent=2, ensure_ascii=False))
    job = payload.get("job")
    if job is not None:
        lines.append("")
        lines.append("Job context:")
        lines.append(json.dumps(job, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def redact_config(data: dict) -> dict:
    redacted = json.loads(json.dumps(data))
    if redacted.get("task", {}).get("output_dir"):
        redacted["task"]["output_dir"] = f"<PATH>/{Path(redacted['task']['output_dir']).name}"
    if redacted.get("mkvmerge", {}).get("path"):
        redacted["mkvmerge"]["path"] = f"<PATH>/{Path(redacted['mkvmerge']['path']).name}"
    if redacted.get("font", {}).get("unrar_path"):
        redacted["font"]["unrar_path"] = f"<PATH>/{Path(redacted['font']['unrar_path']).name}"
    for mapping in redacted.get("plex", {}).get("path_mappings", []):
        if mapping.get("local_root"):
            mapping["local_root"] = f"<PATH>/{Path(mapping['local_root']).name}"
    return redacted


def redact_paths(value):
    if isinstance(value, dict):
        return {key: redact_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_paths(item) for item in value]
    if isinstance(value, str) and ("/" in value or "\\" in value):
        # URLs are public integration metadata rather than local file paths.
        if value.startswith(("http://", "https://")):
            return value
        return f"<PATH>/{Path(value).name}"
    return value


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
