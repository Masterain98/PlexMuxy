import json

import pytest

from plexmuxy.config import ConfigError, default_config, load_config, migrate_config, parse_config, save_config


def test_future_config_version_is_rejected():
    with pytest.raises(ConfigError, match="newer"):
        parse_config({"config_version": 999})


def test_unknown_root_config_field_is_rejected():
    with pytest.raises(ConfigError, match="Unknown config"):
        parse_config({"unexpected": True})


def test_unknown_nested_config_field_is_rejected():
    with pytest.raises(ConfigError, match="Unknown task"):
        parse_config({"task": {"surprise": True}})


def test_duplicate_extensions_are_normalized_and_deduplicated():
    config = parse_config({"media": {"video_extensions": ["MKV", ".mkv", "Mp4"]}})
    assert config.media.video_extensions == [".mkv", ".mp4"]


def test_duplicate_language_profiles_are_rejected_case_insensitively():
    profile = {"id": "chs", "mkv_language": "chi", "ietf_language": "zh-Hans", "keywords": []}
    with pytest.raises(ConfigError, match="Duplicate"):
        parse_config({"subtitle": {"default_language": "chs", "profiles": [profile, {**profile, "id": "CHS"}]}})


def test_invalid_template_variable_is_rejected():
    with pytest.raises(ConfigError, match="Unknown task.name_template"):
        parse_config({"task": {"name_template": "{unknown}"}})


def test_save_config_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config = default_config()
    config.task.output_dir = tmp_path / "out"
    save_config(config, path)
    assert load_config(path, create_if_missing=False).task.output_dir == tmp_path / "out"
    assert not list(tmp_path.glob("*.tmp"))


def test_migrate_config_creates_backup(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"config_version": 1}), encoding="utf-8")
    target, backup = migrate_config(path)
    assert target == path
    assert backup is not None and backup.exists()
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["config_version"] == 4
    assert migrated["ffmpeg"] == {"path": ""}
    assert migrated["notifications"] == {"enabled": False}
    assert migrated["updates"] == {"enabled": False, "interval_hours": 24, "timeout_seconds": 3.0}
    assert migrated["plex"] == {
        "enabled": False,
        "server_url": "",
        "section_id": "",
        "token_env": "PLEXMUXY_PLEX_TOKEN",
        "path_mappings": [],
    }
    assert migrated["tracks"] == {
        "audio_filter_enabled": False,
        "exclude_audio_title_patterns": [],
        "keep_audio_languages": [],
        "keep_default_audio": True,
        "keep_all_when_unknown": True,
        "allow_no_audio": False,
    }
