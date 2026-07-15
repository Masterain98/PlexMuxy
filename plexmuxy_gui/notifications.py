from __future__ import annotations

import base64
import html
import os
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_USER_MODEL_ID = "com.plexmuxy.gui"


@dataclass(frozen=True)
class NotificationCapability:
    available: bool
    backend: str
    reason: str | None = None


@dataclass(frozen=True)
class NotificationResult:
    sent: bool
    backend: str
    error: str | None = None


class NativeNotifier:
    """Small native notification adapter with no extra runtime dependency.

    The Windows backend uses the WinForms ``NotifyIcon`` API already shipped
    with pywebview's Windows runtime.  Keeping each icon alive for the balloon's
    lifetime is essential; otherwise Windows discards the notification before
    it becomes visible.
    """

    def __init__(self, icon_path: str | Path | None = None) -> None:
        self.icon_path = Path(icon_path) if icon_path else _default_icon_path()
        self._active: list[tuple[Any, Any]] = []
        self._lock = threading.Lock()

    def capability(self) -> NotificationCapability:
        if os.name != "nt":
            return NotificationCapability(False, "unsupported", "Native notifications are currently available on Windows only")
        toast = _toast_capability()
        if toast.available:
            return toast
        try:
            import clr

            clr.AddReference("System.Drawing")
            clr.AddReference("System.Windows.Forms")
            from System.Windows.Forms import NotifyIcon  # noqa: F401
        except Exception as exc:  # noqa: BLE001 - capability checks must stay non-fatal.
            return NotificationCapability(False, "windows-notify-icon", str(exc))
        if not self.icon_path.is_file():
            return NotificationCapability(False, "windows-notify-icon", f"Notification icon is missing: {self.icon_path}")
        return NotificationCapability(True, "windows-notify-icon")

    def send(
        self,
        title: str,
        message: str,
        tone: str = "info",
        timeout_ms: int = 6000,
        job_id: str | None = None,
    ) -> NotificationResult:
        capability = self.capability()
        if not capability.available:
            return NotificationResult(False, capability.backend, capability.reason)
        if capability.backend == "windows-toast":
            toast = _send_windows_toast(title, message, job_id)
            if toast.sent:
                return toast
            # The installed identity can be temporarily unavailable after an
            # Explorer restart. Preserve the existing balloon fallback.
        try:
            import clr

            clr.AddReference("System.Drawing")
            clr.AddReference("System.Windows.Forms")
            from System.Drawing import Icon
            from System.Windows.Forms import NotifyIcon, ToolTipIcon

            icon = Icon(str(self.icon_path))
            notification = NotifyIcon()
            notification.Icon = icon
            notification.Text = _truncate(title or "PlexMuxy", 63)
            notification.Visible = True
            level = {
                "error": ToolTipIcon.Error,
                "warning": ToolTipIcon.Warning,
                "warn": ToolTipIcon.Warning,
                "success": ToolTipIcon.Info,
                "info": ToolTipIcon.Info,
            }.get(str(tone).casefold(), ToolTipIcon.Info)
            notification.ShowBalloonTip(
                max(1000, min(int(timeout_ms), 30000)),
                _truncate(title or "PlexMuxy", 127),
                _truncate(message, 255),
                level,
            )
            with self._lock:
                self._active.append((notification, icon))
            timer = threading.Timer(max(timeout_ms / 1000 + 2, 3), self._dispose, args=(notification, icon))
            timer.daemon = True
            timer.start()
            return NotificationResult(True, "windows-notify-icon")
        except Exception as exc:  # noqa: BLE001 - notification failures cannot break a completed job.
            return NotificationResult(False, "windows-notify-icon", str(exc))

    def close(self) -> None:
        with self._lock:
            active, self._active = self._active, []
        for notification, icon in active:
            _dispose_objects(notification, icon)

    def _dispose(self, notification: Any, icon: Any) -> None:
        with self._lock:
            try:
                self._active.remove((notification, icon))
            except ValueError:
                return
        _dispose_objects(notification, icon)


def _default_icon_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "plexmuxy_gui" / "static" / "assets" / "plexmuxy-app.ico"
    return Path(__file__).resolve().parent / "static" / "assets" / "plexmuxy-app.ico"


def _dispose_objects(notification: Any, icon: Any) -> None:
    try:
        notification.Visible = False
        notification.Dispose()
    finally:
        icon.Dispose()


def _truncate(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: max(limit - 1, 0)]}…"


def _toast_capability() -> NotificationCapability:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return NotificationCapability(False, "windows-toast", "Installed application identity is unavailable")
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return NotificationCapability(False, "windows-toast", "Windows PowerShell is unavailable")
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\plexmuxy"):
            pass
    except OSError:
        return NotificationCapability(False, "windows-toast", "PlexMuxy protocol registration is unavailable")
    return NotificationCapability(True, "windows-toast")


def _send_windows_toast(title: str, message: str, job_id: str | None) -> NotificationResult:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return NotificationResult(False, "windows-toast", "Windows PowerShell is unavailable")
    activation = ""
    actions = ""
    if job_id is not None:
        try:
            canonical_job_id = str(uuid.UUID(str(job_id)))
        except ValueError:
            canonical_job_id = ""
        if canonical_job_id:
            view_uri = f"plexmuxy://job/{canonical_job_id}"
            output_uri = f"{view_uri}?action=output"
            activation = f' launch="{view_uri}" activationType="protocol"'
            actions = (
                "<actions>"
                f'<action content="Open task" arguments="{view_uri}" activationType="protocol"/>'
                f'<action content="Open output" arguments="{output_uri}" activationType="protocol"/>'
                "</actions>"
            )
    xml = (
        f"<toast{activation}><visual><binding template=\"ToastGeneric\">"
        f"<text>{html.escape(_truncate(title or 'PlexMuxy', 127))}</text>"
        f"<text>{html.escape(_truncate(message, 512))}</text>"
        f"</binding></visual>{actions}</toast>"
    )
    encoded_xml = base64.b64encode(xml.encode("utf-8")).decode("ascii")
    script = f"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xmlText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_xml}'))
$document = [Windows.Data.Xml.Dom.XmlDocument]::new()
$document.LoadXml($xmlText)
$toast = [Windows.UI.Notifications.ToastNotification]::new($document)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_USER_MODEL_ID}').Show($toast)
""".strip()
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        completed = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
            capture_output=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            return NotificationResult(True, "windows-toast")
        error = completed.stderr.decode("utf-8", errors="replace").strip()[:500]
        return NotificationResult(False, "windows-toast", error or f"PowerShell exited with {completed.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return NotificationResult(False, "windows-toast", str(exc))
