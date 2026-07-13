from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plexmuxy import __version__
from plexmuxy.config import (
    ConfigError,
    config_to_dict,
    default_config,
    load_config,
    parse_config,
    resolve_config_path,
    write_default_config,
)
from plexmuxy.config import (
    save_config as persist_config,
)
from plexmuxy.diagnostics import export_diagnostics as write_diagnostics
from plexmuxy.muxer import resolve_mkvmerge_path
from plexmuxy.overrides import apply_job_overrides, overrides_from_payload
from plexmuxy.serialization import job_report_to_dict, snapshot_from_dict
from plexmuxy.service import execute_plan_snapshot, run_mux_job


@dataclass
class GuiJob:
    job_id: str
    status: str = "queued"
    progress: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    cancel_event: threading.Event = field(default_factory=threading.Event)


class PlexMuxyApi:
    def __init__(self) -> None:
        self._window: Any = None
        self._window_maximized = False
        self._jobs: dict[str, GuiJob] = {}
        self._jobs_lock = threading.Lock()

    def bind_window(self, window: Any) -> None:
        self._window = window
        events = getattr(window, "events", None)
        if events is not None:
            events.maximized += self._handle_window_maximized
            events.restored += self._handle_window_restored

    def _handle_window_maximized(self) -> None:
        self._window_maximized = True

    def _handle_window_restored(self) -> None:
        self._window_maximized = False

    def ok(self, data: Any | None = None) -> dict[str, Any]:
        return {"ok": True, "data": data if data is not None else {}}

    def fail(self, error: str) -> dict[str, Any]:
        return {"ok": False, "error": error}

    def guarded(self, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return callback()
        except ConfigError as exc:
            return self.fail(f"Config error: {exc}")
        except Exception as exc:  # noqa: BLE001 - GUI bridge must never leak Python exceptions.
            logging.exception("Unhandled GUI API error")
            return self.fail(str(exc))

    def get_app_info(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config_path = resolve_config_path()
            return self.ok(
                {
                    "name": "PlexMuxy",
                    "version": __version__,
                    "platform": platform.platform(),
                    "config_path": str(config_path),
                    "config_exists": config_path.exists(),
                }
            )

        return self.guarded(run)

    def choose_directory(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if self._window is None:
                return self.fail("Window is not ready")
            import webview

            dialog_type = getattr(getattr(webview, "FileDialog", object), "FOLDER", None)
            if dialog_type is None:
                dialog_type = getattr(webview, "FOLDER_DIALOG", None)
            if dialog_type is None:
                return self.fail("Folder picker is not available in this pywebview version")
            result = self._window.create_file_dialog(dialog_type)
            if not result:
                return self.ok({"cancelled": True, "path": None})
            return self.ok({"cancelled": False, "path": str(result[0])})

        return self.guarded(run)

    def minimize_window(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if self._window is None:
                return self.fail("Window is not ready")
            self._window.minimize()
            return self.ok()

        return self.guarded(run)

    def toggle_maximize_window(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if self._window is None:
                return self.fail("Window is not ready")
            if self._window_maximized:
                self._window.restore()
                self._window_maximized = False
            else:
                self._window.maximize()
                self._window_maximized = True
            return self.ok({"maximized": self._window_maximized})

        return self.guarded(run)

    def close_window(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if self._window is None:
                return self.fail("Window is not ready")

            # Let pywebview deliver this bridge response before closing its WebView.
            timer = threading.Timer(0.1, self._window.destroy)
            timer.daemon = True
            timer.start()
            return self.ok()

        return self.guarded(run)

    def load_config(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config = load_or_default_config()
            return self.ok(config_summary(config))

        return self.guarded(run)

    def init_config(self, force: bool = False) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config_path = resolve_config_path()
            if config_path.exists() and not force:
                return self.fail(f"Config already exists: {config_path}")
            created = write_default_config(config_path)
            config = load_config(created, create_if_missing=False)
            return self.ok(config_summary(config))

        return self.guarded(run)

    def plan_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(payload, dry_run=True)

    def run_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(payload, dry_run=False)

    def start_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict) or not isinstance(payload.get("snapshot"), dict):
                return self.fail("A generated plan snapshot is required")
            snapshot = snapshot_from_dict(payload["snapshot"])
            config = parse_config(snapshot.config)
            yes = bool(payload.get("yes", False))
            if (requires_delete_confirmation(config) or config.task.overwrite) and not yes:
                return self.fail("Delete or overwrite requires confirmation")
            job = GuiJob(job_id=str(uuid.uuid4()))
            with self._jobs_lock:
                self._jobs[job.job_id] = job
                self._prune_jobs()
            threading.Thread(
                target=self._execute_background_job,
                args=(job, snapshot, config, yes),
                name=f"plexmuxy-gui-{job.job_id[:8]}",
                daemon=True,
            ).start()
            return self.ok({"job_id": job.job_id})
        return self.guarded(run)

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict):
                return self.fail("Settings payload must be an object")
            data = config_to_dict(load_or_default_config())
            task = data["task"]
            for key in ("cleanup", "extra_dir", "output_suffix", "name_strategy", "overwrite"):
                if key in payload:
                    task[key] = payload[key]
            for key in ("output_dir", "name_template"):
                if key in payload:
                    task[key] = payload[key] or None
            task["cleanup_overridden"] = False
            config = parse_config(data)
            path = persist_config(config, config.source_path or resolve_config_path())
            return self.ok(config_summary(load_config(path, create_if_missing=False)))

        return self.guarded(run)

    def export_diagnostics(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            destination = resolve_config_path().parent / f"plexmuxy-diagnostics-{stamp}.zip"
            path = write_diagnostics(load_or_default_config(), destination)
            return self.ok({"path": str(path)})

        return self.guarded(run)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            job = self._find_job(job_id)
            return self.ok({
                "job_id": job.job_id, "status": job.status, "progress": dict(job.progress),
                "error": job.error, "elapsed_seconds": round(time.monotonic() - job.created_at, 1),
            })
        return self.guarded(run)

    def get_job_report(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            job = self._find_job(job_id)
            if job.status not in {"completed", "failed", "cancelled"}:
                return self.fail("Job is not finished")
            if job.report is None:
                return self.fail(job.error or "Job did not produce a report")
            return self.ok(job.report)
        return self.guarded(run)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            job = self._find_job(job_id)
            job.cancel_event.set()
            return self.ok({"job_id": job.job_id, "cancellation_requested": True})
        return self.guarded(run)

    def _find_job(self, job_id: str) -> GuiJob:
        with self._jobs_lock:
            job = self._jobs.get(str(job_id))
        if job is None:
            raise ValueError("Unknown job_id")
        return job

    def _execute_background_job(self, job: GuiJob, snapshot, config, yes: bool) -> None:
        job.status = "running"
        try:
            def progress(event) -> None:
                job.status = event.phase
                job.progress = asdict(event)

            report = execute_plan_snapshot(
                snapshot, config, yes=yes, progress_callback=progress,
                cancellation_event=job.cancel_event,
            )
            job.report = job_report_to_dict(report)
            if report.cancelled:
                job.status = "cancelled"
            elif report.error is not None:
                job.status = "failed"
                job.error = report.error
            else:
                job.status = "completed"
        except Exception as exc:  # noqa: BLE001
            logging.exception("Background GUI job failed")
            job.status = "failed"
            job.error = str(exc)

    def _prune_jobs(self) -> None:
        if len(self._jobs) <= 20:
            return
        finished = [key for key, job in self._jobs.items() if job.status in {"completed", "failed", "cancelled"}]
        for key in finished[: len(self._jobs) - 20]:
            self._jobs.pop(key, None)

    def open_config_location(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config_path = resolve_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            open_path(config_path.parent)
            return self.ok({"path": str(config_path.parent)})

        return self.guarded(run)

    def _run(self, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict):
                return self.fail("Payload must be an object")

            input_dir_raw = payload.get("input_dir")
            if input_dir_raw is None or str(input_dir_raw).strip() == "":
                return self.fail("Input directory is required")
            input_dir = Path(str(input_dir_raw).strip()).expanduser().resolve()
            if not input_dir.exists():
                return self.fail(f"Input directory does not exist: {input_dir}")
            if not input_dir.is_dir():
                return self.fail(f"Input path is not a directory: {input_dir}")

            config = load_or_default_config()
            overrides_raw = payload.get("overrides", {})
            if overrides_raw is None:
                overrides_raw = {}
            if not isinstance(overrides_raw, dict):
                return self.fail("overrides must be an object")
            overrides = overrides_from_payload(overrides_raw)
            config = apply_job_overrides(config, overrides)
            yes = bool(payload.get("yes", False))
            if not dry_run and requires_delete_confirmation(config) and not yes:
                return self.fail("Delete cleanup requires confirmation")

            report = run_mux_job(input_dir, config, dry_run=dry_run, yes=yes)
            return self.ok(job_report_to_dict(report))

        return self.guarded(run)


def load_or_default_config():
    config_path = resolve_config_path()
    if config_path.exists():
        return load_config(config_path, create_if_missing=False)
    config = default_config()
    config.source_path = config_path
    return config


def config_summary(config) -> dict[str, Any]:
    mkvmerge_path = resolve_mkvmerge_path(config)
    source_path = config.source_path or resolve_config_path()
    return {
        "config_path": str(source_path),
        "config_exists": Path(source_path).exists(),
        "mkvmerge": {
            "configured_path": config.mkvmerge.path,
            "resolved_path": mkvmerge_path,
            "available": mkvmerge_path is not None,
        },
        "task": {
            "cleanup": config.task.cleanup,
            "extra_dir": config.task.extra_dir,
            "output_suffix": config.task.output_suffix,
            "output_dir": str(config.task.output_dir) if config.task.output_dir is not None else "",
            "name_strategy": config.task.name_strategy,
            "name_template": config.task.name_template or "",
            "overwrite": config.task.overwrite,
            "delete_original_video": config.task.delete_original_video,
            "delete_original_audio": config.task.delete_original_audio,
            "delete_subtitle": config.task.delete_subtitle,
        },
        "media": {
            "video_extensions": [*config.media.video_extensions],
            "audio_extensions": [*config.media.audio_extensions],
            "subtitle_extensions": [*config.media.subtitle_extensions],
            "font_extensions": [*config.media.font_extensions],
            "font_archive_extensions": [*config.media.font_archive_extensions],
            "recursive": config.media.recursive,
        },
        "font": {
            "delete_fonts_after_mux": config.font.delete_fonts_after_mux,
            "unrar_path": config.font.unrar_path,
            "mode": config.font.mode,
        },
        "matching": {
            "movie_fallback": config.matching.movie_fallback,
            "minimum_confidence": config.matching.minimum_confidence,
        },
        "concurrency": {"max_parallel_mux_jobs": config.concurrency.max_parallel_mux_jobs},
    }


def requires_delete_confirmation(config) -> bool:
    return (
        config.task.cleanup == "delete"
        or config.task.delete_original_video
        or config.task.delete_original_audio
        or config.task.delete_subtitle
        or config.font.delete_fonts_after_mux
    )


def open_path(path: Path) -> None:
    if os.name == "nt":
        start_file = getattr(os, "start" + "file")
        start_file(path)
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
