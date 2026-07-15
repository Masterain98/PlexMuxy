from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .dependencies import resolve_ffmpeg
from .models import AppConfig, MuxPlanSnapshot


class AudioPreviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioPreview:
    preview_id: str
    path: Path
    uri: str
    source_video: Path
    track_id: int
    start_seconds: float
    duration_seconds: float


class AudioPreviewManager:
    """Own short-lived ffmpeg previews outside the immutable mux transaction."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or tempfile.mkdtemp(prefix="plexmuxy-preview-")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._owns_root = root is None
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._previews: dict[str, AudioPreview] = {}

    def create(
        self,
        snapshot: MuxPlanSnapshot,
        config: AppConfig,
        source_video: Path,
        track_id: int,
        start_seconds: float = 60.0,
        duration_seconds: float = 15.0,
    ) -> AudioPreview:
        plan = _find_audio_track(snapshot, source_video, track_id)
        if not 0 <= start_seconds <= 24 * 60 * 60:
            raise AudioPreviewError("Audio preview start must be between 0 and 86400 seconds")
        if not 1 <= duration_seconds <= 20:
            raise AudioPreviewError("Audio preview duration must be between 1 and 20 seconds")
        resolution = resolve_ffmpeg(config.ffmpeg.path)
        if resolution.resolved_path is None:
            raise AudioPreviewError("ffmpeg is unavailable; audio preview is disabled")
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise AudioPreviewError("Another audio preview is already being created")
            preview_id = str(uuid.uuid4())
            output = (self.root / f"{preview_id}.m4a").resolve()
            command = [
                resolution.resolved_path,
                "-nostdin",
                "-y",
                "-ss",
                f"{start_seconds:g}",
                "-i",
                str(plan.source_video),
                "-map",
                f"0:{track_id}",
                "-t",
                f"{duration_seconds:g}",
                "-vn",
                "-c:a",
                "aac",
                str(output),
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_windows_no_window_flag(),
                )
            except OSError as exc:
                raise AudioPreviewError(f"Could not start ffmpeg: {exc}") from exc
            self._process = process
        _, stderr = process.communicate()
        with self._lock:
            if self._process is process:
                self._process = None
        if process.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
            output.unlink(missing_ok=True)
            message = (stderr or "ffmpeg did not create an audio preview").strip()
            raise AudioPreviewError(message)
        preview = AudioPreview(
            preview_id=preview_id,
            path=output,
            uri=output.as_uri(),
            source_video=plan.source_video,
            track_id=track_id,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
        )
        with self._lock:
            self._previews[preview_id] = preview
        return preview

    def cancel(self) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return False
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return True

    def delete(self, preview_id: str) -> bool:
        with self._lock:
            preview = self._previews.pop(str(preview_id), None)
        if preview is None:
            return False
        preview.path.unlink(missing_ok=True)
        return True

    def clear(self) -> None:
        self.cancel()
        with self._lock:
            previews = list(self._previews.values())
            self._previews.clear()
        for preview in previews:
            preview.path.unlink(missing_ok=True)

    def close(self) -> None:
        self.clear()
        if self._owns_root:
            shutil.rmtree(self.root, ignore_errors=True)


def _find_audio_track(snapshot: MuxPlanSnapshot, source_video: Path, track_id: int):
    source = source_video.expanduser().resolve()
    plans = [plan for plan in snapshot.plans if plan.source_video.resolve() == source]
    if len(plans) != 1:
        raise AudioPreviewError("Audio preview source is not part of the active plan")
    plan = plans[0]
    matches = [track for track in plan.source_tracks if track.id == track_id and track.type == "audio"]
    if len(matches) != 1:
        raise AudioPreviewError("Audio preview track is not part of the active plan")
    return plan


def _windows_no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
