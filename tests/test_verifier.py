import json
from types import SimpleNamespace

from plexmuxy.models import AttachmentPlan, MuxPlan, SubtitleTrackPlan
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
    ], "attachments": [{"file_name": "font.ttf"}], "container": {"type": "Matroska"}}
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
