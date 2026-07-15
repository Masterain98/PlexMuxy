from __future__ import annotations

import logging
import os
import platform
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .dependencies import DependencyInspection, inspect_dependency
from .platform_paths import platform_tools_path
from .windows_metadata import AuthenticodeResult, verify_authenticode

RARLAB_UNRAR_URL = "https://www.rarlab.com/rar/unrarw64.exe"
RARLAB_HOSTS = frozenset({"www.rarlab.com", "rarlab.com"})
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 20

_install_lock = threading.Lock()


@dataclass(frozen=True)
class UnrarAcquisition:
    inspection: DependencyInspection
    installer_path: str
    publisher: str | None


class TrustedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_rarlab_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def install_unrar_from_rarlab(
    *,
    url: str = RARLAB_UNRAR_URL,
    opener=None,
    signature_verifier: Callable[..., AuthenticodeResult] = verify_authenticode,
    installer_launcher: Callable[[Path], None] | None = None,
) -> UnrarAcquisition:
    """Download and run RARLAB's signed installer, then detect installed UnRAR.

    RARLAB currently distributes Windows UnRAR as a signed self-extracting
    installer.  Since no stable unattended extraction contract is published,
    PlexMuxy deliberately lets the official installer own the installation UI.
    """

    if os.name != "nt":
        raise RuntimeError("RARLAB UnRAR acquisition is currently available only on Windows")
    if platform.machine().casefold() not in {"amd64", "x86_64"}:
        raise RuntimeError("RARLAB UnRAR acquisition requires Windows x64")
    if not _install_lock.acquire(blocking=False):
        raise RuntimeError("An UnRAR acquisition is already in progress")
    try:
        _validate_rarlab_url(url)
        downloads = platform_tools_path() / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix="unrarw64-", suffix=".download", dir=downloads)
        os.close(fd)
        temporary = Path(temporary_name)
        installer = downloads / "unrarw64.exe"
        try:
            _download_to_file(url, temporary, opener=opener)
            signature = signature_verifier(temporary, allowed_publishers=("win.rar GmbH", "RARLAB"))
            if not signature.valid:
                raise RuntimeError(signature.error or "The RARLAB installer signature is not valid")
            os.replace(temporary, installer)
        finally:
            temporary.unlink(missing_ok=True)

        logging.info("Launching verified RARLAB UnRAR installer signed by %s", signature.publisher)
        (installer_launcher or _launch_installer_and_wait)(installer)
        inspection = inspect_dependency("unrar", ignore_configured=True)
        if not inspection.valid:
            raise RuntimeError(
                "The RARLAB installer finished, but a working UnRAR executable was not found. "
                "Complete the installation and use Auto-detect again."
            )
        return UnrarAcquisition(inspection, str(installer), signature.publisher)
    finally:
        _install_lock.release()


def _download_to_file(url: str, destination: Path, *, opener=None) -> None:
    client = opener or urllib.request.build_opener(TrustedRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "PlexMuxy dependency installer"})
    try:
        with client.open(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            _validate_rarlab_url(response.geturl())
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("RARLAB download exceeds the allowed size")
            _copy_limited(response, destination)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, RuntimeError) as exc:
        destination.unlink(missing_ok=True)
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Unable to download UnRAR from RARLAB: {exc}") from exc


def _copy_limited(source: BinaryIO, destination: Path) -> None:
    total = 0
    with destination.open("wb") as output:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("RARLAB download exceeds the allowed size")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if total == 0:
        raise RuntimeError("RARLAB returned an empty download")


def _validate_rarlab_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.casefold() != "https" or (parsed.hostname or "").casefold() not in RARLAB_HOSTS:
        raise RuntimeError("UnRAR downloads are restricted to the official RARLAB HTTPS host")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise RuntimeError("The RARLAB download URL contains unsupported authority information")


def _launch_installer_and_wait(installer: Path) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run([str(installer)], shell=False, creationflags=flags)
    if result.returncode != 0:
        raise RuntimeError(f"The RARLAB installer exited with code {result.returncode}")
