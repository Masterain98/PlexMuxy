from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

    def send(self, title: str, message: str, tone: str = "info", timeout_ms: int = 6000) -> NotificationResult:
        capability = self.capability()
        if not capability.available:
            return NotificationResult(False, capability.backend, capability.reason)
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
            return NotificationResult(True, capability.backend)
        except Exception as exc:  # noqa: BLE001 - notification failures cannot break a completed job.
            return NotificationResult(False, capability.backend, str(exc))

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
