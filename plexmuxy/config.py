from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    AppConfig,
    ConcurrencyConfig,
    FontConfig,
    LanguageProfile,
    MediaConfig,
    MkvMergeConfig,
    SubtitleConfig,
    TaskConfig,
)


LANGUAGE_PROFILES = [
    LanguageProfile(
        id="jp_sc",
        mkv_language="chi",
        ietf_language="zh-Hans",
        keywords=[".jpsc", "[jpsc]", "jp_sc", "[jp_sc]", "chs&jap", "简日"],
    ),
    LanguageProfile(
        id="jp_tc",
        mkv_language="chi",
        ietf_language="zh-Hant",
        keywords=[".jptc", "[jptc]", "jp_tc", "[jp_tc]", "cht&jap", "繁日"],
    ),
    LanguageProfile(
        id="chs",
        mkv_language="chi",
        ietf_language="zh-Hans",
        keywords=[".chs", ".sc", "[chs]", "[sc]", ".gb", "[gb]"],
    ),
    LanguageProfile(
        id="cht",
        mkv_language="chi",
        ietf_language="zh-Hant",
        keywords=[".cht", ".tc", "[cht]", "[tc]", "big5", "[big5]"],
    ),
    LanguageProfile(
        id="jpn",
        mkv_language="jpn",
        ietf_language="ja",
        keywords=[".jp", ".jpn", ".jap", "[jp]", "[jpn]", "[jap]"],
    ),
    LanguageProfile(
        id="rus",
        mkv_language="rus",
        ietf_language="ru",
        keywords=[".ru", ".rus", "[ru]", "[rus]"],
    ),
]


class ConfigError(ValueError):
    """Raised when a config file cannot be loaded or validated."""


def platform_config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "PlexMuxy" / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PlexMuxy" / "config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "plexmuxy" / "config.json"


def legacy_config_path() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "PlexMuxy" / "config.json"
    return Path.home() / "Documents" / "PlexMuxy" / "config.json"


def resolve_config_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    new_path = platform_config_path()
    old_path = legacy_config_path()
    if new_path.exists():
        return new_path
    if old_path.exists():
        return old_path
    return new_path


def default_config() -> AppConfig:
    return AppConfig(subtitle=SubtitleConfig(profiles=[*LANGUAGE_PROFILES]))


def default_config_dict() -> dict[str, Any]:
    data = asdict(default_config())
    data.pop("source_path", None)
    if data["task"]["output_dir"] is not None:
        data["task"]["output_dir"] = str(data["task"]["output_dir"])
    return data


def write_default_config(path: str | Path | None = None) -> Path:
    config_path = resolve_config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as output:
        json.dump(default_config_dict(), output, indent=2, ensure_ascii=False)
        output.write("\n")
    return config_path


def load_raw_config(path: str | Path | None = None, create_if_missing: bool = True) -> tuple[dict[str, Any], Path]:
    config_path = resolve_config_path(path)
    if not config_path.exists():
        if not create_if_missing:
            raise ConfigError(f"Config file does not exist: {config_path}")
        write_default_config(config_path)
    try:
        with config_path.open("r", encoding="utf-8") as source:
            data = json.load(source)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be an object: {config_path}")
    return data, config_path


def load_config(path: str | Path | None = None, create_if_missing: bool = True) -> AppConfig:
    data, config_path = load_raw_config(path, create_if_missing=create_if_missing)
    config = parse_config(data)
    config.source_path = config_path
    return config


def parse_config(data: dict[str, Any]) -> AppConfig:
    if "TaskSettings" in data:
        return parse_legacy_config(data)
    return parse_v2_config(data)


def parse_v2_config(data: dict[str, Any]) -> AppConfig:
    media_data = require_mapping(data, "media", default={})
    task_data = require_mapping(data, "task", default={})
    subtitle_data = require_mapping(data, "subtitle", default={})
    font_data = require_mapping(data, "font", default={})
    mkvmerge_data = require_mapping(data, "mkvmerge", default={})
    concurrency_data = require_mapping(data, "concurrency", default={})

    media = MediaConfig(
        video_extensions=extension_list(media_data.get("video_extensions", [".mkv", ".mp4", ".avi", ".flv"]), "media.video_extensions"),
        audio_extensions=extension_list(media_data.get("audio_extensions", [".mka"]), "media.audio_extensions"),
        subtitle_extensions=extension_list(media_data.get("subtitle_extensions", [".ass", ".ssa"]), "media.subtitle_extensions"),
        font_extensions=extension_list(media_data.get("font_extensions", [".ttf", ".otf", ".ttc"]), "media.font_extensions"),
        font_archive_extensions=extension_list(
            media_data.get("font_archive_extensions", [".zip", ".7z", ".rar"]),
            "media.font_archive_extensions",
        ),
        recursive=bool_value(media_data.get("recursive", False), "media.recursive"),
    )
    task = TaskConfig(
        output_suffix=str(task_data.get("output_suffix", "_Plex") or "_Plex"),
        output_dir=optional_path(task_data.get("output_dir")),
        overwrite=bool_value(task_data.get("overwrite", False), "task.overwrite"),
        cleanup=cleanup_mode(task_data.get("cleanup", "move"), "task.cleanup"),
        extra_dir=str(task_data.get("extra_dir", "Extra") or "Extra"),
        name_strategy=name_strategy(task_data.get("name_strategy", "suffix"), "task.name_strategy"),
        name_template=optional_string(task_data.get("name_template")),
        delete_original_video=bool_value(task_data.get("delete_original_video", False), "task.delete_original_video"),
        delete_original_audio=bool_value(task_data.get("delete_original_audio", False), "task.delete_original_audio"),
        delete_subtitle=bool_value(task_data.get("delete_subtitle", False), "task.delete_subtitle"),
    )
    profiles = parse_language_profiles(subtitle_data.get("profiles", default_config_dict()["subtitle"]["profiles"]))
    subtitle = SubtitleConfig(
        default_language=str(subtitle_data.get("default_language", "chs")),
        show_author_in_track_name=bool_value(
            subtitle_data.get("show_author_in_track_name", True),
            "subtitle.show_author_in_track_name",
        ),
        profiles=profiles,
    )
    font = FontConfig(
        delete_fonts_after_mux=bool_value(font_data.get("delete_fonts_after_mux", False), "font.delete_fonts_after_mux"),
        unrar_path=str(font_data.get("unrar_path", "")),
    )
    mkvmerge = MkvMergeConfig(path=str(mkvmerge_data.get("path", "")))
    concurrency = ConcurrencyConfig(
        thread_count=thread_count(concurrency_data.get("thread_count", "auto"), "concurrency.thread_count")
    )
    return AppConfig(
        config_version=int(data.get("config_version", 2)),
        media=media,
        task=task,
        subtitle=subtitle,
        font=font,
        mkvmerge=mkvmerge,
        concurrency=concurrency,
    )


def parse_legacy_config(data: dict[str, Any]) -> AppConfig:
    missing = [key for key in ["TaskSettings", "Font", "Subtitle", "mkvmerge", "multiprocessing"] if key not in data]
    if missing:
        raise ConfigError(f"Legacy config is missing required section(s): {', '.join(missing)}")

    task_data = require_mapping(data, "TaskSettings")
    font_data = require_mapping(data, "Font")
    subtitle_data = require_mapping(data, "Subtitle")
    keyword_data = require_mapping(subtitle_data, "Keyword", default={})
    profiles = [
        LanguageProfile(
            id="jp_sc",
            mkv_language="chi",
            ietf_language="zh-Hans",
            keywords=string_list(keyword_data.get("JP_SC", LANGUAGE_PROFILES[0].keywords), "Subtitle.Keyword.JP_SC"),
        ),
        LanguageProfile(
            id="jp_tc",
            mkv_language="chi",
            ietf_language="zh-Hant",
            keywords=string_list(keyword_data.get("JP_TC", LANGUAGE_PROFILES[1].keywords), "Subtitle.Keyword.JP_TC"),
        ),
        LanguageProfile(
            id="chs",
            mkv_language="chi",
            ietf_language="zh-Hans",
            keywords=string_list(keyword_data.get("CHS", LANGUAGE_PROFILES[2].keywords), "Subtitle.Keyword.CHS"),
        ),
        LanguageProfile(
            id="cht",
            mkv_language="chi",
            ietf_language="zh-Hant",
            keywords=string_list(keyword_data.get("CHT", LANGUAGE_PROFILES[3].keywords), "Subtitle.Keyword.CHT"),
        ),
        LanguageProfile(
            id="jpn",
            mkv_language="jpn",
            ietf_language="ja",
            keywords=string_list(keyword_data.get("JP", LANGUAGE_PROFILES[4].keywords), "Subtitle.Keyword.JP"),
        ),
        LanguageProfile(
            id="rus",
            mkv_language="rus",
            ietf_language="ru",
            keywords=string_list(keyword_data.get("RU", LANGUAGE_PROFILES[5].keywords), "Subtitle.Keyword.RU"),
        ),
    ]
    return AppConfig(
        media=MediaConfig(
            font_extensions=extension_list(font_data.get("AllowedExtensions", [".ttf", ".otf", ".ttc"]), "Font.AllowedExtensions")
        ),
        task=TaskConfig(
            output_suffix=str(task_data.get("OutputSuffixName", "_Plex") or "_Plex"),
            cleanup="move",
            extra_dir="Extra",
            delete_original_video=bool_value(task_data.get("DeleteOriginalMKV", False), "TaskSettings.DeleteOriginalMKV"),
            delete_original_audio=bool_value(task_data.get("DeleteOriginalMKA", False), "TaskSettings.DeleteOriginalMKA"),
            delete_subtitle=bool_value(task_data.get("DeleteSubtitle", False), "TaskSettings.DeleteSubtitle"),
        ),
        subtitle=SubtitleConfig(
            default_language=str(subtitle_data.get("DefaultLanguage", "chs")),
            show_author_in_track_name=bool_value(
                subtitle_data.get("ShowSubtitleAuthorInTrackName", True),
                "Subtitle.ShowSubtitleAuthorInTrackName",
            ),
            profiles=profiles,
        ),
        font=FontConfig(
            delete_fonts_after_mux=bool_value(task_data.get("DeleteFonts", False), "TaskSettings.DeleteFonts"),
            unrar_path=str(font_data.get("Unrar_Path", "")),
        ),
        mkvmerge=MkvMergeConfig(path=str(require_mapping(data, "mkvmerge").get("path", ""))),
        concurrency=ConcurrencyConfig(
            thread_count=thread_count(require_mapping(data, "multiprocessing").get("thread_count", "auto"), "multiprocessing.thread_count")
        ),
    )


def parse_language_profiles(raw_profiles: Any) -> list[LanguageProfile]:
    if not isinstance(raw_profiles, list):
        raise ConfigError("subtitle.profiles must be a list")
    profiles = []
    for index, item in enumerate(raw_profiles):
        if not isinstance(item, dict):
            raise ConfigError(f"subtitle.profiles[{index}] must be an object")
        profile_id = str(item.get("id", ""))
        if not profile_id:
            raise ConfigError(f"subtitle.profiles[{index}].id is required")
        profiles.append(
            LanguageProfile(
                id=profile_id,
                mkv_language=str(item.get("mkv_language", "")),
                ietf_language=str(item.get("ietf_language", "")),
                keywords=string_list(item.get("keywords", []), f"subtitle.profiles[{index}].keywords"),
            )
        )
    return profiles


def require_mapping(data: dict[str, Any], key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if key not in data:
        if default is not None:
            return default
        raise ConfigError(f"Missing config section: {key}")
    value = data[key]
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be an object")
    return value


def string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{field_name} must be a list of strings")
    return [item for item in value]


def extension_list(value: Any, field_name: str) -> list[str]:
    return [normalize_extension(item) for item in string_list(value, field_name)]


def normalize_extension(value: str) -> str:
    extension = value.strip().lower()
    if not extension:
        raise ConfigError("File extension cannot be empty")
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension


def bool_value(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{field_name} must be a boolean")


def thread_count(value: Any, field_name: str) -> int | str:
    if isinstance(value, bool):
        raise ConfigError(f'{field_name} must be a positive integer or "auto"')
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, str):
        if value.lower() == "auto":
            return "auto"
        if value.isnumeric() and int(value) >= 1:
            return int(value)
    raise ConfigError(f'{field_name} must be a positive integer or "auto"')


def cleanup_mode(value: Any, field_name: str) -> str:
    if value in {"none", "move", "delete"}:
        return value
    raise ConfigError(f'{field_name} must be one of "none", "move", or "delete"')


def name_strategy(value: Any, field_name: str) -> str:
    if value in {"suffix", "same-name", "template"}:
        return value
    raise ConfigError(f'{field_name} must be one of "suffix", "same-name", or "template"')


def optional_path(value: Any) -> Path | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ConfigError("task.output_dir must be a string or null")
    return Path(value).expanduser()


def optional_string(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ConfigError("Optional string field must be a string or null")
    return value


def get_config() -> dict[str, Any]:
    """Compatibility helper for callers that still expect raw config data."""
    data, _ = load_raw_config()
    return data
