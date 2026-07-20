import json
from types import SimpleNamespace

from plexmuxy.models import AttachmentPlan, AudioTrackPlan, MuxPlan, SourceTrackInfo, SubtitleTrackPlan
from plexmuxy.muxer import verify_mux_output


def test_structural_verifier_checks_tracks_and_attachments(monkeypatch, tmp_path):
    output = tmp_path / "output.mkv"
    output.write_bytes(b"mkv")
    subtitle = SubtitleTrackPlan(tmp_path / "sub.ass", "chs Author", "chi", "zh-Hans", True, False, "exact")
    font = tmp_path / "font.ttf"
    plan = MuxPlan(tmp_path / "source.mkv", output, subtitle_tracks=[subtitle], attachments=[AttachmentPlan(font)])
    payload = {"tracks": [
        {"type": "video", "properties": {}},
        {"type": "subtitles", "properties": {"language": "chi", "language_ietf": "zh-Hans", "track_name": "chs Author", "default_track": True, "forced_track": False}},
    ], "attachments": [{
        "file_name": "font.ttf",
        "content_type": "application/x-truetype-font",
    }], "container": {"type": "Matroska"}}
    monkeypatch.setattr("plexmuxy.muxer.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""))
    result = verify_mux_output(plan, output, "mkvmerge")
    assert result.success is True
    assert result.details["video_tracks"] == 1


def test_structural_verifier_rejects_missing_video(monkeypatch, tmp_path):
    output = tmp_path / "output.mkv"
    output.write_bytes(b"mkv")
    plan = MuxPlan(tmp_path / "source.mkv", output)
    monkeypatch.setattr("plexmuxy.muxer.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout='{"tracks": [], "attachments": []}', stderr=""))
    result = verify_mux_output(plan, output, "mkvmerge")
    assert result.success is False
    assert result.error_code == "TRACK_COUNT_MISMATCH"


def test_structural_verifier_rejects_attachment_mime_mismatch(monkeypatch, tmp_path):
    output = tmp_path / "output.mkv"
    output.write_bytes(b"mkv")
    attachment = AttachmentPlan(
        tmp_path / "font.ttf",
        expected_name="font.ttf",
        expected_mime_type="application/x-truetype-font",
    )
    plan = MuxPlan(tmp_path / "source.mkv", output, attachments=[attachment])
    payload = {
        "tracks": [{"type": "video", "properties": {}}],
        "attachments": [{"file_name": "font.ttf", "content_type": "application/octet-stream"}],
    }
    monkeypatch.setattr(
        "plexmuxy.muxer.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )

    result = verify_mux_output(plan, output, "mkvmerge")

    assert result.error_code == "ATTACHMENT_PROPERTY_MISMATCH"


def test_structural_verifier_checks_exact_audio_count_and_retained_source_properties(monkeypatch, tmp_path):
    output = tmp_path / "output.mkv"
    output.write_bytes(b"mkv")
    source_audio = SourceTrackInfo(
        1,
        "audio",
        codec="AAC",
        language="eng",
        title="Main",
        default_track=True,
        channels=2,
    )
    plan = MuxPlan(
        tmp_path / "source.mkv",
        output,
        audio_tracks=[AudioTrackPlan(tmp_path / "extra.mka", None, "exact", expected_track_count=1)],
        source_tracks=[SourceTrackInfo(0, "video"), source_audio],
    )
    payload = {
        "tracks": [
            {"type": "video", "codec": "AVC", "properties": {}},
            {"type": "audio", "codec": "AAC", "properties": {
                "language": "eng", "track_name": "Main", "default_track": True,
                "forced_track": False, "audio_channels": 2,
            }},
            {"type": "audio", "codec": "FLAC", "properties": {}},
        ],
        "attachments": [],
    }
    monkeypatch.setattr(
        "plexmuxy.muxer.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )

    assert verify_mux_output(plan, output, "mkvmerge").success is True
    payload["tracks"].pop()
    assert verify_mux_output(plan, output, "mkvmerge").error_code == "TRACK_COUNT_MISMATCH"


def test_structural_verifier_rejects_changed_retained_source_audio(monkeypatch, tmp_path):
    output = tmp_path / "output.mkv"
    output.write_bytes(b"mkv")
    plan = MuxPlan(
        tmp_path / "source.mkv",
        output,
        source_tracks=[
            SourceTrackInfo(0, "video"),
            SourceTrackInfo(1, "audio", codec="AAC", language="jpn", title="Main", channels=2),
        ],
    )
    payload = {"tracks": [
        {"type": "video", "properties": {}},
        {"type": "audio", "codec": "AAC", "properties": {
            "language": "eng", "track_name": "Main", "audio_channels": 2,
        }},
    ], "attachments": []}
    monkeypatch.setattr(
        "plexmuxy.muxer.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )

    assert verify_mux_output(plan, output, "mkvmerge").error_code == "TRACK_PROPERTY_MISMATCH"
