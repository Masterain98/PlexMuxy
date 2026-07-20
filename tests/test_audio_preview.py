from __future__ import annotations

from pathlib import Path

import pytest

from plexmuxy.audio_preview import AudioPreviewError, AudioPreviewManager
from plexmuxy.config import config_to_dict, default_config
from plexmuxy.dependencies import DependencyResolution
from plexmuxy.models import MuxPlan, MuxPlanSnapshot, SourceTrackInfo


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.returncode = 0
        Path(command[-1]).write_bytes(b"preview")

    def communicate(self):
        return "", ""

    def poll(self):
        return self.returncode


def snapshot(tmp_path: Path) -> tuple[MuxPlanSnapshot, Path]:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    plan = MuxPlan(
        source,
        tmp_path / "output.mkv",
        source_tracks=[SourceTrackInfo(1, "audio", codec="AAC")],
    )
    config = default_config()
    return MuxPlanSnapshot(
        plan_id="plan",
        config_hash="hash",
        created_at="now",
        input_dir=tmp_path,
        config=config_to_dict(config),
        plans=[plan],
        files=[],
    ), source


def test_preview_is_limited_to_active_plan_source_and_audio_track(monkeypatch, tmp_path):
    plan_snapshot, source = snapshot(tmp_path)
    config = default_config()
    monkeypatch.setattr(
        "plexmuxy.audio_preview.resolve_ffmpeg",
        lambda _path: DependencyResolution("ffmpeg", "", "ffmpeg", "path"),
    )
    monkeypatch.setattr("plexmuxy.audio_preview.subprocess.Popen", FakeProcess)
    manager = AudioPreviewManager(tmp_path / "previews")

    preview = manager.create(plan_snapshot, config, source, 1, 60, 15)

    assert preview.path.read_bytes() == b"preview"
    assert preview.uri.startswith("file:")
    assert manager.delete(preview.preview_id) is True
    assert not preview.path.exists()

    with pytest.raises(AudioPreviewError, match="track is not part"):
        manager.create(plan_snapshot, config, source, 99)
    with pytest.raises(AudioPreviewError, match="source is not part"):
        manager.create(plan_snapshot, config, tmp_path / "other.mkv", 1)


def test_preview_validates_duration_and_optional_dependency(monkeypatch, tmp_path):
    plan_snapshot, source = snapshot(tmp_path)
    config = default_config()
    manager = AudioPreviewManager(tmp_path / "previews")

    with pytest.raises(AudioPreviewError, match="duration"):
        manager.create(plan_snapshot, config, source, 1, duration_seconds=30)

    monkeypatch.setattr(
        "plexmuxy.audio_preview.resolve_ffmpeg",
        lambda _path: DependencyResolution("ffmpeg", "", None, "missing"),
    )
    with pytest.raises(AudioPreviewError, match="unavailable"):
        manager.create(plan_snapshot, config, source, 1)
