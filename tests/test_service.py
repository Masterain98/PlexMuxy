from plexmuxy.config import default_config
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
