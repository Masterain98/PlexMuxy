from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import platform_config_path


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        for field in (
            "job_id", "plan_id", "source_video", "phase", "error_code",
            "dependency_version", "duration_ms",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(verbose: bool = False, json_log: bool = False) -> Path:
    log_dir = platform_config_path().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _remove_expired_logs(log_dir)
    stem = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{os.getpid()}"
    log_path = log_dir / f"{stem}.log"
    text_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    text_handler.setFormatter(
        logging.Formatter("%(levelname)s:%(asctime)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    handlers: list[logging.Handler] = [text_handler]
    if json_log:
        json_handler = RotatingFileHandler(
            log_dir / f"{stem}.jsonl", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        json_handler.setFormatter(JsonLogFormatter())
        handlers.append(json_handler)
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers, force=True)
    return log_path


def _remove_expired_logs(log_dir: Path, max_age_days: int = 30) -> None:
    cutoff = time.time() - max_age_days * 86400
    for path in log_dir.glob("*.*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue
