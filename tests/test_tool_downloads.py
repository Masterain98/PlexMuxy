from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

import pytest

from plexmuxy.dependencies import DependencyInspection
from plexmuxy.tool_downloads import (
    MAX_DOWNLOAD_BYTES,
    _download_to_file,
    _install_lock,
    _validate_rarlab_url,
    install_unrar_from_rarlab,
)
from plexmuxy.windows_metadata import AuthenticodeResult


class FakeResponse(BytesIO):
    def __init__(self, data: bytes, *, url="https://www.rarlab.com/rar/unrarw64.exe", length=None):
        super().__init__(data)
        self._url = url
        self.headers = {"Content-Length": str(length if length is not None else len(data))}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, _request, timeout):
        assert timeout > 0
        return self.response


def test_rejects_non_https_and_untrusted_hosts():
    with pytest.raises(RuntimeError):
        _validate_rarlab_url("http://www.rarlab.com/rar/unrarw64.exe")
    with pytest.raises(RuntimeError):
        _validate_rarlab_url("https://example.com/unrarw64.exe")


def test_rejects_redirect_to_untrusted_host(tmp_path: Path):
    destination = tmp_path / "download"
    opener = FakeOpener(FakeResponse(b"data", url="https://example.com/unrarw64.exe"))
    with pytest.raises(RuntimeError):
        _download_to_file("https://www.rarlab.com/rar/unrarw64.exe", destination, opener=opener)
    assert not destination.exists()


def test_enforces_download_size_limit_and_removes_partial_file(tmp_path: Path):
    destination = tmp_path / "download"
    opener = FakeOpener(FakeResponse(b"small", length=MAX_DOWNLOAD_BYTES + 1))
    with pytest.raises(RuntimeError):
        _download_to_file("https://www.rarlab.com/rar/unrarw64.exe", destination, opener=opener)
    assert not destination.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: RARLAB UnRAR acquisition requires Windows")
def test_verified_installer_is_atomically_published_and_returns_candidate(tmp_path: Path, monkeypatch):
    tools = tmp_path / "tools"
    monkeypatch.setattr("plexmuxy.tool_downloads.platform_tools_path", lambda: tools)
    inspection = DependencyInspection("unrar", str(tmp_path / "UnRAR.exe"), "program-files", True, True, version="7.23")
    monkeypatch.setattr("plexmuxy.tool_downloads.inspect_dependency", lambda *_args, **_kwargs: inspection)
    launched = []

    result = install_unrar_from_rarlab(
        opener=FakeOpener(FakeResponse(b"signed installer")),
        signature_verifier=lambda *_args, **_kwargs: AuthenticodeResult(True, "CN=win.rar GmbH"),
        installer_launcher=lambda path: launched.append(path),
    )

    installer = tools / "downloads" / "unrarw64.exe"
    assert installer.read_bytes() == b"signed installer"
    assert launched == [installer]
    assert result.inspection.version == "7.23"


def test_signature_failure_does_not_publish_installer(tmp_path: Path, monkeypatch):
    tools = tmp_path / "tools"
    monkeypatch.setattr("plexmuxy.tool_downloads.platform_tools_path", lambda: tools)
    with pytest.raises(RuntimeError):
        install_unrar_from_rarlab(
            opener=FakeOpener(FakeResponse(b"untrusted")),
            signature_verifier=lambda *_args, **_kwargs: AuthenticodeResult(False, error="bad signature"),
            installer_launcher=lambda _path: None,
        )
    assert not (tools / "downloads" / "unrarw64.exe").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: RARLAB UnRAR acquisition requires Windows")
def test_concurrent_install_request_is_rejected():
    assert _install_lock.acquire(blocking=False)
    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            install_unrar_from_rarlab()
    finally:
        _install_lock.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: RARLAB UnRAR acquisition requires Windows")
def test_windows_x64_is_required(monkeypatch):
    monkeypatch.setattr("plexmuxy.tool_downloads.platform.machine", lambda: "ARM64")
    with pytest.raises(RuntimeError, match="Windows x64"):
        install_unrar_from_rarlab()
