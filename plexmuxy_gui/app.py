from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    # Python 3.13 no longer lazily imports ctypes submodules; this makes
    # ``ctypes.wintypes`` available for the icon/app-id helpers below.
    import ctypes.wintypes  # noqa: F401

    # Windows-only ctypes attributes are absent from the type stubs on other
    # platforms. Expose them as module globals so the helpers below type-check
    # cross-platform while keeping their runtime no-op behaviour on non-Windows.
    _windll = ctypes.windll
    _wintypes = ctypes.wintypes
    _HRESULT = ctypes.HRESULT
    _WINFUNCTYPE = ctypes.WINFUNCTYPE
else:
    _windll: Any = None
    _wintypes: Any = None
    _HRESULT: Any = None
    _WINFUNCTYPE: Any = None

from plexmuxy.logging_utils import configure_logging

from .activation import parse_activation_args
from .api import PlexMuxyApi

WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
GUI_EXTRA_MESSAGE = 'PlexMuxy GUI requires optional dependencies. Install with `pip install -e ".[gui]"`.'
WEBVIEW2_ERROR_MARKERS = (
    "webview2",
    "edge chromium",
    "edgechromium",
    "corewebview2",
    "icorewebview2",
)
EXPOSED_API_METHODS = (
    "cancel_job",
    "choose_dependency",
    "choose_directory",
    "choose_external_track",
    "clear_jobs",
    "close_window",
    "delete_job",
    "export_diagnostics",
    "export_job_diagnostics",
    "get_job_diagnostics",
    "check_updates",
    "create_audio_preview",
    "delete_audio_preview",
    "cancel_audio_preview",
    "detect_dependency",
    "get_app_info",
    "get_job_report",
    "get_job_status",
    "get_preferences",
    "list_jobs",
    "load_job",
    "load_config",
    "install_unrar_from_rarlab",
    "minimize_window",
    "open_config_location",
    "open_diagnostics_location",
    "open_job_output",
    "open_project_link",
    "pause_queue",
    "plan_job",
    "reset_dependency_path",
    "reorder_job",
    "replan_job",
    "resume_queue",
    "retry_job",
    "retry_plex_refresh",
    "save_environment_settings",
    "save_preferences",
    "save_settings",
    "start_job",
    "test_notification",
    "update_plan_draft",
    "toggle_maximize_window",
)


def static_path(name: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / "plexmuxy_gui" / "static" / name)
    return str(Path(__file__).resolve().parent / "static" / name)


_WINDOW_TITLE = "PlexMuxy"
_APP_USER_MODEL_ID = "com.plexmuxy.gui"


def _set_windows_app_id(app_id: str) -> None:
    """Group the taskbar button under a stable identity instead of python.exe."""
    try:
        shell32 = _windll.shell32
    except AttributeError:
        return
    try:
        set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [_wintypes.LPCWSTR]
        set_app_id.restype = _HRESULT
        set_app_id(app_id)
    except Exception:  # noqa: BLE001 - cosmetic; never block startup.
        pass


def _apply_window_icon_when_ready(icon_path: str) -> None:
    """Apply our icon once pywebview has created the native window.

    pywebview only honors ``icon`` on GTK/Qt back-ends, so on Windows the
    edgechromium window keeps the host process icon (python.exe in dev mode).
    We poll for the window and set the icon directly on its native handle.
    """
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if _set_native_window_icon(icon_path):
            return
        time.sleep(0.2)


def _set_native_window_icon(icon_path: str) -> bool:
    """Set the big/small icons on the PlexMuxy top-level window. Returns True if applied."""
    try:
        user32 = _windll.user32
    except AttributeError:
        return False

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    WM_SETICON = 0x0080
    ICON_SMALL, ICON_BIG = 0, 1

    load_image = user32.LoadImageW
    load_image.argtypes = [
        _wintypes.HANDLE,
        _wintypes.LPCWSTR,
        _wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        _wintypes.UINT,
    ]
    load_image.restype = _wintypes.HANDLE

    big = load_image(0, icon_path, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
    if not big:
        big = load_image(0, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
    small = load_image(0, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
    if not small:
        small = big
    if not (big or small):
        return False

    send_message = user32.SendMessageW
    send_message.argtypes = [
        _wintypes.HWND,
        _wintypes.UINT,
        _wintypes.WPARAM,
        _wintypes.LPARAM,
    ]
    send_message.restype = _wintypes.LPARAM

    get_window_thread_process_id = user32.GetWindowThreadProcessId
    get_window_thread_process_id.argtypes = [_wintypes.HWND, ctypes.POINTER(_wintypes.DWORD)]
    get_window_thread_process_id.restype = _wintypes.DWORD

    get_window_text_length = user32.GetWindowTextLengthW
    get_window_text_length.argtypes = [_wintypes.HWND]
    get_window_text_length.restype = ctypes.c_int

    get_window_text = user32.GetWindowTextW
    get_window_text.argtypes = [_wintypes.HWND, _wintypes.LPWSTR, ctypes.c_int]
    get_window_text.restype = ctypes.c_int

    enum_windows = user32.EnumWindows
    enum_proc = _WINFUNCTYPE(ctypes.c_bool, _wintypes.HWND, _wintypes.LPARAM)
    pid = os.getpid()
    applied = False

    def _match(hwnd, _lparam):
        nonlocal applied
        owner = _wintypes.DWORD()
        get_window_thread_process_id(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        length = get_window_text_length(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        get_window_text(hwnd, buffer, length + 1)
        if buffer.value != _WINDOW_TITLE:
            return True
        if big:
            send_message(hwnd, WM_SETICON, ICON_BIG, big)
        if small:
            send_message(hwnd, WM_SETICON, ICON_SMALL, small)
        applied = True
        return False

    try:
        enum_windows(enum_proc(_match), 0)
    except Exception:  # noqa: BLE001 - cosmetic; never block startup.
        return False
    return applied


def start() -> None:
    enable_per_monitor_v2()
    configure_logging(verbose=os.environ.get("PLEXMUXY_GUI_DEBUG") == "1", json_log=True)
    webview = import_webview()
    debug = os.environ.get("PLEXMUXY_GUI_DEBUG") == "1"
    activation = parse_activation_args(sys.argv[1:])
    api = PlexMuxyApi(
        activation_job_id=activation.job_id if activation else None,
        activation_action=activation.action if activation else "view",
    )

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_DOWNLOADS"] = False

    icon_path = static_path("assets/plexmuxy-app.ico")
    icon_thread = None
    if sys.platform == "win32":
        # pywebview only applies `icon` on GTK/Qt; on Windows the edgechromium
        # window keeps the host process icon (python.exe in dev mode). Set our
        # identity up front and patch the native icon once the window exists.
        _set_windows_app_id(_APP_USER_MODEL_ID)
        icon_thread = threading.Thread(
            target=_apply_window_icon_when_ready,
            args=(icon_path,),
            name="plexmuxy-gui-icon",
            daemon=True,
        )

    window = webview.create_window(
        title=_WINDOW_TITLE,
        url=static_path("index.html"),
        js_api=None,
        width=1280,
        height=800,
        min_size=(960, 640),
        frameless=True,
        easy_drag=False,
        shadow=True,
        background_color="#1c1c1c",
        text_select=True,
        confirm_close=False,
    )
    api.bind_window(window)
    window.expose(*(getattr(api, name) for name in EXPOSED_API_METHODS))

    if icon_thread is not None:
        icon_thread.start()

    try:
        if sys.platform == "win32":
            webview.start(debug=debug, gui="edgechromium", http_server=True, icon=icon_path)
        else:
            webview.start(debug=debug, http_server=True, icon=icon_path)
    except Exception as exc:  # noqa: BLE001 - desktop startup should fail cleanly from CLI/script entry points.
        if sys.platform == "win32" and is_webview2_missing_error(exc):
            raise RuntimeError(
                "PlexMuxy GUI requires Microsoft Edge WebView2 Runtime.\n\n"
                "Windows 11 usually includes it. Some Windows 10 devices may need a manual install.\n\n"
                f"Download: {WEBVIEW2_DOWNLOAD_URL}"
            ) from exc
        raise RuntimeError(f"PlexMuxy GUI could not start: {exc}") from exc


def main() -> None:
    if sys.argv[1:] == ["--smoke-test"]:
        run_frozen_smoke_test()
        return
    try:
        start()
    except RuntimeError as exc:
        print(f"GUI mode is unavailable in this environment: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def run_frozen_smoke_test() -> None:
    required = [
        "index.html", "app.js", "app.css", "i18n.js",
        "locales/en.json", "locales/zh-CN.json", "assets/plexmuxy-app.ico",
    ]
    missing = [name for name in required if not Path(static_path(name)).is_file()]
    if missing:
        raise RuntimeError(f"Frozen GUI resources are missing: {', '.join(missing)}")
    for name in ("locales/en.json", "locales/zh-CN.json"):
        value = json.loads(Path(static_path(name)).read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not value:
            raise RuntimeError(f"Frozen GUI locale is invalid: {name}")
    import_webview()


def import_webview():
    try:
        import webview
    except ImportError as exc:
        if is_missing_webview_import(exc):
            raise RuntimeError(GUI_EXTRA_MESSAGE) from exc
        raise
    return webview


def is_missing_webview_import(exc: ImportError) -> bool:
    return exc.name == "webview" or "webview" in str(exc).lower()


def is_webview2_missing_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in WEBVIEW2_ERROR_MARKERS)


def enable_per_monitor_v2() -> bool:
    """Request Per-Monitor V2 scaling before any native GUI objects are created."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_awareness = user32.SetProcessDpiAwarenessContext
        set_awareness.argtypes = [ctypes.c_void_p]
        set_awareness.restype = ctypes.c_bool
        return bool(set_awareness(ctypes.c_void_p(-4)))
    except (AttributeError, OSError):
        # Packaged Windows builds also carry a PerMonitorV2 manifest. Older
        # Windows releases can safely continue with their manifest/default DPI mode.
        return False


if __name__ == "__main__":
    main()
