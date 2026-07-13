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
from plexmuxy.dependencies import (
    DependencyResolution,
    resolve_ffmpeg,
    resolve_mkvmerge,
    resolve_unrar,
)
from plexmuxy.diagnostics import export_diagnostics as write_diagnostics
from plexmuxy.overrides import apply_job_overrides, overrides_from_payload
from plexmuxy.serialization import job_report_to_dict, snapshot_from_dict
from plexmuxy.service import execute_plan_snapshot, run_mux_job

from .notifications import NativeNotifier

DEPENDENCY_RESOLVERS: dict[str, Callable[[str], DependencyResolution]] = {
    "mkvmerge": resolve_mkvmerge,
    "ffmpeg": resolve_ffmpeg,
    "unrar": resolve_unrar,
}
DEPENDENCY_EXECUTABLES = {
    "mkvmerge": {"mkvmerge", "mkvmerge.exe"},
    "ffmpeg": {"ffmpeg", "ffmpeg.exe"},
    "unrar": {"unrar", "unrar.exe"},
}


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
        self._allow_window_close = False
        self._jobs: dict[str, GuiJob] = {}
        self._jobs_lock = threading.Lock()
        self._last_diagnostics_path: Path | None = None
        self._notifier = NativeNotifier()

    def bind_window(self, window: Any) -> None:
        self._window = window
        events = getattr(window, "events", None)
        if events is not None:
            events.maximized += self._handle_window_maximized
            events.restored += self._handle_window_restored
            events.closing += self._handle_window_closing

    def _handle_window_maximized(self) -> None:
        self._window_maximized = True

    def _handle_window_restored(self) -> None:
        self._window_maximized = False

    def _handle_window_closing(self) -> bool | None:
        if self._allow_window_close:
            return None
        if self._window is not None:
            timer = threading.Timer(0.01, self._request_frontend_close_confirmation)
            timer.daemon = True
            timer.start()
        return False

    def _request_frontend_close_confirmation(self) -> None:
        if self._window is None:
            return
        try:
            self._window.evaluate_js("window.PlexMuxyRequestClose?.()")
        except Exception:  # noqa: BLE001 - a closing WebView may already be unavailable.
            logging.debug("Could not request the custom close dialog", exc_info=True)

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

    def choose_dependency(self, dependency: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            name = normalize_dependency_name(dependency)
            if self._window is None:
                return self.fail("Window is not ready")
            import webview

            dialog_type = getattr(getattr(webview, "FileDialog", object), "OPEN", None)
            if dialog_type is None:
                dialog_type = getattr(webview, "OPEN_DIALOG", None)
            if dialog_type is None:
                return self.fail("File picker is not available in this pywebview version")
            file_types = ("Executable files (*.exe)",) if os.name == "nt" else ("All files (*.*)",)
            result = self._window.create_file_dialog(
                dialog_type,
                allow_multiple=False,
                file_types=file_types,
            )
            if not result:
                return self.ok({"cancelled": True, "dependency": name, "path": None})
            selected = validate_dependency_path(name, str(result[0]))
            return self.ok(
                {
                    "cancelled": False,
                    "dependency": name,
                    "path": selected.resolved_path,
                    "resolution": dependency_resolution_to_dict(selected),
                }
            )

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

            self._allow_window_close = True
            self._notifier.close()
            # Let pywebview deliver this bridge response before closing its WebView.
            timer = threading.Timer(0.1, self._window.destroy)
            timer.daemon = True
            timer.start()
            return self.ok()

        return self.guarded(run)

    def load_config(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config = load_or_default_config()
            return self.ok(config_summary(config, self._notifier))

        return self.guarded(run)

    def init_config(self, force: bool = False) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config_path = resolve_config_path()
            if config_path.exists() and not force:
                return self.fail(f"Config already exists: {config_path}")
            created = write_default_config(config_path)
            config = load_config(created, create_if_missing=False)
            return self.ok(config_summary(config, self._notifier))

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
            if "font_mode" in payload:
                data["font"]["mode"] = payload["font_mode"]
            task["cleanup_overridden"] = False
            config = parse_config(data)
            path = persist_config(config, config.source_path or resolve_config_path())
            return self.ok(config_summary(load_config(path, create_if_missing=False), self._notifier))

        return self.guarded(run)

    def save_environment_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict):
                return self.fail("Environment settings payload must be an object")
            allowed = {"mkvmerge_path", "ffmpeg_path", "unrar_path", "notifications_enabled"}
            unknown = sorted(set(payload) - allowed)
            if unknown:
                return self.fail(f"Unknown environment setting(s): {', '.join(unknown)}")

            data = config_to_dict(load_or_default_config())
            for payload_key, dependency in (
                ("mkvmerge_path", "mkvmerge"),
                ("ffmpeg_path", "ffmpeg"),
                ("unrar_path", "unrar"),
            ):
                if payload_key not in payload:
                    continue
                raw_path = payload[payload_key]
                if not isinstance(raw_path, str):
                    return self.fail(f"{payload_key} must be a string")
                configured = raw_path.strip()
                if configured:
                    validate_dependency_path(dependency, configured)
                if dependency == "unrar":
                    data["font"]["unrar_path"] = configured
                else:
                    data[dependency]["path"] = configured
            if "notifications_enabled" in payload:
                enabled = payload["notifications_enabled"]
                if not isinstance(enabled, bool):
                    return self.fail("notifications_enabled must be a boolean")
                data["notifications"]["enabled"] = enabled

            config = parse_config(data)
            path = persist_config(config, config.source_path or resolve_config_path())
            return self.ok(config_summary(load_config(path, create_if_missing=False), self._notifier))

        return self.guarded(run)

    def reset_dependency_path(self, dependency: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            name = normalize_dependency_name(dependency)
            data = config_to_dict(load_or_default_config())
            if name == "unrar":
                data["font"]["unrar_path"] = ""
            else:
                data[name]["path"] = ""
            config = parse_config(data)
            path = persist_config(config, config.source_path or resolve_config_path())
            return self.ok(config_summary(load_config(path, create_if_missing=False), self._notifier))

        return self.guarded(run)

    def test_notification(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            values = payload if isinstance(payload, dict) else {}
            title = str(values.get("title") or "PlexMuxy")[:127]
            message = str(values.get("message") or "PlexMuxy notifications are ready.")[:255]
            capability = self._notifier.capability()
            if not capability.available:
                return self.ok({"capability": asdict(capability), "result": None})
            result = self._notifier.send(title, message, tone="success")
            return self.ok({"capability": asdict(capability), "result": asdict(result)})

        return self.guarded(run)

    def export_diagnostics(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            destination = resolve_config_path().parent / f"plexmuxy-diagnostics-{stamp}.zip"
            path = write_diagnostics(load_or_default_config(), destination)
            self._last_diagnostics_path = path
            return self.ok({"path": str(path), "directory": str(path.parent)})

        return self.guarded(run)

    def open_diagnostics_location(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if self._last_diagnostics_path is None:
                return self.fail("No diagnostics archive has been exported in this session")
            open_path(self._last_diagnostics_path.parent)
            return self.ok({"path": str(self._last_diagnostics_path.parent)})

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
            elif report.error is not None or report.failure_count > 0:
                job.status = "failed"
                job.error = report.error or f"{report.failure_count} mux operation(s) failed"
            else:
                job.status = "completed"
        except Exception as exc:  # noqa: BLE001
            logging.exception("Background GUI job failed")
            job.status = "failed"
            job.error = str(exc)
        finally:
            self._notify_job_terminal(job)

    def _notify_job_terminal(self, job: GuiJob) -> None:
        try:
            if not load_or_default_config().notifications.enabled:
                return
            messages = {
                "completed": ("PlexMuxy job completed", "Your mux job finished successfully.", "success"),
                "cancelled": ("PlexMuxy job cancelled", "The mux job was cancelled.", "warning"),
                "failed": ("PlexMuxy job failed", job.error or "The mux job did not complete.", "error"),
            }
            title, message, tone = messages.get(job.status, messages["failed"])
            result = self._notifier.send(title, message, tone=tone)
            if not result.sent and result.error:
                logging.info("Native job notification was not sent: %s", result.error)
        except Exception:  # noqa: BLE001 - notifications must never change a completed job result.
            logging.exception("Native job notification failed")

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


def config_summary(config, notifier: NativeNotifier | None = None) -> dict[str, Any]:
    mkvmerge = resolve_mkvmerge(config.mkvmerge.path)
    ffmpeg = resolve_ffmpeg(config.ffmpeg.path)
    unrar = resolve_unrar(config.font.unrar_path)
    capability = (notifier or NativeNotifier()).capability()
    source_path = config.source_path or resolve_config_path()
    return {
        "config_path": str(source_path),
        "config_exists": Path(source_path).exists(),
        "mkvmerge": {**dependency_resolution_to_dict(mkvmerge), "required": True},
        "ffmpeg": {**dependency_resolution_to_dict(ffmpeg), "required": False},
        "unrar": {**dependency_resolution_to_dict(unrar), "required": False},
        "notifications": {
            "enabled": config.notifications.enabled,
            "available": capability.available,
            "backend": capability.backend,
            "reason": capability.reason,
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
            "subset_failure_action": config.font.subset_failure_action,
        },
        "matching": {
            "movie_fallback": config.matching.movie_fallback,
            "minimum_confidence": config.matching.minimum_confidence,
        },
        "concurrency": {"max_parallel_mux_jobs": config.concurrency.max_parallel_mux_jobs},
    }


def normalize_dependency_name(value: str) -> str:
    name = str(value or "").strip().casefold()
    if name not in DEPENDENCY_RESOLVERS:
        raise ValueError(f"Unsupported dependency: {value}")
    return name


def validate_dependency_path(dependency: str, value: str) -> DependencyResolution:
    name = normalize_dependency_name(dependency)
    configured = str(value or "").strip()
    if not configured:
        raise ValueError(f"{name} path cannot be empty")
    resolution = DEPENDENCY_RESOLVERS[name](configured)
    if resolution.resolved_path is None:
        raise ValueError(f"The selected {name} executable could not be found")
    resolved_name = Path(resolution.resolved_path).name.casefold()
    if resolved_name not in DEPENDENCY_EXECUTABLES[name]:
        expected = ", ".join(sorted(DEPENDENCY_EXECUTABLES[name]))
        raise ValueError(f"Expected {expected}, got {resolved_name}")
    return resolution


def dependency_resolution_to_dict(resolution: DependencyResolution) -> dict[str, Any]:
    return {
        "configured_path": resolution.configured_path,
        "resolved_path": resolution.resolved_path,
        "available": resolution.available,
        "source": resolution.source,
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
