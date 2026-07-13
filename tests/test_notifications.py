from pathlib import Path

from plexmuxy_gui.notifications import NativeNotifier, _truncate


def test_notification_capability_is_nonfatal_without_icon(tmp_path: Path) -> None:
    capability = NativeNotifier(tmp_path / "missing.ico").capability()

    assert capability.available is False
    assert capability.reason


def test_notification_text_is_compact_and_bounded() -> None:
    assert _truncate("  one\n two   three ", 32) == "one two three"
    value = _truncate("x" * 20, 8)
    assert value == "xxxxxxx…"
    assert len(value) == 8
