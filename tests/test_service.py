from plexmuxy.config import default_config
from plexmuxy.models import SourceTrackInfo
from plexmuxy.service import run_mux_job


def test_run_mux_job_dry_run_returns_report_without_results(tmp_path):
    video = tmp_path / "Example.mkv"
    subtitle = tmp_path / "Example.chs.ass"
    video.write_text("video", encoding="utf-8")
    subtitle.write_text("subtitle", encoding="utf-8")

    report = run_mux_job(tmp_path, default_config(), dry_run=True)

    assert report.input_dir == tmp_path.resolve()
    assert len(report.plans) == 1
    assert report.results == []
    assert report.cleanup_results == []


def test_missing_font_fail_job_policy_is_reported_during_planning(tmp_path):
    (tmp_path / "Example.mkv").write_bytes(b"video")
    (tmp_path / "Example.chs.ass").write_text("Style: Default, Missing Font,20,x", encoding="utf-8")
    config = default_config()
    config.font.mode = "referenced"
    config.font.missing_font_action = "fail-job"

    report = run_mux_job(tmp_path, config, dry_run=True)

    assert report.error_code == "MISSING_REFERENCED_FONT"


def test_audio_filter_requires_source_inspection_and_writes_decisions(monkeypatch, tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    (tmp_path / "Example.chs.ass").write_text("subtitle", encoding="utf-8")
    config = default_config()
    config.tracks.audio_filter_enabled = True
    config.tracks.keep_default_audio = False
    config.tracks.keep_audio_languages = ["jpn"]
    monkeypatch.setattr("plexmuxy.service.resolve_mkvmerge_path", lambda _config: "mkvmerge")
    monkeypatch.setattr("plexmuxy.service.inspect_source_tracks", lambda _path, _tool: [
        SourceTrackInfo(0, "video", codec="AVC"),
        SourceTrackInfo(1, "audio", codec="AAC", language="jpn"),
        SourceTrackInfo(2, "audio", codec="AAC", language="eng"),
    ])

    report = run_mux_job(tmp_path, config, dry_run=True)

    assert report.error is None
    assert [track.included for track in report.plans[0].source_tracks] == [True, True, False]
    assert report.snapshot is not None and report.snapshot.schema_version == 3


def test_audio_filter_fails_closed_when_mkvmerge_is_unavailable(monkeypatch, tmp_path):
    (tmp_path / "Example.mkv").write_bytes(b"video")
    (tmp_path / "Example.chs.ass").write_text("subtitle", encoding="utf-8")
    config = default_config()
    config.tracks.audio_filter_enabled = True
    monkeypatch.setattr("plexmuxy.service.resolve_mkvmerge_path", lambda _config: None)

    report = run_mux_job(tmp_path, config, dry_run=True)

    assert report.error_code == "MKVMERGE_REQUIRED_FOR_TRACK_FILTER"
    assert report.snapshot is None
