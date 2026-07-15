from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .models import UpdateConfig

RELEASE_API_URL = "https://api.github.com/repos/Masterain98/PlexMuxy/releases/latest"


@dataclass(frozen=True)
class UpdateCheckResult:
    enabled: bool
    checked: bool
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    release_notes_summary: str | None = None
    checksum_url: str | None = None
    checked_at: int | None = None
    cached: bool = False
    error: str | None = None


def platform_update_cache_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "PlexMuxy" / "update-check.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "PlexMuxy" / "update-check.json"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "plexmuxy" / "update-check.json"


def check_for_updates(
    current_version: str,
    config: UpdateConfig,
    *,
    force: bool = False,
    cache_path: Path | None = None,
) -> UpdateCheckResult:
    if not config.enabled and not force:
        return UpdateCheckResult(False, False, current_version)
    target = Path(cache_path or platform_update_cache_path())
    now = int(time.time())
    cached = _read_cache(target)
    if not force and cached and now - int(cached.get("checked_at", 0)) < config.interval_hours * 3600:
        return _result_from_cache(current_version, cached, enabled=config.enabled)
    try:
        request = urllib.request.Request(
            RELEASE_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"PlexMuxy/{current_version}"},
        )
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
        tag = str(payload.get("tag_name") or "").strip()
        latest = tag[1:] if tag.casefold().startswith("v") else tag
        release_url = str(payload.get("html_url") or "").strip() or None
        notes = " ".join(str(payload.get("body") or "").split())[:500] or None
        checksum_url = next((
            str(asset.get("browser_download_url"))
            for asset in payload.get("assets", [])
            if isinstance(asset, dict) and "sha256" in str(asset.get("name", "")).casefold()
        ), None)
        if _version_parts(latest) is None:
            raise ValueError("Release response did not contain a valid version")
        data = {
            "checked_at": now, "latest_version": latest, "release_url": release_url,
            "release_notes_summary": notes, "checksum_url": checksum_url, "error": None,
        }
        _write_cache(target, data)
        return _result_from_cache(current_version, data, enabled=config.enabled, cached=False)
    except Exception as exc:  # noqa: BLE001 - checks must never block application startup.
        error = str(exc).splitlines()[0][:500]
        data = {"checked_at": now, "latest_version": None, "release_url": None, "error": error}
        _write_cache(target, data)
        return UpdateCheckResult(config.enabled, True, current_version, checked_at=now, error=error)


def _result_from_cache(
    current_version: str,
    data: dict,
    *,
    enabled: bool,
    cached: bool = True,
) -> UpdateCheckResult:
    latest = data.get("latest_version")
    return UpdateCheckResult(
        enabled=enabled,
        checked=True,
        current_version=current_version,
        latest_version=latest,
        update_available=_is_newer(str(latest), current_version) if latest else False,
        release_url=data.get("release_url"),
        release_notes_summary=data.get("release_notes_summary"),
        checksum_url=data.get("checksum_url"),
        checked_at=int(data.get("checked_at", 0)) or None,
        cached=cached,
        error=data.get("error"),
    )


def _version_parts(value: str) -> tuple[int, int, int, int, int, int] | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+){1,3})(?:(a|b|rc)(\d+))?\s*", str(value), re.IGNORECASE)
    if not match:
        return None
    release = [int(part) for part in match.group(1).split(".")]
    release.extend([0] * (4 - len(release)))
    stages = {"a": 0, "b": 1, "rc": 2}
    stage = stages.get((match.group(2) or "").casefold(), 3)
    prerelease = int(match.group(3) or 0)
    return (release[0], release[1], release[2], release[3], stage, prerelease)


def _is_newer(candidate: str, current: str) -> bool:
    candidate_parts = _version_parts(candidate)
    current_parts = _version_parts(current)
    return bool(candidate_parts is not None and current_parts is not None and candidate_parts > current_parts)


def _read_cache(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass
