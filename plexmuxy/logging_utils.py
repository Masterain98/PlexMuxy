from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from .config import platform_config_path


def configure_logging(verbose: bool = False) -> Path:
    log_dir = platform_config_path().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{os.getpid()}.log"
    logging.basicConfig(
        filename=log_path,
        encoding="utf-8",
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s:%(asctime)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    return log_path
