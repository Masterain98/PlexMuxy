from __future__ import annotations

import os
import sys
from pathlib import Path

from plexmuxy.logging_utils import configure_logging

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


def static_path(name: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / "plexmuxy_gui" / "static" / name)
    return str(Path(__file__).resolve().parent / "static" / name)


def start() -> None:
    configure_logging(verbose=os.environ.get("PLEXMUXY_GUI_DEBUG") == "1", json_log=True)
    webview = import_webview()
    debug = os.environ.get("PLEXMUXY_GUI_DEBUG") == "1"
    api = PlexMuxyApi()

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_DOWNLOADS"] = False

    window = webview.create_window(
        title="PlexMuxy",
        url=static_path("index.html"),
        js_api=api,
        width=1180,
        height=760,
        min_size=(960, 640),
        background_color="#101014",
        text_select=True,
        confirm_close=True,
    )
    api.bind_window(window)

    try:
        if sys.platform == "win32":
            webview.start(debug=debug, gui="edgechromium")
        else:
            webview.start(debug=debug)
    except Exception as exc:  # noqa: BLE001 - desktop startup should fail cleanly from CLI/script entry points.
        if sys.platform == "win32" and is_webview2_missing_error(exc):
            raise RuntimeError(
                "PlexMuxy GUI requires Microsoft Edge WebView2 Runtime.\n\n"
                "Windows 11 usually includes it. Some Windows 10 devices may need a manual install.\n\n"
                f"Download: {WEBVIEW2_DOWNLOAD_URL}"
            ) from exc
        raise RuntimeError(f"PlexMuxy GUI could not start: {exc}") from exc


def main() -> None:
    try:
        start()
    except RuntimeError as exc:
        print(f"GUI mode is unavailable in this environment: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


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


if __name__ == "__main__":
    main()
