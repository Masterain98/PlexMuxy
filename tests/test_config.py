from pathlib import Path

import pytest

from plexmuxy.config import (
    ConfigError,
    cleanup_mode,
    config_to_dict,
    default_config,
    extension_list,
    name_strategy,
    parse_config,
    parse_v2_config,
)


def test_legacy_config_is_migrated_in_memory():
    config = parse_config(
        {
            "TaskSettings": {
                "DeleteFonts": False,
                "DeleteOriginalMKV": True,
                "DeleteOriginalMKA": False,
                "DeleteSubtitle": False,
                "OutputSuffixName": "",
            },
            "Font": {
                "AllowedExtensions": [".ttf", ".otf", ".ttc"],
                "Unrar_Path": "C:\\Program Files\\WinRAR\\UnRAR.exe",
            },
            "Subtitle": {
                "Keyword": {
                    "CHS": [".chs"],
                    "CHT": [".cht"],
                    "JP_SC": [".jpsc"],
                    "JP_TC": [".jptc"],
                    "JP": [".jpn"],
                    "RU": [".rus"],
                },
                "DefaultLanguage": "chs",
                "ShowSubtitleAuthorInTrackName": True,
            },
            "mkvmerge": {"path": "mkvmerge"},
            "multiprocessing": {"thread_count": "auto"},
        }
    )

    assert config.task.output_suffix == "_Plex"
    assert config.task.delete_original_video is True
    assert config.subtitle.profiles[0].id == "jp_sc"


def test_thread_count_validation_reports_field():
    with pytest.raises(ConfigError, match=r"concurrency\.thread_count"):
        parse_config({"concurrency": {"thread_count": 0}})


def test_thread_count_rejects_bool_values():
    with pytest.raises(ConfigError, match=r"concurrency\.thread_count"):
        parse_config({"concurrency": {"thread_count": True}})


def test_parse_v2_config_normalizes_extensions_and_suffix_default():
    config = parse_v2_config(
        {
            "media": {
                "video_extensions": ["MKV", "Mp4"],
                "audio_extensions": ["MKA"],
                "subtitle_extensions": ["ASS"],
            },
            "task": {
                "output_suffix": "",
                "cleanup": "none",
                "name_strategy": "same-name",
                "output_dir": "~/PlexReady",
            },
        }
    )

    assert config.media.video_extensions == [".mkv", ".mp4"]
    assert config.media.audio_extensions == [".mka"]
    assert config.media.subtitle_extensions == [".ass"]
    assert config.task.output_suffix == "_Plex"
    assert config.task.cleanup == "none"
    assert config.task.name_strategy == "same-name"
    assert config.task.output_dir == Path("~/PlexReady").expanduser()


def test_config_validation_helpers_reject_invalid_values():
    with pytest.raises(ConfigError):
        cleanup_mode("invalid", "task.cleanup")
    with pytest.raises(ConfigError):
        name_strategy("invalid", "task.name_strategy")


def test_extension_list_normalizes_extensions():
    assert extension_list(["MKV", ".mka", "Mp3"], "media.extensions") == [".mkv", ".mka", ".mp3"]


def test_default_config_v4_contains_environment_subset_and_track_contracts():
    config = default_config()

    assert config.config_version == 4
    assert config.media.font_extensions == [".ttf", ".otf", ".ttc", ".otc"]
    assert config.font.subset_failure_action == "fallback-full"
    assert config.font_cache.enabled is True
    assert config.font_cache.max_size_mb == 2048
    assert config.font_cache.max_age_days == 90
    assert config.ffmpeg.path == ""
    assert config.notifications.enabled is False
    assert config.tracks.audio_filter_enabled is False
    assert config.tracks.keep_default_audio is True
    assert config.tracks.allow_no_audio is False
    assert config.updates.enabled is False
    assert config.plex.enabled is False
    assert set(config_to_dict(config)) >= {"ffmpeg", "notifications", "font_cache", "updates", "plex"}


def test_update_and_plex_config_are_strict_and_safe_by_default():
    config = parse_config({
        "updates": {"enabled": True, "interval_hours": 12, "timeout_seconds": 2.5},
        "plex": {
            "enabled": True,
            "server_url": "https://plex.example.test",
            "section_id": "2",
            "token_env": "MY_PLEX_TOKEN",
            "path_mappings": [{"local_root": str(Path.cwd() / "media"), "server_root": "/media"}],
        },
    })
    assert config.updates.interval_hours == 12
    assert config.plex.token_env == "MY_PLEX_TOKEN"
    assert config.plex.path_mappings[0].server_root == "/media"

    with pytest.raises(ConfigError, match=r"plex\.path_mappings"):
        parse_config({"plex": {"path_mappings": "C:/media"}})
    with pytest.raises(ConfigError, match=r"updates\.timeout_seconds"):
        parse_config({"updates": {"timeout_seconds": 30}})


def test_v2_config_without_v3_sections_migrates_in_memory():
    config = parse_config({
        "config_version": 2,
        "mkvmerge": {"path": "C:/tools/mkvmerge.exe"},
        "font": {"mode": "subset"},
    })

    assert config.config_version == 4
    assert config.mkvmerge.path == "C:/tools/mkvmerge.exe"
    assert config.ffmpeg.path == ""
    assert config.notifications.enabled is False
    assert config.font.subset_failure_action == "fallback-full"


def test_v3_environment_and_subset_fields_are_validated_strictly():
    config = parse_config({
        "config_version": 3,
        "ffmpeg": {"path": "C:/tools/ffmpeg.exe"},
        "notifications": {"enabled": True},
        "font": {"subset_failure_action": "skip-video"},
    })
    assert config.ffmpeg.path == "C:/tools/ffmpeg.exe"
    assert config.notifications.enabled is True
    assert config.font.subset_failure_action == "skip-video"

    with pytest.raises(ConfigError, match="Unknown notifications"):
        parse_config({"notifications": {"surprise": True}})
    with pytest.raises(ConfigError, match=r"font\.subset_failure_action"):
        parse_config({"font": {"subset_failure_action": "continue-anyway"}})


def test_v3_tracks_migrate_to_safe_v4_defaults_without_enabling_filtering():
    config = parse_config({
        "config_version": 3,
        "tracks": {
            "exclude_audio_title_patterns": ["commentary"],
            "keep_audio_languages": ["jpn"],
            "keep_all_when_unknown": True,
        },
    })

    assert config.config_version == 4
    assert config.tracks.audio_filter_enabled is False
    assert config.tracks.exclude_audio_title_patterns == ["commentary"]
    assert config.tracks.keep_audio_languages == ["jpn"]
    assert config.tracks.keep_default_audio is True
    assert config.tracks.allow_no_audio is False


def test_v4_track_filter_fields_are_strictly_validated():
    config = parse_config({
        "config_version": 4,
        "tracks": {
            "audio_filter_enabled": True,
            "keep_default_audio": False,
            "allow_no_audio": True,
        },
    })
    assert config.tracks.audio_filter_enabled is True
    assert config.tracks.keep_default_audio is False
    assert config.tracks.allow_no_audio is True

    with pytest.raises(ConfigError, match=r"tracks\.audio_filter_enabled"):
        parse_config({"config_version": 4, "tracks": {"audio_filter_enabled": "yes"}})
