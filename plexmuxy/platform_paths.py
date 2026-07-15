from __future__ import annotations

import os
import sys
from pathlib import Path


def platform_tools_path() -> Path:
    """Return the per-device, per-user directory for managed helper tools."""

    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return root / "PlexMuxy" / "tools"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PlexMuxy" / "tools"
    root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "plexmuxy" / "tools"
