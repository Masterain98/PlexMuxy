from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    # ``ctypes.windll`` only exists on Windows; alias it so this module
    # type-checks on other platforms (the path is short-circuited there).
    _windll = ctypes.windll
else:
    _windll: Any = None


@dataclass(frozen=True)
class WindowsFileMetadata:
    file_version: str | None = None
    product_version: str | None = None
    product_name: str | None = None
    original_filename: str | None = None


@dataclass(frozen=True)
class AuthenticodeResult:
    valid: bool
    publisher: str | None = None
    error: str | None = None


def read_windows_file_metadata(path: Path) -> WindowsFileMetadata:
    """Read common PE version-resource strings without third-party packages."""

    if os.name != "nt":
        return WindowsFileMetadata()
    try:
        version = _windll.version
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return WindowsFileMetadata()
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return WindowsFileMetadata()

        translations = _query_value(version, buffer, r"\VarFileInfo\Translation", raw=True)
        language, codepage = (0x0409, 0x04B0)
        if translations and len(translations) >= 4:
            language = int.from_bytes(translations[:2], "little")
            codepage = int.from_bytes(translations[2:4], "little")
        prefixes = tuple(dict.fromkeys((
            f"\\StringFileInfo\\{language:04x}{codepage:04x}",
            f"\\StringFileInfo\\{language:04x}04b0",
            r"\StringFileInfo\040904b0",
            r"\StringFileInfo\040904e4",
            r"\StringFileInfo\000004b0",
        )))
        values = {}
        for key in ("FileVersion", "ProductVersion", "ProductName", "OriginalFilename"):
            values[key] = next(
                (value for prefix in prefixes if (value := _query_value(version, buffer, f"{prefix}\\{key}"))),
                None,
            )
        return WindowsFileMetadata(
            file_version=values["FileVersion"],
            product_version=values["ProductVersion"],
            product_name=values["ProductName"],
            original_filename=values["OriginalFilename"],
        )
    except (AttributeError, OSError, ValueError):
        return WindowsFileMetadata()


def _query_value(version, buffer, key: str, *, raw: bool = False):
    pointer = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not version.VerQueryValueW(buffer, key, ctypes.byref(pointer), ctypes.byref(length)) or not pointer.value:
        return None
    if raw:
        return ctypes.string_at(pointer.value, length.value)
    value = ctypes.wstring_at(pointer.value, length.value).rstrip("\x00").strip()
    return value or None


def verify_authenticode(path: Path, *, allowed_publishers: tuple[str, ...] = ()) -> AuthenticodeResult:
    """Verify a Windows Authenticode signature with the system trust provider."""

    if os.name != "nt":
        return AuthenticodeResult(False, error="Authenticode verification is only available on Windows")
    escaped = str(path).replace("'", "''")
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    security_module = (
        system_root
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "Modules"
        / "Microsoft.PowerShell.Security"
        / "Microsoft.PowerShell.Security.psd1"
    )
    escaped_module = str(security_module).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
        f"Import-Module -Name '{escaped_module}';"
        f"$s=Get-AuthenticodeSignature -LiteralPath '{escaped}';"
        "$subject=if($s.SignerCertificate){$s.SignerCertificate.Subject}else{''};"
        "$payload=[ordered]@{status=[string]$s.Status;publisher=$subject};"
        "[Console]::Out.Write(($payload|ConvertTo-Json -Compress))"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            shell=False,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return AuthenticodeResult(False, error=f"Signature verification failed: {exc}")
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or f"PowerShell exited with code {result.returncode}"
        return AuthenticodeResult(False, error=f"Signature verification failed: {details}")
    try:
        payload = json.loads(result.stdout)
        status = str(payload.get("status", "")).strip()
        publisher = str(payload.get("publisher", "")).strip() or None
    except (json.JSONDecodeError, AttributeError):
        details = result.stderr.strip() or result.stdout.strip() or "PowerShell returned no signature result"
        return AuthenticodeResult(False, error=f"Signature verification failed: {details}")
    if status.casefold() != "valid":
        return AuthenticodeResult(False, publisher, f"Authenticode status: {status or 'unknown'}")
    if allowed_publishers and not any(item.casefold() in (publisher or "").casefold() for item in allowed_publishers):
        return AuthenticodeResult(False, publisher, "The executable publisher is not trusted for this download")
    return AuthenticodeResult(True, publisher)
