import json

import pytest

from plexmuxy.config import default_config, parse_config
from plexmuxy.errors import StalePlanError
from plexmuxy.models import MuxPlan
from plexmuxy.serialization import snapshot_from_dict, snapshot_to_dict
from plexmuxy.snapshot import create_plan_snapshot, validate_plan_snapshot


def test_snapshot_round_trip_and_validation(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    video.write_bytes(b"video")
    subtitle.write_bytes(b"subtitle")
    config = default_config()
    plan = MuxPlan(video, tmp_path / "Example_Plex.mkv", cleanup_candidates=[video])
    snapshot = create_plan_snapshot(tmp_path, [plan], config, [subtitle])

    restored = snapshot_from_dict(json.loads(json.dumps(snapshot_to_dict(snapshot))))

    validate_plan_snapshot(restored, parse_config(restored.config))
    assert restored.plan_id == snapshot.plan_id


def test_snapshot_rejects_changed_input(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)
    video.write_bytes(b"changed")

    with pytest.raises(StalePlanError, match="changed"):
        validate_plan_snapshot(snapshot, config)


def test_snapshot_rejects_new_output(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    video.write_bytes(b"video")
    config = default_config()
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, output)], config)
    output.write_bytes(b"unexpected")

    with pytest.raises(StalePlanError, match="appeared"):
        validate_plan_snapshot(snapshot, config)


def test_snapshot_rejects_tampered_output_path(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)
    snapshot.plans[0].output_path = tmp_path / "elsewhere.mkv"

    with pytest.raises(StalePlanError, match="does not match"):
        validate_plan_snapshot(snapshot, config)
