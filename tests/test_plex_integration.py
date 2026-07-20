from pathlib import Path

import pytest

from plexmuxy.integrations.plex import PlexIntegrationError, map_local_path, refresh_paths
from plexmuxy.models import PlexConfig, PlexPathMapping


def plex_config(root: Path) -> PlexConfig:
    return PlexConfig(
        enabled=True,
        server_url="https://plex.example.test",
        section_id="2",
        path_mappings=[PlexPathMapping(root, "/media")],
    )


def test_plex_path_mapping_uses_most_specific_root(tmp_path):
    root = tmp_path.resolve()
    config = plex_config(root)
    config.path_mappings.append(PlexPathMapping(root / "shows", "/tv"))
    assert map_local_path(root / "shows" / "Series", config) == "/tv/Series"
    with pytest.raises(PlexIntegrationError, match="No Plex path mapping"):
        map_local_path(root.parent / "other", config)


def test_plex_refresh_sends_token_in_header_and_never_url(monkeypatch, tmp_path):
    config = plex_config(tmp_path.resolve())
    monkeypatch.setenv("PLEXMUXY_PLEX_TOKEN", "secret-token")
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def open_request(request, timeout):
        captured.update(url=request.full_url, headers=dict(request.header_items()), timeout=timeout)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    result = refresh_paths(config, [tmp_path / "Show"])
    assert result[0].success is True
    assert "secret-token" not in captured["url"]
    assert captured["headers"]["X-plex-token"] == "secret-token"


def test_plex_refresh_missing_token_is_explicit_without_exposing_values(monkeypatch, tmp_path):
    config = plex_config(tmp_path.resolve())
    monkeypatch.delenv("PLEXMUXY_PLEX_TOKEN", raising=False)
    with pytest.raises(PlexIntegrationError, match="PLEXMUXY_PLEX_TOKEN"):
        refresh_paths(config, [tmp_path])
