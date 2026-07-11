from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import platform_config_path


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def configure_logging(verbose: bool = False, json_log: bool = False) -> Path:
    log_dir = platform_config_path().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{os.getpid()}"
    log_path = log_dir / f"{stem}.log"
    text_handler = logging.FileHandler(log_path, encoding="utf-8")
    text_handler.setFormatter(
        logging.Formatter("%(levelname)s:%(asctime)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    handlers: list[logging.Handler] = [text_handler]
    if json_log:
        json_handler = logging.FileHandler(log_dir / f"{stem}.jsonl", encoding="utf-8")
        json_handler.setFormatter(JsonLogFormatter())
        handlers.append(json_handler)
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers, force=True)
    return log_path
