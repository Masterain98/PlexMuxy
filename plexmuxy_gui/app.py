from __future__ import annotations

import os
import sys
from pathlib import Path

import webview

from .api import PlexMuxyApi


WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"


def static_path(name: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / "plexmuxy_gui" / "static" / name)
    return str(Path(__file__).resolve().parent / "static" / name)


def main() -> None:
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
    except Exception as exc:  # noqa: BLE001 - desktop startup should explain missing WebView2 clearly.
        if sys.platform == "win32":
            raise RuntimeError(
                "PlexMuxy GUI requires Microsoft Edge WebView2 Runtime.\n\n"
                "Windows 11 usually includes it. Some Windows 10 devices may need a manual install.\n\n"
                f"Download: {WEBVIEW2_DOWNLOAD_URL}"
            ) from exc
        raise


if __name__ == "__main__":
    main()
