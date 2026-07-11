from plexmuxy.cleanup import cleanup_successful_results
from plexmuxy.config import default_config
from plexmuxy.models import MuxPlan, MuxResult


def test_shared_resource_waits_when_any_dependent_plan_fails(tmp_path):
    shared = tmp_path / "Common.mka"
    first = tmp_path / "One.mkv"
    second = tmp_path / "Two.mkv"
    for path in (shared, first, second):
        path.write_bytes(b"source")
    first_plan = MuxPlan(first, tmp_path / "One_Plex.mkv", cleanup_candidates=[shared])
    second_plan = MuxPlan(second, tmp_path / "Two_Plex.mkv", cleanup_candidates=[shared])
    results = [
        MuxResult(first_plan, True, first_plan.output_path, verified=True),
        MuxResult(second_plan, False, second_plan.output_path, verified=False),
    ]
    assert cleanup_successful_results(results, default_config()) == []
    assert shared.exists()
