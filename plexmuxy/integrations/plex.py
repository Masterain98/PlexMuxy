from __future__ import annotations

import os
import posixpath
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..models import PlexConfig


class PlexIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlexRefreshResult:
    local_path: str
    server_path: str | None
    success: bool
    status_code: int | None = None
    error: str | None = None


def validate_server_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PlexIntegrationError("Plex server URL must be an absolute http or https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PlexIntegrationError("Plex server URL cannot contain credentials, a query, or a fragment")
    return raw


def map_local_path(path: Path, config: PlexConfig) -> str:
    resolved = path.expanduser().resolve()
    candidates: list[tuple[int, str]] = []
    for mapping in config.path_mappings:
        local_root = mapping.local_root.expanduser().resolve()
        try:
            relative = resolved.relative_to(local_root)
        except ValueError:
            continue
        server_root = mapping.server_root.rstrip("/\\")
        relative_parts = [part for part in relative.parts if part not in {".", ""}]
        if "\\" in server_root and "/" not in server_root:
            mapped = server_root + (("\\" + "\\".join(relative_parts)) if relative_parts else "")
        else:
            mapped = posixpath.join(server_root or "/", *relative_parts)
        candidates.append((len(local_root.parts), mapped))
    if not candidates:
        raise PlexIntegrationError(f"No Plex path mapping covers: {resolved}")
    return max(candidates, key=lambda item: item[0])[1]


def refresh_paths(config: PlexConfig, paths: list[Path], *, timeout: float = 5.0) -> list[PlexRefreshResult]:
    if not config.enabled:
        return []
    server_url = validate_server_url(config.server_url)
    if not config.section_id or not config.section_id.isdigit():
        raise PlexIntegrationError("Plex section_id must be a numeric library section ID")
    token = os.environ.get(config.token_env, "").strip()
    if not token:
        raise PlexIntegrationError(f"Plex token environment variable is not set: {config.token_env}")

    results: list[PlexRefreshResult] = []
    for path in sorted({item.expanduser().resolve() for item in paths}, key=str):
        try:
            server_path = map_local_path(path, config)
            query = urllib.parse.urlencode({"path": server_path})
            url = f"{server_url}/library/sections/{config.section_id}/refresh?{query}"
            request = urllib.request.Request(
                url,
                method="GET",
                headers={"Accept": "application/json", "X-Plex-Token": token, "User-Agent": "PlexMuxy"},
            )
            with urllib.request.urlopen(request, timeout=max(0.5, min(float(timeout), 15.0))) as response:
                status = int(getattr(response, "status", 200))
            results.append(PlexRefreshResult(str(path), server_path, 200 <= status < 300, status))
        except Exception as exc:  # noqa: BLE001 - post actions are reported per path.
            server_path = None
            try:
                server_path = map_local_path(path, config)
            except PlexIntegrationError:
                pass
            results.append(PlexRefreshResult(str(path), server_path, False, error=_safe_error(exc)))
    return results


def _safe_error(exc: Exception) -> str:
    # Request objects keep the token in a header rather than the URL; avoid
    # repr(exc) so an HTTP library cannot leak request headers into reports.
    return str(exc).splitlines()[0][:500]
