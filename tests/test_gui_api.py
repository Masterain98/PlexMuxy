from plexmuxy.config import default_config
from plexmuxy.models import JobReport, MuxPlan
from plexmuxy_gui.api import PlexMuxyApi


def test_get_app_info_returns_ok(monkeypatch, tmp_path):
    monkeypatch.setattr("plexmuxy_gui.api.resolve_config_path", lambda path=None: tmp_path / "config.json")
    api = PlexMuxyApi()

    response = api.get_app_info()

    assert response["ok"] is True
    assert response["data"]["name"] == "PlexMuxy"


def test_load_config_returns_default_summary_when_config_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("plexmuxy_gui.api.resolve_config_path", lambda path=None: tmp_path / "missing.json")
    api = PlexMuxyApi()

    response = api.load_config()

    assert response["ok"] is True
    assert response["data"]["config_exists"] is False
    assert "mkvmerge" in response["data"]


def test_plan_job_rejects_missing_input_dir(tmp_path):
    api = PlexMuxyApi()

    response = api.plan_job({"input_dir": str(tmp_path / "missing"), "overrides": {}})

    assert response["ok"] is False
    assert "does not exist" in response["error"]


def test_plan_job_uses_service_and_serializes_report(monkeypatch, tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    plan = MuxPlan(source_video=video, output_path=output)

    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", default_config)
    monkeypatch.setattr(
        "plexmuxy_gui.api.run_mux_job",
        lambda input_dir, config, dry_run, yes: JobReport(input_dir=input_dir, plans=[plan]),
    )
    api = PlexMuxyApi()

    response = api.plan_job({"input_dir": str(tmp_path), "overrides": {}})

    assert response["ok"] is True
    assert response["data"]["plans"][0]["source_video_name"] == "Example.mkv"


def test_run_job_requires_delete_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", default_config)
    api = PlexMuxyApi()

    response = api.run_job(
        {
            "input_dir": str(tmp_path),
            "yes": False,
            "overrides": {"cleanup": "delete"},
        }
    )

    assert response["ok"] is False
    assert "confirmation" in response["error"]


def test_run_job_requires_confirmation_for_config_delete_flags(monkeypatch, tmp_path):
    config = default_config()
    config.task.delete_original_video = True
    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", lambda: config)
    api = PlexMuxyApi()

    response = api.run_job({"input_dir": str(tmp_path), "yes": False, "overrides": {}})

    assert response["ok"] is False
    assert "confirmation" in response["error"]


def test_run_job_uses_service_and_serializes_report(monkeypatch, tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    plan = MuxPlan(source_video=video, output_path=output)

    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", default_config)
    monkeypatch.setattr(
        "plexmuxy_gui.api.run_mux_job",
        lambda input_dir, config, dry_run, yes: JobReport(input_dir=input_dir, plans=[plan]),
    )
    api = PlexMuxyApi()

    response = api.run_job({"input_dir": str(tmp_path), "yes": True, "overrides": {}})

    assert response["ok"] is True
    assert response["data"]["plans"][0]["output_name"] == "Example_Plex.mkv"
