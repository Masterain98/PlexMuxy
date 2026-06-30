from plexmuxy.config import default_config
from plexmuxy.models import MuxPlan
from plexmuxy.muxer import execute_mux_plan


def test_execute_mux_plan_refuses_in_place_output_even_with_overwrite(tmp_path):
    video = tmp_path / "Example.mkv"
    video.write_text("source", encoding="utf-8")
    config = default_config()
    config.task.overwrite = True
    plan = MuxPlan(source_video=video, output_path=video)

    result = execute_mux_plan(plan, config)

    assert result.success is False
    assert "same as the source" in result.error
