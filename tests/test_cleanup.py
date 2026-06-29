from plexmuxy.cleanup import cleanup_successful_results
from plexmuxy.config import default_config
from plexmuxy.models import MuxPlan, MuxResult


def test_cleanup_moves_verified_successful_candidates(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    video.write_text("source", encoding="utf-8")
    output.write_text("output", encoding="utf-8")
    plan = MuxPlan(source_video=video, output_path=output, cleanup_candidates=[video])
    result = MuxResult(plan=plan, success=True, output_path=output, verified=True)

    cleanup_results = cleanup_successful_results([result], default_config())

    assert cleanup_results[0].success is True
    assert cleanup_results[0].action == "move"
    assert cleanup_results[0].destination == tmp_path / "Extra" / "Example.mkv"
    assert not video.exists()
    assert (tmp_path / "Extra" / "Example.mkv").exists()


def test_delete_cleanup_requires_yes(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    video.write_text("source", encoding="utf-8")
    output.write_text("output", encoding="utf-8")
    config = default_config()
    config.task.delete_original_video = True
    plan = MuxPlan(source_video=video, output_path=output, cleanup_candidates=[video])
    result = MuxResult(plan=plan, success=True, output_path=output, verified=True)

    cleanup_results = cleanup_successful_results([result], config, yes=False)

    assert cleanup_results[0].success is False
    assert cleanup_results[0].action == "delete"
    assert video.exists()


def test_failed_mux_result_is_not_cleaned(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    video.write_text("source", encoding="utf-8")
    plan = MuxPlan(source_video=video, output_path=output, cleanup_candidates=[video])
    result = MuxResult(plan=plan, success=False, output_path=output, verified=False)

    cleanup_results = cleanup_successful_results([result], default_config())

    assert cleanup_results == []
    assert video.exists()
