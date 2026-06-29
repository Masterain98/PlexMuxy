import pytest

from plexmuxy.config import ConfigError, parse_config


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
    with pytest.raises(ConfigError, match="concurrency.thread_count"):
        parse_config({"concurrency": {"thread_count": 0}})
