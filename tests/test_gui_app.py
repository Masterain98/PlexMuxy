from plexmuxy_gui import app


class FakeWindow:
    def __init__(self) -> None:
        self.exposed = ()

    def expose(self, *functions) -> None:
        self.exposed = functions


class FakeWebview:
    def __init__(self) -> None:
        self.settings = {}
        self.window = FakeWindow()
        self.create_kwargs = None
        self.start_kwargs = None

    def create_window(self, **kwargs):
        self.create_kwargs = kwargs
        return self.window

    def start(self, **kwargs) -> None:
        self.start_kwargs = kwargs


def test_start_exposes_only_intended_bridge_methods(monkeypatch):
    webview = FakeWebview()
    dpi_calls = []
    monkeypatch.setattr(app, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(app, "import_webview", lambda: webview)
    monkeypatch.setattr(app, "enable_per_monitor_v2", lambda: dpi_calls.append(True))

    app.start()

    assert webview.create_kwargs["js_api"] is None
    assert webview.create_kwargs["frameless"] is True
    assert webview.create_kwargs["easy_drag"] is False
    assert webview.create_kwargs["width"] == 1280
    assert webview.create_kwargs["height"] == 800
    assert webview.create_kwargs["min_size"] == (960, 640)
    assert webview.create_kwargs["confirm_close"] is False
    assert webview.start_kwargs["http_server"] is True
    assert webview.start_kwargs["icon"].endswith("plexmuxy-app.ico")
    assert dpi_calls == [True]
    assert {function.__name__ for function in webview.window.exposed} == set(app.EXPOSED_API_METHODS)
    api = webview.window.exposed[0].__self__
    assert api._window is webview.window
    assert "window" not in vars(api)
    assert "jobs" not in vars(api)
    assert "jobs_lock" not in vars(api)
