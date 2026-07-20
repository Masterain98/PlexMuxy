import hashlib
import json
import os
import zipfile

import pytest

from plexmuxy.config import config_to_dict, default_config, parse_config
from plexmuxy.errors import StalePlanError
from plexmuxy.models import (
    AttachmentPlan,
    FileSnapshot,
    FontFaceRef,
    FontSubsetGroupIntent,
    FontSubsetIntent,
    MuxPlan,
    MuxPlanSnapshot,
    SubtitleTrackPlan,
)
from plexmuxy.serialization import snapshot_from_dict, snapshot_to_dict
from plexmuxy.snapshot import calculate_config_hash, create_plan_snapshot, validate_plan_snapshot


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def subtitle_track(path):
    return SubtitleTrackPlan(path, "chs", "chi", "zh-Hans", True, False, "exact")


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


def _collapse_whole_floats(value):
    # Mirror the GUI/UI bridge, where JavaScript serializes whole-number floats
    # (e.g. 3.0) as ints (3) on the snapshot round-trip.
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _collapse_whole_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_collapse_whole_floats(item) for item in value]
    return value


def test_config_hash_is_invariant_to_int_float_collapse():
    config_data = config_to_dict(default_config())
    assert isinstance(config_data["updates"]["timeout_seconds"], float)

    collapsed = _collapse_whole_floats(config_data)

    assert isinstance(collapsed["updates"]["timeout_seconds"], int)
    assert calculate_config_hash(config_data) == calculate_config_hash(collapsed)


def test_validate_accepts_snapshot_after_bridge_int_float_collapse(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)

    bridged = snapshot_from_dict(_collapse_whole_floats(snapshot_to_dict(snapshot)))

    validate_plan_snapshot(bridged, parse_config(bridged.config))


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


def test_schema3_tracks_direct_font_and_subtitle_digests(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    font = tmp_path / "Fonts" / "Demo.ttf"
    font.parent.mkdir()
    video.write_bytes(b"video")
    subtitle.write_bytes(b"subtitle")
    font.write_bytes(b"font-one")
    face = FontFaceRef(
        source_path=font,
        face_index=0,
        source_digest=sha256(font.read_bytes()),
        family_names=("Demo",),
        typographic_family_names=(),
        subfamily_names=("Regular",),
        full_names=("Demo Regular",),
        postscript_names=("Demo-Regular",),
        weight=400,
        width=5,
        italic=False,
        unicode_codepoints=(0x20, 0x41),
        outline_type="truetype",
    )
    intent = FontSubsetIntent(
        analyzer_version=1,
        subset_profile_version=1,
        groups=(FontSubsetGroupIntent(("Demo",), "PMX_DIRECT", (face,), ((0x20, 0x20), (0x41, 0x41))),),
        subtitle_digests=((subtitle, sha256(subtitle.read_bytes())),),
    )
    config = default_config()
    config.font.mode = "subset"
    plan = MuxPlan(
        video,
        tmp_path / "Example_Plex.mkv",
        subtitle_tracks=[subtitle_track(subtitle)],
        font_subset_intent=intent,
    )
    snapshot = create_plan_snapshot(tmp_path, [plan], config)

    tracked = {item.path: item for item in snapshot.files}
    assert snapshot.schema_version == 3
    assert tracked[subtitle.resolve()].sha256 == sha256(subtitle.read_bytes())
    assert tracked[font.resolve()].sha256 == face.source_digest
    validate_plan_snapshot(snapshot, config)

    font_snapshot = tracked[font.resolve()]
    original_stat = font.stat()
    font.write_bytes(b"font-two")  # Same size; reset mtime to prove digest validation is independent.
    os.utime(font, ns=(original_stat.st_atime_ns, font_snapshot.modified_time_ns))
    with pytest.raises(StalePlanError, match="digest changed"):
        validate_plan_snapshot(snapshot, config)


def test_schema3_tracks_archive_not_future_extraction_path(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    archive = tmp_path / "Fonts.zip"
    future_font = tmp_path / "Fonts" / "Demo.ttc"
    video.write_bytes(b"video")
    subtitle.write_bytes(b"subtitle")
    archive.write_bytes(b"archive-one")
    face = FontFaceRef(
        source_path=None,
        archive_path=archive,
        archive_member="nested/Demo.ttc",
        archive_digest=sha256(archive.read_bytes()),
        face_index=3,
        source_digest=sha256(b"font member payload"),
        family_names=("Demo",),
        typographic_family_names=(),
        subfamily_names=("Italic",),
        full_names=("Demo Italic",),
        postscript_names=("Demo-Italic",),
        weight=400,
        width=5,
        italic=True,
        unicode_codepoints=(0x20, 0x4E00),
        outline_type="truetype",
    )
    intent = FontSubsetIntent(
        analyzer_version=1,
        subset_profile_version=1,
        groups=(FontSubsetGroupIntent(("Demo",), "PMX_ARCHIVE", (face,), ((0x20, 0x20), (0x4E00, 0x4E00))),),
        subtitle_digests=((subtitle, sha256(subtitle.read_bytes())),),
    )
    config = default_config()
    config.font.mode = "subset"
    plan = MuxPlan(
        video,
        tmp_path / "Example_Plex.mkv",
        subtitle_tracks=[subtitle_track(subtitle)],
        font_subset_intent=intent,
    )
    snapshot = create_plan_snapshot(tmp_path, [plan], config, extra_inputs=[archive])

    tracked = {item.path for item in snapshot.files}
    assert archive.resolve() in tracked
    assert future_font.resolve() not in tracked
    validate_plan_snapshot(snapshot, config)

    archive_snapshot = next(item for item in snapshot.files if item.path == archive.resolve())
    original_stat = archive.stat()
    archive.write_bytes(b"archive-two")
    os.utime(archive, ns=(original_stat.st_atime_ns, archive_snapshot.modified_time_ns))
    with pytest.raises(StalePlanError, match="digest changed"):
        validate_plan_snapshot(snapshot, config)


def test_subset_snapshot_accepts_future_attachment_previewed_from_tracked_archive(tmp_path):
    video = tmp_path / "Example.mkv"
    archive = tmp_path / "Fonts.zip"
    future_font = tmp_path / "Fonts" / "Demo.otf"
    video.write_bytes(b"video")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Demo.otf", b"font payload")
    config = default_config()
    config.font.mode = "subset"
    plan = MuxPlan(
        video,
        tmp_path / "Example_Plex.mkv",
        attachments=[AttachmentPlan(future_font)],
        font_subset_intent=FontSubsetIntent(1, 1, (), ()),
    )
    snapshot = create_plan_snapshot(tmp_path, [plan], config, extra_inputs=[archive])

    assert future_font.resolve() not in {item.path for item in snapshot.files}
    validate_plan_snapshot(snapshot, config)


def test_subset_snapshot_rejects_untracked_font_not_in_archive_preview(tmp_path):
    video = tmp_path / "Example.mkv"
    archive = tmp_path / "Fonts.zip"
    untrusted_font = tmp_path / "Fonts" / "Injected.otf"
    video.write_bytes(b"video")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Demo.otf", b"font payload")
    config = default_config()
    config.font.mode = "subset"
    plan = MuxPlan(
        video,
        tmp_path / "Example_Plex.mkv",
        attachments=[AttachmentPlan(untrusted_font)],
        font_subset_intent=FontSubsetIntent(1, 1, (), ()),
    )
    snapshot = create_plan_snapshot(tmp_path, [plan], config, extra_inputs=[archive])

    with pytest.raises(StalePlanError, match="Untrusted attachment path"):
        validate_plan_snapshot(snapshot, config)


def test_schema1_v2_config_remains_valid_outside_subset_mode(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    plan = MuxPlan(video, tmp_path / "Example_Plex.mkv")
    raw_config = config_to_dict(default_config())
    raw_config["config_version"] = 2
    raw_config.pop("ffmpeg")
    raw_config.pop("notifications")
    raw_config["font"].pop("subset_failure_action")
    stat = video.stat()
    snapshot = MuxPlanSnapshot(
        plan_id="legacy-plan",
        config_hash=calculate_config_hash(raw_config),
        created_at="2026-01-01T00:00:00+00:00",
        input_dir=tmp_path,
        config=raw_config,
        plans=[plan],
        files=[FileSnapshot(video, stat.st_size, stat.st_mtime_ns)],
        schema_version=1,
    )

    validate_plan_snapshot(snapshot, parse_config(raw_config))

    snapshot.config["font"]["mode"] = "subset"
    snapshot.config_hash = calculate_config_hash(snapshot.config)
    with pytest.raises(StalePlanError, match="schema_version 1"):
        validate_plan_snapshot(snapshot, parse_config(snapshot.config))


def test_snapshot_rejects_mismatched_direct_font_intent_digest(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    font = tmp_path / "Demo.ttf"
    video.write_bytes(b"video")
    subtitle.write_bytes(b"subtitle")
    font.write_bytes(b"font")
    face = FontFaceRef(
        source_path=font,
        face_index=0,
        source_digest="0" * 64,
        family_names=("Demo",),
        typographic_family_names=(),
        subfamily_names=("Regular",),
        full_names=("Demo",),
        postscript_names=("Demo",),
        weight=400,
        width=5,
        italic=False,
        unicode_codepoints=(0x20,),
    )
    intent = FontSubsetIntent(
        1,
        1,
        (FontSubsetGroupIntent(("Demo",), "PMX_BAD", (face,), ((0x20, 0x20),)),),
        ((subtitle, sha256(subtitle.read_bytes())),),
    )
    config = default_config()
    config.font.mode = "subset"
    plan = MuxPlan(
        video,
        tmp_path / "Example_Plex.mkv",
        subtitle_tracks=[subtitle_track(subtitle)],
        font_subset_intent=intent,
    )
    snapshot = create_plan_snapshot(tmp_path, [plan], config)

    with pytest.raises(StalePlanError, match="Direct font digest"):
        validate_plan_snapshot(snapshot, config)
