from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from plexmuxy import __version__
from plexmuxy.config import ConfigError, default_config, load_config, resolve_config_path, write_default_config
from plexmuxy.muxer import resolve_mkvmerge_path
from plexmuxy.overrides import apply_job_overrides, overrides_from_payload
from plexmuxy.serialization import job_report_to_dict
from plexmuxy.service import run_mux_job


class PlexMuxyApi:
    def __init__(self) -> None:
        self.window: Any = None

    def bind_window(self, window: Any) -> None:
        self.window = window

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
            if self.window is None:
                return self.fail("Window is not ready")
            import webview

            dialog_type = getattr(getattr(webview, "FileDialog", object), "FOLDER", None)
            if dialog_type is None:
                dialog_type = getattr(webview, "FOLDER_DIALOG", None)
            result = self.window.create_file_dialog(dialog_type)
            if not result:
                return self.ok({"cancelled": True, "path": None})
            return self.ok({"cancelled": False, "path": str(result[0])})

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

            input_dir = Path(str(payload.get("input_dir", ""))).expanduser()
            if not input_dir.exists():
                return self.fail(f"Input directory does not exist: {input_dir}")
            if not input_dir.is_dir():
                return self.fail(f"Input path is not a directory: {input_dir}")

            config = load_or_default_config()
            overrides = overrides_from_payload(payload.get("overrides") or {})
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
        },
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
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
