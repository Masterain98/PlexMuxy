from plexmuxy.config import default_config
from plexmuxy.models import JobReport, MuxPlan, MuxResult
from plexmuxy_gui.api import GuiJob, PlexMuxyApi
from plexmuxy_gui.notifications import NotificationCapability, NotificationResult


class FakeDesktopWindow:
    def __init__(self) -> None:
        self.calls = []
        self.scripts = []

    def minimize(self) -> None:
        self.calls.append("minimize")

    def maximize(self) -> None:
        self.calls.append("maximize")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")

    def evaluate_js(self, script) -> None:
        self.scripts.append(script)


class ImmediateTimer:
    def __init__(self, _delay, callback) -> None:
        self.callback = callback
        self.daemon = False

    def start(self) -> None:
        self.callback()


class FakeNotifier:
    def __init__(self, available=True) -> None:
        self.available = available
        self.messages = []
        self.closed = False

    def capability(self):
        return NotificationCapability(self.available, "test", None if self.available else "unsupported")

    def send(self, title, message, tone="info", timeout_ms=6000):
        self.messages.append((title, message, tone, timeout_ms))
        return NotificationResult(self.available, "test", None if self.available else "unsupported")

    def close(self) -> None:
        self.closed = True


class PickerWindow(FakeDesktopWindow):
    def __init__(self, selected_path) -> None:
        super().__init__()
        self.selected_path = selected_path
        self.dialog_call = None

    def create_file_dialog(self, dialog_type, **kwargs):
        self.dialog_call = (dialog_type, kwargs)
        return [str(self.selected_path)] if self.selected_path else None


def test_window_controls_delegate_to_bound_desktop_window(monkeypatch):
    monkeypatch.setattr("plexmuxy_gui.api.threading.Timer", ImmediateTimer)
    api = PlexMuxyApi()
    window = FakeDesktopWindow()
    api.bind_window(window)

    assert api.minimize_window()["ok"] is True
    assert api.toggle_maximize_window()["data"] == {"maximized": True}
    assert api.toggle_maximize_window()["data"] == {"maximized": False}
    assert api.close_window()["ok"] is True
    assert window.calls == ["minimize", "maximize", "restore", "destroy"]


def test_native_window_close_is_redirected_to_custom_frontend_dialog(monkeypatch):
    monkeypatch.setattr("plexmuxy_gui.api.threading.Timer", ImmediateTimer)
    api = PlexMuxyApi()
    window = FakeDesktopWindow()
    api.bind_window(window)

    assert api._handle_window_closing() is False
    assert window.scripts == ["window.PlexMuxyRequestClose?.()"]

    api._allow_window_close = True
    assert api._handle_window_closing() is None


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


def test_plan_job_rejects_empty_input_dir():
    api = PlexMuxyApi()

    response = api.plan_job({"input_dir": "", "overrides": {}})

    assert response["ok"] is False
    assert "required" in response["error"]


def test_plan_job_rejects_non_object_overrides(tmp_path):
    api = PlexMuxyApi()

    response = api.plan_job({"input_dir": str(tmp_path), "overrides": ["bad"]})

    assert response["ok"] is False
    assert "overrides must be an object" in response["error"]


def test_plan_job_uses_service_and_serializes_report(monkeypatch, tmp_path):
    video = tmp_path / "Example.mkv"
    output = tmp_path / "Example_Plex.mkv"
    plan = MuxPlan(source_video=video, output_path=output)
    calls = []

    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", default_config)

    def fake_run_mux_job(input_dir, config, dry_run, yes):
        calls.append({"input_dir": input_dir, "dry_run": dry_run, "yes": yes})
        return JobReport(input_dir=input_dir, plans=[plan])

    monkeypatch.setattr("plexmuxy_gui.api.run_mux_job", fake_run_mux_job)
    api = PlexMuxyApi()

    response = api.plan_job({"input_dir": str(tmp_path), "overrides": {}})

    assert response["ok"] is True
    assert response["data"]["plans"][0]["source_video_name"] == "Example.mkv"
    assert calls == [{"input_dir": tmp_path.resolve(), "dry_run": True, "yes": False}]


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
    calls = []

    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", default_config)

    def fake_run_mux_job(input_dir, config, dry_run, yes):
        calls.append({"input_dir": input_dir, "dry_run": dry_run, "yes": yes})
        return JobReport(input_dir=input_dir, plans=[plan])

    monkeypatch.setattr("plexmuxy_gui.api.run_mux_job", fake_run_mux_job)
    api = PlexMuxyApi()

    response = api.run_job({"input_dir": str(tmp_path), "yes": True, "overrides": {}})

    assert response["ok"] is True
    assert response["data"]["plans"][0]["output_name"] == "Example_Plex.mkv"
    assert calls == [{"input_dir": tmp_path.resolve(), "dry_run": False, "yes": True}]


def test_save_settings_persists_validated_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("plexmuxy_gui.api.resolve_config_path", lambda path=None: config_path)
    api = PlexMuxyApi()

    response = api.save_settings({"cleanup": "none", "output_suffix": "_Ready"})

    assert response["ok"] is True
    assert config_path.exists()
    assert response["data"]["task"]["cleanup"] == "none"
    assert response["data"]["task"]["output_suffix"] == "_Ready"


def test_save_settings_persists_font_subset_mode(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("plexmuxy_gui.api.resolve_config_path", lambda path=None: config_path)
    api = PlexMuxyApi()
    api._notifier = FakeNotifier()

    response = api.save_settings({"font_mode": "subset"})

    assert response["ok"] is True
    assert response["data"]["font"]["mode"] == "subset"


def test_choose_dependency_uses_open_picker_and_validates_allowlist(tmp_path):
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"stub")
    window = PickerWindow(executable)
    api = PlexMuxyApi()
    api.bind_window(window)

    response = api.choose_dependency("ffmpeg")

    assert response["ok"] is True
    assert response["data"]["path"] == str(executable.resolve())
    assert window.dialog_call[1]["allow_multiple"] is False
    assert window.dialog_call[1]["file_types"] == ("Executable files (*.exe)",)


def test_choose_dependency_rejects_wrong_executable_name(tmp_path):
    executable = tmp_path / "unrelated.exe"
    executable.write_bytes(b"stub")
    api = PlexMuxyApi()
    api.bind_window(PickerWindow(executable))

    response = api.choose_dependency("mkvmerge")

    assert response["ok"] is False
    assert "Expected" in response["error"]


def test_save_environment_settings_persists_paths_and_notifications(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    mkvmerge = tmp_path / "mkvmerge.exe"
    ffmpeg = tmp_path / "ffmpeg.exe"
    mkvmerge.write_bytes(b"stub")
    ffmpeg.write_bytes(b"stub")
    monkeypatch.setattr("plexmuxy_gui.api.resolve_config_path", lambda path=None: config_path)
    api = PlexMuxyApi()
    api._notifier = FakeNotifier()

    response = api.save_environment_settings(
        {
            "mkvmerge_path": str(mkvmerge),
            "ffmpeg_path": str(ffmpeg),
            "unrar_path": "",
            "notifications_enabled": True,
        }
    )

    assert response["ok"] is True
    assert response["data"]["mkvmerge"]["configured_path"] == str(mkvmerge)
    assert response["data"]["ffmpeg"]["available"] is True
    assert response["data"]["notifications"]["enabled"] is True
    assert response["data"]["notifications"]["available"] is True


def test_reset_dependency_path_restores_automatic_resolution(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    mkvmerge = tmp_path / "mkvmerge.exe"
    mkvmerge.write_bytes(b"stub")
    monkeypatch.setattr("plexmuxy_gui.api.resolve_config_path", lambda path=None: config_path)
    api = PlexMuxyApi()
    api._notifier = FakeNotifier()
    assert api.save_environment_settings({"mkvmerge_path": str(mkvmerge)})["ok"] is True

    response = api.reset_dependency_path("mkvmerge")

    assert response["ok"] is True
    assert response["data"]["mkvmerge"]["configured_path"] == ""


def test_native_job_notification_is_gated_by_persisted_setting(monkeypatch):
    config = default_config()
    notifier = FakeNotifier()
    api = PlexMuxyApi()
    api._notifier = notifier
    monkeypatch.setattr("plexmuxy_gui.api.load_or_default_config", lambda: config)
    job = GuiJob("job", status="completed")

    api._notify_job_terminal(job)
    assert notifier.messages == []

    config.notifications.enabled = True
    api._notify_job_terminal(job)
    assert notifier.messages[0][0] == "PlexMuxy job completed"
    assert notifier.messages[0][2] == "success"


def test_background_job_with_failed_mux_uses_failed_terminal_status(monkeypatch, tmp_path):
    plan = MuxPlan(tmp_path / "source.mkv", tmp_path / "output.mkv")
    report = JobReport(
        input_dir=tmp_path,
        plans=[plan],
        results=[MuxResult(plan, False, plan.output_path, error_code="MUX_FAILED", error="boom")],
    )
    monkeypatch.setattr("plexmuxy_gui.api.execute_plan_snapshot", lambda *_args, **_kwargs: report)
    api = PlexMuxyApi()
    monkeypatch.setattr(api, "_notify_job_terminal", lambda _job: None)
    job = GuiJob("job")

    api._execute_background_job(job, object(), default_config(), False)

    assert job.status == "failed"
    assert job.error == "1 mux operation(s) failed"


def test_notification_test_reports_explicit_unavailability():
    api = PlexMuxyApi()
    api._notifier = FakeNotifier(available=False)

    response = api.test_notification()

    assert response["ok"] is True
    assert response["data"]["capability"]["available"] is False
    assert response["data"]["result"] is None
