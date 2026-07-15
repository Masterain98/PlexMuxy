from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plexmuxy import __version__
from plexmuxy.audio_preview import AudioPreviewManager
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
from plexmuxy.font_cache import FontSubsetCache
from plexmuxy.integrations.plex import refresh_paths
from plexmuxy.job_store import JobStore, platform_state_path
from plexmuxy.jobs import JobRecord
from plexmuxy.overrides import apply_job_overrides, overrides_from_payload
from plexmuxy.plan_edit import plan_edits_from_payload
from plexmuxy.queue import JobQueue
from plexmuxy.serialization import job_report_to_dict, snapshot_from_dict
from plexmuxy.service import execute_plan_snapshot, run_mux_job
from plexmuxy.snapshot import validate_plan_snapshot
from plexmuxy.update_check import check_for_updates

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
    def __init__(
        self,
        state_path: Path | None = None,
        preview_root: Path | None = None,
        activation_job_id: str | None = None,
        activation_action: str = "view",
    ) -> None:
        self._window: Any = None
        self._window_maximized = False
        self._allow_window_close = False
        self._state_path = state_path
        self._job_store: JobStore | None = None
        self._job_queue: JobQueue | None = None
        self._preview = AudioPreviewManager(preview_root)
        self._active_plan_ids: dict[Path, str] = {}
        self._last_diagnostics_path: Path | None = None
        self._notifier = NativeNotifier()
        self._activation_job_id = activation_job_id
        self._activation_action = activation_action

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
                    "activation_job_id": self._activation_job_id,
                    "activation_action": self._activation_action,
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
            self._preview.close()
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
        return self._plan(payload)

    def run_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(payload, dry_run=False)

    def start_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict) or not isinstance(payload.get("snapshot"), dict):
                return self.fail("A generated plan snapshot is required")
            snapshot = snapshot_from_dict(payload["snapshot"])
            config = parse_config(snapshot.config)
            validate_plan_snapshot(snapshot, config)
            yes = bool(payload.get("yes", False))
            if (requires_delete_confirmation(config) or config.task.overwrite) and not yes:
                return self.fail("Delete or overwrite requires confirmation")
            store, queue = self._ensure_jobs()
            job_id = str(payload.get("job_id") or "")
            if job_id:
                job = store.get_job(job_id)
                if job.state != "awaiting_review" or job.plan_id != snapshot.plan_id:
                    return self.fail("Job is not awaiting review for this plan snapshot")
            else:
                job = store.create_job(snapshot.input_dir)
                store.transition(job.id, "planning", event_type="plan_started")
                store.save_plan(job.id, payload["snapshot"], {"snapshot": payload["snapshot"], "plans": []})
                job = store.transition(job.id, "awaiting_review", event_type="plan_completed")
            active = self._active_plan_ids.get(snapshot.input_dir.resolve())
            if active is not None and active != snapshot.plan_id:
                return self.fail("This plan was superseded by a newer edited snapshot")

            def execute(cancel_event: threading.Event) -> dict[str, Any]:
                def progress(event) -> None:
                    store.append_event(job.id, "progress", asdict(event))

                report = execute_plan_snapshot(
                    snapshot,
                    config,
                    yes=yes,
                    progress_callback=progress,
                    cancellation_event=cancel_event,
                )
                return job_report_to_dict(report)

            queue.submit(job.id, execute)
            return self.ok({"job_id": job.id})
        return self.guarded(run)

    def update_plan_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._plan(payload, existing_job_id=str(payload.get("job_id") or ""), edited=True)

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
            tracks = data["tracks"]
            for key in (
                "audio_filter_enabled",
                "exclude_audio_title_patterns",
                "keep_audio_languages",
                "keep_default_audio",
                "keep_all_when_unknown",
                "allow_no_audio",
            ):
                if key in payload:
                    tracks[key] = payload[key]
            cache = data["font_cache"]
            for key in ("enabled", "max_size_mb", "max_age_days"):
                payload_key = f"font_cache_{key}"
                if payload_key in payload:
                    cache[key] = payload[payload_key]
            task["cleanup_overridden"] = False
            config = parse_config(data)
            path = persist_config(config, config.source_path or resolve_config_path())
            return self.ok(config_summary(load_config(path, create_if_missing=False), self._notifier))

        return self.guarded(run)

    def save_environment_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict):
                return self.fail("Environment settings payload must be an object")
            allowed = {
                "mkvmerge_path", "ffmpeg_path", "unrar_path", "notifications_enabled",
                "updates_enabled", "plex_enabled", "plex_server_url", "plex_section_id",
                "plex_token_env", "plex_path_mappings", "font_cache_enabled",
                "font_cache_max_size_mb", "font_cache_max_age_days",
            }
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
            if "updates_enabled" in payload:
                data["updates"]["enabled"] = bool_setting(payload["updates_enabled"], "updates_enabled")
            if "font_cache_enabled" in payload:
                data["font_cache"]["enabled"] = bool_setting(payload["font_cache_enabled"], "font_cache_enabled")
            for key in ("max_size_mb", "max_age_days"):
                payload_key = f"font_cache_{key}"
                if payload_key in payload:
                    data["font_cache"][key] = payload[payload_key]
            if "plex_enabled" in payload:
                data["plex"]["enabled"] = bool_setting(payload["plex_enabled"], "plex_enabled")
            for payload_key, config_key in (
                ("plex_server_url", "server_url"),
                ("plex_section_id", "section_id"),
                ("plex_token_env", "token_env"),
            ):
                if payload_key in payload:
                    if not isinstance(payload[payload_key], str):
                        return self.fail(f"{payload_key} must be a string")
                    data["plex"][config_key] = payload[payload_key].strip()
            if "plex_path_mappings" in payload:
                mappings = payload["plex_path_mappings"]
                if not isinstance(mappings, list):
                    return self.fail("plex_path_mappings must be a list")
                data["plex"]["path_mappings"] = mappings

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
            store, _queue = self._ensure_jobs()
            job = store.get_job(str(job_id))
            progress = store.latest_event(job.id, "progress")
            return self.ok({
                "job_id": job.id,
                "status": job.state,
                "progress": progress.data if progress is not None else {},
                "error": job.error_message,
                "error_code": job.error_code,
            })
        return self.guarded(run)

    def create_audio_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if not isinstance(payload, dict) or not isinstance(payload.get("snapshot"), dict):
                return self.fail("An active plan snapshot is required for audio preview")
            source = payload.get("source_video")
            track_id = payload.get("track_id")
            if not isinstance(source, str) or not source or isinstance(track_id, bool) or not isinstance(track_id, int):
                return self.fail("Audio preview requires source_video and an integer track_id")
            snapshot = snapshot_from_dict(payload["snapshot"])
            config = parse_config(snapshot.config)
            validate_plan_snapshot(snapshot, config)
            preview = self._preview.create(
                snapshot,
                config,
                Path(source),
                track_id,
                float(payload.get("start_seconds", 60)),
                float(payload.get("duration_seconds", 15)),
            )
            return self.ok({
                "preview_id": preview.preview_id,
                "uri": preview.uri,
                "source_video": str(preview.source_video),
                "track_id": preview.track_id,
                "start_seconds": preview.start_seconds,
                "duration_seconds": preview.duration_seconds,
            })
        return self.guarded(run)

    def cancel_audio_preview(self) -> dict[str, Any]:
        return self.guarded(lambda: self.ok({"cancelled": self._preview.cancel()}))

    def delete_audio_preview(self, preview_id: str) -> dict[str, Any]:
        return self.guarded(lambda: self.ok({"deleted": self._preview.delete(str(preview_id))}))

    def get_font_cache(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config = load_or_default_config()
            cache = FontSubsetCache(config.font_cache)
            return self.ok({**asdict(cache.stats()), "enabled": config.font_cache.enabled})
        return self.guarded(run)

    def clear_font_cache(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config = load_or_default_config()
            return self.ok(asdict(FontSubsetCache(config.font_cache).clear()))
        return self.guarded(run)

    def open_font_cache_location(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config = load_or_default_config()
            path = FontSubsetCache(config.font_cache).root
            open_path(path)
            return self.ok({"path": str(path)})
        return self.guarded(run)

    def get_job_report(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            job = store.get_job(str(job_id))
            if job.state not in {"completed", "failed", "cancelled", "interrupted"}:
                return self.fail("Job is not finished")
            report = store.load_report(job.id)
            if report is None:
                return self.fail(job.error_message or "Job did not produce a report")
            return self.ok(report)
        return self.guarded(run)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            _store, queue = self._ensure_jobs()
            requested = queue.cancel(str(job_id))
            return self.ok({"job_id": str(job_id), "cancellation_requested": requested})
        return self.guarded(run)

    def load_job(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            job = store.get_job(str(job_id))
            report = store.load_report(job.id)
            if report is None:
                return self.fail("Job does not have a saved plan or report")
            return self.ok({"job": asdict(job), "report": report})
        return self.guarded(run)

    def open_job_output(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            report = store.load_report(str(job_id))
            if report is None:
                return self.fail("Job does not have a saved report")
            candidates = [
                item.get("output_path") for item in report.get("results", [])
                if isinstance(item, dict) and item.get("output_path")
            ] or [
                item.get("output_path") for item in report.get("plans", [])
                if isinstance(item, dict) and item.get("output_path")
            ]
            if not candidates:
                return self.fail("Job has no output location")
            directory = Path(str(candidates[0])).expanduser().resolve().parent
            open_path(directory)
            return self.ok({"path": str(directory)})
        return self.guarded(run)

    def export_job_diagnostics(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            job = store.get_job(str(job_id))
            context = {
                "job": asdict(job),
                "events": [asdict(event) for event in store.list_events(job.id)],
                "report": store.load_report(job.id),
            }
            stamp = time.strftime("%Y%m%d-%H%M%S")
            destination = resolve_config_path().parent / f"plexmuxy-job-{job.id[:8]}-{stamp}.zip"
            path = write_diagnostics(load_or_default_config(), destination, job_context=context)
            self._last_diagnostics_path = path
            return self.ok({"path": str(path), "directory": str(path.parent)})
        return self.guarded(run)

    def retry_plex_refresh(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            report = store.load_report(str(job_id))
            snapshot = store.load_snapshot(str(job_id))
            if report is None or snapshot is None:
                return self.fail("Job has no saved execution report and configuration")
            config = parse_config(snapshot["config"])
            if not config.plex.enabled:
                return self.fail("Plex refresh is disabled for this job")
            output_dirs = [
                Path(str(item["output_path"])).parent
                for item in report.get("results", [])
                if isinstance(item, dict) and item.get("success") and item.get("verified") and item.get("output_path")
            ]
            if not output_dirs:
                return self.fail("Job has no verified output location to refresh")
            results = refresh_paths(config.plex, output_dirs)
            payload = [{"type": "plex_refresh", **result.__dict__} for result in results]
            report.setdefault("post_actions", []).extend(payload)
            store.save_report(str(job_id), report)
            return self.ok({"results": payload})
        return self.guarded(run)

    def check_updates(self, force: bool = False) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config = load_or_default_config()
            return self.ok(asdict(check_for_updates(__version__, config.updates, force=bool(force))))
        return self.guarded(run)

    def list_jobs(self, limit: int = 100) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, queue = self._ensure_jobs()
            return self.ok({
                "paused": queue.paused,
                "jobs": [asdict(job) for job in store.list_jobs(limit=int(limit))],
            })
        return self.guarded(run)

    def pause_queue(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            _store, queue = self._ensure_jobs()
            queue.pause()
            return self.ok({"paused": True})
        return self.guarded(run)

    def resume_queue(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            _store, queue = self._ensure_jobs()
            queue.resume()
            return self.ok({"paused": False})
        return self.guarded(run)

    def reorder_job(self, job_id: str | dict[str, Any], position: int = 0) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if isinstance(job_id, dict):
                identifier = str(job_id.get("job_id") or "")
                target = int(job_id.get("position", 0))
            else:
                identifier = str(job_id)
                target = int(position)
            _store, queue = self._ensure_jobs()
            queue.reorder(identifier, target)
            return self.ok({"job_id": identifier, "position": target})
        return self.guarded(run)

    def retry_job(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            original = store.get_job(str(job_id))
            if original.state not in {"failed", "cancelled", "interrupted"}:
                return self.fail("Only failed, cancelled, or interrupted jobs can be retried")
            return self.ok(self._replan_history_job(store, original, retry_of=original.id))
        return self.guarded(run)

    def replan_job(self, job_id: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            store, _queue = self._ensure_jobs()
            original = store.get_job(str(job_id))
            return self.ok(self._replan_history_job(store, original, retry_of=original.id))
        return self.guarded(run)

    def _replan_history_job(
        self,
        store: JobStore,
        original: JobRecord,
        *,
        retry_of: str,
    ) -> dict[str, Any]:
        saved_snapshot = store.load_snapshot(original.id)
        config = (
            parse_config(saved_snapshot["config"])
            if saved_snapshot is not None and isinstance(saved_snapshot.get("config"), dict)
            else load_or_default_config()
        )
        job = store.create_job(Path(original.input_dir), retry_of=retry_of)
        store.transition(job.id, "planning", event_type="plan_started")
        report = run_mux_job(Path(original.input_dir), config, dry_run=True, yes=False)
        data = job_report_to_dict(report)
        data["job_id"] = job.id
        if report.snapshot is None or report.error is not None:
            store.save_report(job.id, data)
            store.transition(
                job.id,
                "failed",
                error_code=report.error_code or "PLAN_NOT_EXECUTABLE",
                error_message=report.error or "Plan did not produce an executable snapshot",
            )
        else:
            store.save_plan(job.id, data["snapshot"], data)
            store.transition(job.id, "awaiting_review", event_type="plan_completed")
            self._active_plan_ids[Path(original.input_dir).resolve()] = report.snapshot.plan_id
        return data

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

    def _notify_job_terminal(self, job: GuiJob | JobRecord) -> None:
        try:
            if not load_or_default_config().notifications.enabled:
                return
            status = getattr(job, "status", getattr(job, "state", "failed"))
            error = getattr(job, "error", getattr(job, "error_message", None))
            messages = {
                "completed": ("PlexMuxy job completed", "Your mux job finished successfully.", "success"),
                "cancelled": ("PlexMuxy job cancelled", "The mux job was cancelled.", "warning"),
                "interrupted": ("PlexMuxy job interrupted", "The application exited before completion.", "warning"),
                "failed": ("PlexMuxy job failed", error or "The mux job did not complete.", "error"),
            }
            title, message, tone = messages.get(status, messages["failed"])
            result = self._notifier.send(title, message, tone=tone, job_id=getattr(job, "id", getattr(job, "job_id", None)))
            if not result.sent and result.error:
                logging.info("Native job notification was not sent: %s", result.error)
        except Exception:  # noqa: BLE001 - notifications must never change a completed job result.
            logging.exception("Native job notification failed")

    def open_config_location(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            config_path = resolve_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            open_path(config_path.parent)
            return self.ok({"path": str(config_path.parent)})

        return self.guarded(run)

    def _ensure_jobs(self) -> tuple[JobStore, JobQueue]:
        if self._job_store is None:
            self._job_store = JobStore(self._state_path or platform_state_path())
        if self._job_queue is None:
            self._job_queue = JobQueue(self._job_store, terminal_callback=self._notify_job_terminal)
        return self._job_store, self._job_queue

    def _request_context(self, payload: dict[str, Any]):
        if not isinstance(payload, dict):
            raise ValueError("Payload must be an object")
        input_dir_raw = payload.get("input_dir")
        if input_dir_raw is None or str(input_dir_raw).strip() == "":
            raise ValueError("Input directory is required")
        input_dir = Path(str(input_dir_raw).strip()).expanduser().resolve()
        if not input_dir.exists():
            raise ValueError(f"Input directory does not exist: {input_dir}")
        if not input_dir.is_dir():
            raise ValueError(f"Input path is not a directory: {input_dir}")
        config = load_or_default_config()
        overrides_raw = payload.get("overrides", {})
        if overrides_raw is None:
            overrides_raw = {}
        if not isinstance(overrides_raw, dict):
            raise ValueError("overrides must be an object")
        config = apply_job_overrides(config, overrides_from_payload(overrides_raw))
        return input_dir, config, bool(payload.get("yes", False))

    def _plan(
        self,
        payload: dict[str, Any],
        *,
        existing_job_id: str = "",
        edited: bool = False,
    ) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            input_dir, config, _yes = self._request_context(payload)
            edits = plan_edits_from_payload(payload.get("plan_edits"))
            store, _queue = self._ensure_jobs()
            if existing_job_id:
                job = store.get_job(existing_job_id)
                if job.state != "awaiting_review" or Path(job.input_dir).resolve() != input_dir:
                    return self.fail("Only the current awaiting-review job can be edited")
                base_plan_id = str(payload.get("base_plan_id") or "")
                if base_plan_id and job.plan_id != base_plan_id:
                    return self.fail("The plan draft was superseded; reload it before editing")
                store.transition(job.id, "planning", event_type="plan_edit_started")
            else:
                job = store.create_job(input_dir)
                store.transition(job.id, "planning", event_type="plan_started")
            self._preview.clear()
            try:
                arguments: dict[str, Any] = {"dry_run": True, "yes": False}
                if edits:
                    arguments["plan_edits"] = edits
                report = run_mux_job(input_dir, config, **arguments)
                data = job_report_to_dict(report)
                data["job_id"] = job.id
                if report.error is not None or report.snapshot is None:
                    store.save_report(job.id, data)
                    store.transition(
                        job.id,
                        "failed",
                        error_code=report.error_code or "PLAN_NOT_EXECUTABLE",
                        error_message=report.error or "Plan did not produce an executable snapshot",
                    )
                else:
                    store.save_plan(job.id, data["snapshot"], data)
                    store.transition(
                        job.id,
                        "awaiting_review",
                        event_type="plan_edited" if edited else "plan_completed",
                        event_data={"plan_id": report.snapshot.plan_id},
                    )
                    self._active_plan_ids[input_dir] = report.snapshot.plan_id
                return self.ok(data)
            except Exception as exc:
                current = store.get_job(job.id)
                if current.state == "planning":
                    store.transition(
                        job.id,
                        "failed",
                        error_code="PLAN_FAILED",
                        error_message=str(exc),
                    )
                raise

        return self.guarded(run)

    def _run(self, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            input_dir, config, yes = self._request_context(payload)
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
        "updates": {
            "enabled": config.updates.enabled,
            "interval_hours": config.updates.interval_hours,
            "timeout_seconds": config.updates.timeout_seconds,
        },
        "plex": {
            "enabled": config.plex.enabled,
            "server_url": config.plex.server_url,
            "section_id": config.plex.section_id,
            "token_env": config.plex.token_env,
            "path_mappings": [
                {"local_root": str(mapping.local_root), "server_root": mapping.server_root}
                for mapping in config.plex.path_mappings
            ],
            "token_available": bool(os.environ.get(config.plex.token_env, "")),
        },
        "font_cache": {
            "enabled": config.font_cache.enabled,
            "max_size_mb": config.font_cache.max_size_mb,
            "max_age_days": config.font_cache.max_age_days,
        },
        "tracks": {
            "audio_filter_enabled": config.tracks.audio_filter_enabled,
            "exclude_audio_title_patterns": [*config.tracks.exclude_audio_title_patterns],
            "keep_audio_languages": [*config.tracks.keep_audio_languages],
            "keep_default_audio": config.tracks.keep_default_audio,
            "keep_all_when_unknown": config.tracks.keep_all_when_unknown,
            "allow_no_audio": config.tracks.allow_no_audio,
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


def bool_setting(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


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
