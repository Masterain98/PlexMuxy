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


def test_default_config_v3_contains_environment_and_subset_contracts():
    config = default_config()

    assert config.config_version == 3
    assert config.media.font_extensions == [".ttf", ".otf", ".ttc", ".otc"]
    assert config.font.subset_failure_action == "fallback-full"
    assert config.ffmpeg.path == ""
    assert config.notifications.enabled is False
    assert set(config_to_dict(config)) >= {"ffmpeg", "notifications"}


def test_v2_config_without_v3_sections_migrates_in_memory():
    config = parse_config({
        "config_version": 2,
        "mkvmerge": {"path": "C:/tools/mkvmerge.exe"},
        "font": {"mode": "subset"},
    })

    assert config.config_version == 3
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
