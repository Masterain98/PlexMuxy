from pathlib import Path

from plexmuxy_gui.notifications import NativeNotifier, _send_windows_toast, _truncate


def test_notification_capability_is_nonfatal_without_icon(tmp_path: Path) -> None:
    capability = NativeNotifier(tmp_path / "missing.ico").capability()

    assert capability.available is False
    assert capability.reason


def test_notification_text_is_compact_and_bounded() -> None:
    assert _truncate("  one\n two   three ", 32) == "one two three"
    value = _truncate("x" * 20, 8)
    assert value == "xxxxxxx…"
    assert len(value) == 8


def test_windows_toast_uses_encoded_content_and_restricted_job_uri(monkeypatch) -> None:
    captured = {}

    class Completed:
        returncode = 0
        stderr = b""

    monkeypatch.setattr("plexmuxy_gui.notifications.shutil.which", lambda _name: "powershell.exe")

    def run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return Completed()

    monkeypatch.setattr("plexmuxy_gui.notifications.subprocess.run", run)
    result = _send_windows_toast(
        "Title <safe>",
        "Body & safe",
        "5bf5467d-a161-4753-8d55-673265aae746",
    )
    assert result.sent is True
    assert result.backend == "windows-toast"
    assert captured["command"][:3] == ["powershell.exe", "-NoProfile", "-NonInteractive"]
    assert "Title <safe>" not in " ".join(captured["command"])
