import json
from io import BytesIO

from plexmuxy.models import UpdateConfig
from plexmuxy.update_check import check_for_updates


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self._stream = BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self._stream.read(size)


def test_update_check_is_offline_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    result = check_for_updates("0.2.0", UpdateConfig(), cache_path=tmp_path / "updates.json")
    assert result.enabled is False
    assert result.checked is False


def test_update_check_uses_official_release_and_cache(monkeypatch, tmp_path):
    calls = []

    def open_request(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeResponse({"tag_name": "v0.3.0", "html_url": "https://github.com/Masterain98/PlexMuxy/releases/tag/v0.3.0"})

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    config = UpdateConfig(enabled=True, interval_hours=24, timeout_seconds=2)
    cache = tmp_path / "updates.json"
    first = check_for_updates("0.2.0", config, cache_path=cache)
    second = check_for_updates("0.2.0", config, cache_path=cache)
    assert first.update_available is True
    assert first.cached is False
    assert second.cached is True
    assert len(calls) == 1


def test_update_failure_is_non_fatal_and_cached(monkeypatch, tmp_path):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    result = check_for_updates("0.2.0", UpdateConfig(enabled=True), cache_path=tmp_path / "updates.json")
    assert result.checked is True
    assert result.error == "offline"


def test_stable_release_is_newer_than_same_version_release_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"tag_name": "v0.3.0", "html_url": "https://example.test/release"}),
    )
    result = check_for_updates("0.3.0rc1", UpdateConfig(enabled=True), cache_path=tmp_path / "updates.json")
    assert result.update_available is True
