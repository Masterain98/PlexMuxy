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


def test_cleanup_move_conflict_uses_unique_destination(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    extra = tmp_path / "Extra"
    video.write_text("source", encoding="utf-8")
    output.write_text("output", encoding="utf-8")
    extra.mkdir()
    (extra / "Example.mkv").write_text("existing", encoding="utf-8")
    plan = MuxPlan(source_video=video, output_path=output, cleanup_candidates=[video])
    result = MuxResult(plan=plan, success=True, output_path=output, verified=True)

    cleanup_results = cleanup_successful_results([result], default_config())

    assert cleanup_results[0].success is True
    assert cleanup_results[0].destination == extra / "Example (1).mkv"
    assert cleanup_results[0].destination.exists()
    assert not video.exists()


def test_cleanup_move_directory_setup_failure_returns_result(tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    blocked_extra = tmp_path / "blocked"
    video.write_text("source", encoding="utf-8")
    output.write_text("output", encoding="utf-8")
    blocked_extra.write_text("not a directory", encoding="utf-8")
    config = default_config()
    config.task.extra_dir = str(blocked_extra)
    plan = MuxPlan(source_video=video, output_path=output, cleanup_candidates=[video])
    result = MuxResult(plan=plan, success=True, output_path=output, verified=True)

    cleanup_results = cleanup_successful_results([result], config)

    assert cleanup_results[0].success is False
    assert cleanup_results[0].action == "move"
    assert video.exists()


def test_cleanup_deletes_fonts_for_each_successful_source_directory(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    for directory in (first_dir, second_dir):
        (directory / "Fonts").mkdir()
        (directory / "Fonts" / "font.ttf").write_text("font", encoding="utf-8")

    first_video = first_dir / "Example.mkv"
    first_output = first_dir / "Example_Plex.mkv"
    second_video = second_dir / "Example.mkv"
    second_output = second_dir / "Example_Plex.mkv"
    for path in (first_video, first_output, second_video, second_output):
        path.write_text("media", encoding="utf-8")

    results = [
        MuxResult(
            plan=MuxPlan(source_video=first_video, output_path=first_output, cleanup_candidates=[]),
            success=True,
            output_path=first_output,
            verified=True,
        ),
        MuxResult(
            plan=MuxPlan(source_video=second_video, output_path=second_output, cleanup_candidates=[]),
            success=True,
            output_path=second_output,
            verified=True,
        ),
    ]
    config = default_config()
    config.font.delete_fonts_after_mux = True

    cleanup_results = cleanup_successful_results(results, config, yes=True)

    deleted_font_dirs = {result.path for result in cleanup_results if result.action == "delete"}
    assert deleted_font_dirs == {first_dir / "Fonts", second_dir / "Fonts"}
    assert not (first_dir / "Fonts").exists()
    assert not (second_dir / "Fonts").exists()


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
