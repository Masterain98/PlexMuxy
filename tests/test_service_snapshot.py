from plexmuxy.config import default_config
from plexmuxy.models import MuxPlan, MuxResult
from plexmuxy.service import execute_plan_snapshot
from plexmuxy.snapshot import create_plan_snapshot


def test_execute_snapshot_reports_stale_config(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)
    changed = default_config()
    changed.task.cleanup = "none"
    report = execute_plan_snapshot(snapshot, changed)
    assert report.error_code == "PLAN_STALE"


def test_execute_snapshot_runs_progress_and_cleanup(monkeypatch, tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    config.task.cleanup = "none"
    plan = MuxPlan(video, tmp_path / "Example_Plex.mkv", cleanup_candidates=[video])
    snapshot = create_plan_snapshot(tmp_path, [plan], config)
    monkeypatch.setattr("plexmuxy.service.prepare_fonts", lambda *a, **k: __import__("plexmuxy.models", fromlist=["FontResult"]).FontResult())
    monkeypatch.setattr("plexmuxy.service.execute_mux_plan", lambda plan, config, cancel: MuxResult(plan, True, plan.output_path, verified=True))
    events = []
    report = execute_plan_snapshot(snapshot, config, progress_callback=events.append)
    assert report.success_count == 1
    assert report.cleanup_results[0].action == "none"
    assert [event.phase for event in events][-2:] == ["cleaning", "completed"]


def test_execute_snapshot_parallel_jobs(monkeypatch, tmp_path):
    videos = [tmp_path / "One.mkv", tmp_path / "Two.mkv"]
    for video in videos:
        video.write_bytes(b"video")
    config = default_config()
    config.task.cleanup = "none"
    config.concurrency.max_parallel_mux_jobs = 2
    plans = [MuxPlan(video, tmp_path / f"{video.stem}_Plex.mkv") for video in videos]
    snapshot = create_plan_snapshot(tmp_path, plans, config)
    monkeypatch.setattr("plexmuxy.service.prepare_fonts", lambda *a, **k: __import__("plexmuxy.models", fromlist=["FontResult"]).FontResult())
    monkeypatch.setattr("plexmuxy.service.execute_mux_plan", lambda plan, config, cancel: MuxResult(plan, True, plan.output_path, verified=True))
    report = execute_plan_snapshot(snapshot, config)
    assert report.success_count == 2


def test_execute_snapshot_requires_confirmation_for_overwrite(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    video.write_bytes(b"video")
    output.write_bytes(b"existing")
    config = default_config()
    config.task.overwrite = True
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, output)], config)
    report = execute_plan_snapshot(snapshot, config, yes=False)
    assert report.error_code == "OVERWRITE_CONFIRMATION_REQUIRED"


def test_execute_snapshot_requires_confirmation_for_delete(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_bytes(b"video")
    config = default_config()
    config.task.cleanup = "delete"
    config.task.cleanup_overridden = True
    snapshot = create_plan_snapshot(tmp_path, [MuxPlan(video, tmp_path / "Example_Plex.mkv")], config)
    report = execute_plan_snapshot(snapshot, config, yes=False)
    assert report.error_code == "DELETE_CONFIRMATION_REQUIRED"
