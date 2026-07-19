from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from string import Formatter
from typing import Any

from .errors import ConfigError
from .models import (
    AppConfig,
    ArchiveLimits,
    ConcurrencyConfig,
    FfmpegConfig,
    FontCacheConfig,
    FontConfig,
    LanguageProfile,
    MatchingConfig,
    MediaConfig,
    MkvMergeConfig,
    NotificationConfig,
    PlexConfig,
    PlexPathMapping,
    SubtitleConfig,
    TaskConfig,
    TrackFilterConfig,
    UpdateConfig,
)

CURRENT_CONFIG_VERSION = 4
ROOT_FIELDS = {
    "config_version", "media", "task", "matching", "subtitle", "font",
    "font_cache", "mkvmerge", "ffmpeg", "notifications", "updates", "plex", "concurrency", "tracks",
}

LANGUAGE_PROFILES = [
    LanguageProfile("jp_sc", "chi", "zh-Hans", [".jpsc", "[jpsc]", "jp_sc", "[jp_sc]", "chs&jap", "简日"]),
    LanguageProfile("jp_tc", "chi", "zh-Hant", [".jptc", "[jptc]", "jp_tc", "[jp_tc]", "cht&jap", "繁日"]),
    LanguageProfile("chs", "chi", "zh-Hans", [".chs", ".sc", "[chs]", "[sc]", ".gb", "[gb]"]),
    LanguageProfile("cht", "chi", "zh-Hant", [".cht", ".tc", "[cht]", "[tc]", "big5", "[big5]"]),
    LanguageProfile("jpn", "jpn", "ja", [".jp", ".jpn", ".jap", "[jp]", "[jpn]", "[jap]"]),
    LanguageProfile("rus", "rus", "ru", [".ru", ".rus", "[ru]", "[rus]"]),
]


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
    return new_path if new_path.exists() or not old_path.exists() else old_path


def default_config() -> AppConfig:
    return AppConfig(subtitle=SubtitleConfig(profiles=[*LANGUAGE_PROFILES]))


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    data = asdict(config)
    data.pop("source_path", None)
    data["config_version"] = CURRENT_CONFIG_VERSION
    return _json_safe(data)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def default_config_dict() -> dict[str, Any]:
    return config_to_dict(default_config())


def save_config(config: AppConfig, path: str | Path) -> Path:
    """Validate and atomically persist a configuration file."""
    target = Path(path).expanduser()
    validated = parse_config(config_to_dict(config))
    payload = config_to_dict(validated)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            json.dump(payload, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


def write_default_config(path: str | Path | None = None) -> Path:
    return save_config(default_config(), resolve_config_path(path))


def load_raw_config(path: str | Path | None = None, create_if_missing: bool = True) -> tuple[dict[str, Any], Path]:
    config_path = resolve_config_path(path)
    if not config_path.exists():
        if not create_if_missing:
            raise ConfigError(f"Config file does not exist: {config_path}")
        write_default_config(config_path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be an object: {config_path}")
    return data, config_path


def load_config(path: str | Path | None = None, create_if_missing: bool = True) -> AppConfig:
    data, config_path = load_raw_config(path, create_if_missing=create_if_missing)
    config = parse_config(data)
    config.source_path = config_path
    return config


def migrate_config(source: str | Path, target: str | Path | None = None) -> tuple[Path, Path | None]:
    source_path = Path(source).expanduser()
    data, _ = load_raw_config(source_path, create_if_missing=False)
    migrated = parse_config(data)
    target_path = Path(target).expanduser() if target is not None else source_path
    backup: Path | None = None
    if target_path.resolve() == source_path.resolve():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = source_path.with_name(f"{source_path.name}.bak-{stamp}")
        shutil.copy2(source_path, backup)
    try:
        save_config(migrated, target_path)
    except Exception:
        if backup is not None and backup.exists() and not source_path.exists():
            shutil.copy2(backup, source_path)
        raise
    return target_path, backup


def parse_config(data: dict[str, Any]) -> AppConfig:
    if "TaskSettings" in data:
        return parse_legacy_config(data)
    version = data.get("config_version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ConfigError("config_version must be a positive integer")
    if version > CURRENT_CONFIG_VERSION:
        raise ConfigError(
            f"Config version {version} is newer than supported version {CURRENT_CONFIG_VERSION}; upgrade PlexMuxy"
        )
    unknown = sorted(set(data) - ROOT_FIELDS)
    if unknown:
        raise ConfigError(f"Unknown config field(s): {', '.join(unknown)}")
    return parse_v2_config(data)


def parse_v2_config(data: dict[str, Any]) -> AppConfig:
    media_data = require_mapping(data, "media", default={})
    task_data = require_mapping(data, "task", default={})
    matching_data = require_mapping(data, "matching", default={})
    subtitle_data = require_mapping(data, "subtitle", default={})
    font_data = require_mapping(data, "font", default={})
    font_cache_data = require_mapping(data, "font_cache", default={})
    limit_data = require_mapping(font_data, "archive_limits", default={})
    mkvmerge_data = require_mapping(data, "mkvmerge", default={})
    ffmpeg_data = require_mapping(data, "ffmpeg", default={})
    notifications_data = require_mapping(data, "notifications", default={})
    updates_data = require_mapping(data, "updates", default={})
    plex_data = require_mapping(data, "plex", default={})
    concurrency_data = require_mapping(data, "concurrency", default={})
    tracks_data = require_mapping(data, "tracks", default={})
    reject_unknown(media_data, {
        "video_extensions", "audio_extensions", "subtitle_extensions", "font_extensions",
        "font_archive_extensions", "recursive", "include_hidden", "follow_symlinks",
    }, "media")
    reject_unknown(task_data, {
        "output_suffix", "output_dir", "overwrite", "cleanup", "cleanup_overridden", "extra_dir",
        "name_strategy", "name_template", "failed_output_action", "delete_original_video",
        "delete_original_audio", "delete_subtitle",
    }, "task")
    reject_unknown(matching_data, {
        "movie_fallback", "allow_episode_only_match", "minimum_confidence", "ambiguous_action",
    }, "matching")
    reject_unknown(subtitle_data, {"default_language", "show_author_in_track_name", "profiles"}, "subtitle")
    reject_unknown(font_data, {
        "delete_fonts_after_mux", "unrar_path", "mode", "mime_mode", "missing_font_action",
        "subset_failure_action", "archive_limits",
    }, "font")
    reject_unknown(font_cache_data, {"enabled", "max_size_mb", "max_age_days"}, "font_cache")
    reject_unknown(limit_data, {
        "max_archive_size", "max_files", "max_total_size", "max_file_size", "max_depth",
        "allow_uninspected_archives",
    }, "font.archive_limits")
    reject_unknown(mkvmerge_data, {"path"}, "mkvmerge")
    reject_unknown(ffmpeg_data, {"path"}, "ffmpeg")
    reject_unknown(notifications_data, {"enabled"}, "notifications")
    reject_unknown(updates_data, {"enabled", "interval_hours", "timeout_seconds"}, "updates")
    reject_unknown(plex_data, {"enabled", "server_url", "section_id", "token_env", "path_mappings"}, "plex")
    reject_unknown(concurrency_data, {"max_parallel_mux_jobs", "thread_count"}, "concurrency")
    reject_unknown(tracks_data, {
        "audio_filter_enabled", "exclude_audio_title_patterns", "keep_audio_languages",
        "keep_default_audio", "keep_all_when_unknown", "allow_no_audio",
    }, "tracks")

    media = MediaConfig(
        video_extensions=extension_list(media_data.get("video_extensions", [".mkv", ".mp4", ".avi", ".flv"]), "media.video_extensions"),
        audio_extensions=extension_list(media_data.get("audio_extensions", [".mka"]), "media.audio_extensions"),
        subtitle_extensions=extension_list(media_data.get("subtitle_extensions", [".ass", ".ssa"]), "media.subtitle_extensions"),
        font_extensions=extension_list(media_data.get("font_extensions", [".ttf", ".otf", ".ttc", ".otc"]), "media.font_extensions"),
        font_archive_extensions=extension_list(media_data.get("font_archive_extensions", [".zip", ".7z", ".rar"]), "media.font_archive_extensions"),
        recursive=bool_value(media_data.get("recursive", False), "media.recursive"),
        include_hidden=bool_value(media_data.get("include_hidden", False), "media.include_hidden"),
        follow_symlinks=bool_value(media_data.get("follow_symlinks", False), "media.follow_symlinks"),
    )
    template = optional_string(task_data.get("name_template"))
    validate_template(template)
    task = TaskConfig(
        output_suffix=str(task_data.get("output_suffix", "_Plex") or "_Plex"),
        output_dir=optional_path(task_data.get("output_dir")),
        overwrite=bool_value(task_data.get("overwrite", False), "task.overwrite"),
        cleanup=choice(task_data.get("cleanup", "move"), {"none", "move", "delete"}, "task.cleanup"),
        cleanup_overridden=bool_value(task_data.get("cleanup_overridden", False), "task.cleanup_overridden"),
        extra_dir=str(task_data.get("extra_dir", "Extra") or "Extra"),
        name_strategy=choice(task_data.get("name_strategy", "suffix"), {"suffix", "same-name", "template"}, "task.name_strategy"),
        name_template=template,
        failed_output_action=choice(task_data.get("failed_output_action", "rename"), {"keep", "delete", "rename"}, "task.failed_output_action"),
        delete_original_video=bool_value(task_data.get("delete_original_video", False), "task.delete_original_video"),
        delete_original_audio=bool_value(task_data.get("delete_original_audio", False), "task.delete_original_audio"),
        delete_subtitle=bool_value(task_data.get("delete_subtitle", False), "task.delete_subtitle"),
    )
    matching = MatchingConfig(
        movie_fallback=bool_value(matching_data.get("movie_fallback", False), "matching.movie_fallback"),
        allow_episode_only_match=bool_value(matching_data.get("allow_episode_only_match", True), "matching.allow_episode_only_match"),
        minimum_confidence=float_range(matching_data.get("minimum_confidence", 0.7), "matching.minimum_confidence", 0, 1),
        ambiguous_action=choice(matching_data.get("ambiguous_action", "skip"), {"skip"}, "matching.ambiguous_action"),
    )
    profiles = parse_language_profiles(subtitle_data.get("profiles", default_config_dict()["subtitle"]["profiles"]))
    default_language = str(subtitle_data.get("default_language", "chs"))
    if not profiles:
        raise ConfigError("subtitle.profiles cannot be empty")
    if default_language.casefold() not in {profile.id.casefold() for profile in profiles}:
        raise ConfigError("subtitle.default_language must reference a configured profile")
    subtitle = SubtitleConfig(
        default_language=default_language,
        show_author_in_track_name=bool_value(subtitle_data.get("show_author_in_track_name", True), "subtitle.show_author_in_track_name"),
        profiles=profiles,
    )
    limits = ArchiveLimits(
        max_archive_size=positive_int(limit_data.get("max_archive_size", 256 * 1024 * 1024), "font.archive_limits.max_archive_size"),
        max_files=positive_int(limit_data.get("max_files", 2000), "font.archive_limits.max_files"),
        max_total_size=positive_int(limit_data.get("max_total_size", 1024 * 1024 * 1024), "font.archive_limits.max_total_size"),
        max_file_size=positive_int(limit_data.get("max_file_size", 256 * 1024 * 1024), "font.archive_limits.max_file_size"),
        max_depth=positive_int(limit_data.get("max_depth", 8), "font.archive_limits.max_depth"),
        allow_uninspected_archives=bool_value(limit_data.get("allow_uninspected_archives", False), "font.archive_limits.allow_uninspected_archives"),
    )
    font = FontConfig(
        delete_fonts_after_mux=bool_value(font_data.get("delete_fonts_after_mux", False), "font.delete_fonts_after_mux"),
        unrar_path=str(font_data.get("unrar_path", "")),
        mode=choice(font_data.get("mode", "all"), {"all", "referenced", "subset"}, "font.mode"),
        mime_mode=choice(font_data.get("mime_mode", "legacy"), {"legacy", "modern"}, "font.mime_mode"),
        missing_font_action=choice(font_data.get("missing_font_action", "warn"), {"warn", "skip-video", "fail-job", "fallback-all"}, "font.missing_font_action"),
        subset_failure_action=choice(
            font_data.get("subset_failure_action", "fallback-full"),
            {"fallback-full", "skip-video", "fail-job"},
            "font.subset_failure_action",
        ),
        archive_limits=limits,
    )
    font_cache = FontCacheConfig(
        enabled=bool_value(font_cache_data.get("enabled", True), "font_cache.enabled"),
        max_size_mb=positive_int(font_cache_data.get("max_size_mb", 2048), "font_cache.max_size_mb"),
        max_age_days=positive_int(font_cache_data.get("max_age_days", 90), "font_cache.max_age_days"),
    )
    using_legacy_thread_count = "max_parallel_mux_jobs" not in concurrency_data and "thread_count" in concurrency_data
    raw_parallel = concurrency_data.get("max_parallel_mux_jobs", concurrency_data.get("thread_count", 1))
    if raw_parallel == "auto":
        raw_parallel = 1
    concurrency_field = "concurrency.thread_count" if using_legacy_thread_count else "concurrency.max_parallel_mux_jobs"
    concurrency = ConcurrencyConfig(max_parallel_mux_jobs=int_range(raw_parallel, concurrency_field, 1, 4))
    tracks = TrackFilterConfig(
        audio_filter_enabled=bool_value(
            tracks_data.get("audio_filter_enabled", False), "tracks.audio_filter_enabled"
        ),
        exclude_audio_title_patterns=string_list(tracks_data.get("exclude_audio_title_patterns", []), "tracks.exclude_audio_title_patterns"),
        keep_audio_languages=string_list(tracks_data.get("keep_audio_languages", []), "tracks.keep_audio_languages"),
        keep_default_audio=bool_value(
            tracks_data.get("keep_default_audio", True), "tracks.keep_default_audio"
        ),
        keep_all_when_unknown=bool_value(tracks_data.get("keep_all_when_unknown", True), "tracks.keep_all_when_unknown"),
        allow_no_audio=bool_value(tracks_data.get("allow_no_audio", False), "tracks.allow_no_audio"),
    )
    raw_path_mappings = plex_data.get("path_mappings", [])
    if not isinstance(raw_path_mappings, list):
        raise ConfigError("plex.path_mappings must be a list")
    path_mappings: list[PlexPathMapping] = []
    for index, item in enumerate(raw_path_mappings):
        field = f"plex.path_mappings[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{field} must be an object")
        reject_unknown(item, {"local_root", "server_root"}, field)
        local_root = optional_path(item.get("local_root"))
        server_root = str(item.get("server_root", "")).strip()
        if local_root is None or not local_root.is_absolute():
            raise ConfigError(f"{field}.local_root must be an absolute path")
        if not server_root:
            raise ConfigError(f"{field}.server_root cannot be empty")
        path_mappings.append(PlexPathMapping(local_root=local_root, server_root=server_root))
    return AppConfig(
        config_version=CURRENT_CONFIG_VERSION, media=media, task=task, matching=matching,
        subtitle=subtitle, font=font, font_cache=font_cache,
        mkvmerge=MkvMergeConfig(path=str(mkvmerge_data.get("path", ""))),
        ffmpeg=FfmpegConfig(path=str(ffmpeg_data.get("path", ""))),
        notifications=NotificationConfig(
            enabled=bool_value(notifications_data.get("enabled", False), "notifications.enabled")
        ),
        updates=UpdateConfig(
            enabled=bool_value(updates_data.get("enabled", False), "updates.enabled"),
            interval_hours=int_range(updates_data.get("interval_hours", 24), "updates.interval_hours", 1, 24 * 30),
            timeout_seconds=float_range(updates_data.get("timeout_seconds", 3.0), "updates.timeout_seconds", 0.5, 15.0),
        ),
        plex=PlexConfig(
            enabled=bool_value(plex_data.get("enabled", False), "plex.enabled"),
            server_url=str(plex_data.get("server_url", "")).strip(),
            section_id=str(plex_data.get("section_id", "")).strip(),
            token_env=str(plex_data.get("token_env", "PLEXMUXY_PLEX_TOKEN")).strip() or "PLEXMUXY_PLEX_TOKEN",
            path_mappings=path_mappings,
        ),
        concurrency=concurrency, tracks=tracks,
    )


def parse_legacy_config(data: dict[str, Any]) -> AppConfig:
    missing = [key for key in ["TaskSettings", "Font", "Subtitle", "mkvmerge", "multiprocessing"] if key not in data]
    if missing:
        raise ConfigError(f"Legacy config is missing required section(s): {', '.join(missing)}")
    task_data = require_mapping(data, "TaskSettings")
    font_data = require_mapping(data, "Font")
    subtitle_data = require_mapping(data, "Subtitle")
    keyword_data = require_mapping(subtitle_data, "Keyword", default={})
    keys = ["JP_SC", "JP_TC", "CHS", "CHT", "JP", "RU"]
    profiles = [
        LanguageProfile(profile.id, profile.mkv_language, profile.ietf_language,
                        string_list(keyword_data.get(key, profile.keywords), f"Subtitle.Keyword.{key}"))
        for profile, key in zip(LANGUAGE_PROFILES, keys, strict=True)
    ]
    legacy_threads = require_mapping(data, "multiprocessing").get("thread_count", 1)
    if legacy_threads == "auto":
        legacy_threads = 1
    return AppConfig(
        media=MediaConfig(font_extensions=extension_list(font_data.get("AllowedExtensions", [".ttf", ".otf", ".ttc", ".otc"]), "Font.AllowedExtensions")),
        task=TaskConfig(
            output_suffix=str(task_data.get("OutputSuffixName", "_Plex") or "_Plex"), cleanup="move", extra_dir="Extra",
            delete_original_video=bool_value(task_data.get("DeleteOriginalMKV", False), "TaskSettings.DeleteOriginalMKV"),
            delete_original_audio=bool_value(task_data.get("DeleteOriginalMKA", False), "TaskSettings.DeleteOriginalMKA"),
            delete_subtitle=bool_value(task_data.get("DeleteSubtitle", False), "TaskSettings.DeleteSubtitle"),
        ),
        subtitle=SubtitleConfig(
            default_language=str(subtitle_data.get("DefaultLanguage", "chs")),
            show_author_in_track_name=bool_value(subtitle_data.get("ShowSubtitleAuthorInTrackName", True), "Subtitle.ShowSubtitleAuthorInTrackName"),
            profiles=profiles,
        ),
        font=FontConfig(
            delete_fonts_after_mux=bool_value(task_data.get("DeleteFonts", False), "TaskSettings.DeleteFonts"),
            unrar_path=str(font_data.get("Unrar_Path", "")),
        ),
        mkvmerge=MkvMergeConfig(path=str(require_mapping(data, "mkvmerge").get("path", ""))),
        concurrency=ConcurrencyConfig(max_parallel_mux_jobs=int_range(legacy_threads, "multiprocessing.thread_count", 1, 4)),
    )


def parse_language_profiles(raw_profiles: Any) -> list[LanguageProfile]:
    if not isinstance(raw_profiles, list):
        raise ConfigError("subtitle.profiles must be a list")
    profiles: list[LanguageProfile] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_profiles):
        if not isinstance(item, dict):
            raise ConfigError(f"subtitle.profiles[{index}] must be an object")
        reject_unknown(item, {"id", "mkv_language", "ietf_language", "keywords"}, f"subtitle.profiles[{index}]")
        profile_id = str(item.get("id", "")).strip()
        if not profile_id:
            raise ConfigError(f"subtitle.profiles[{index}].id is required")
        folded = profile_id.casefold()
        if folded in seen:
            raise ConfigError(f"Duplicate subtitle profile id: {profile_id}")
        seen.add(folded)
        profiles.append(LanguageProfile(
            id=profile_id, mkv_language=str(item.get("mkv_language", "")),
            ietf_language=str(item.get("ietf_language", "")),
            keywords=dedupe_strings(string_list(item.get("keywords", []), f"subtitle.profiles[{index}].keywords")),
        ))
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


def reject_unknown(data: dict[str, Any], allowed: set[str], field_name: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"Unknown {field_name} field(s): {', '.join(unknown)}")


def string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{field_name} must be a list of strings")
    return list(value)


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def extension_list(value: Any, field_name: str) -> list[str]:
    return dedupe_strings([normalize_extension(item) for item in string_list(value, field_name)])


def normalize_extension(value: str) -> str:
    extension = value.strip().lower()
    if not extension:
        raise ConfigError("File extension cannot be empty")
    return extension if extension.startswith(".") else f".{extension}"


def bool_value(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{field_name} must be a boolean")
    return value


def positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{field_name} must be a positive integer")
    return value


def int_range(value: Any, field_name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def float_range(value: Any, field_name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= float(value) <= maximum:
        raise ConfigError(f"{field_name} must be between {minimum} and {maximum}")
    return float(value)


def thread_count(value: Any, field_name: str) -> int | str:
    """Compatibility validator retained for external imports."""
    if value == "auto":
        return value
    return int_range(value, field_name, 1, 4)


def choice(value: Any, allowed: set[str], field_name: str) -> Any:
    if value not in allowed:
        values = ", ".join(sorted(allowed))
        raise ConfigError(f"{field_name} must be one of: {values}")
    return value


def cleanup_mode(value: Any, field_name: str) -> str:
    return choice(value, {"none", "move", "delete"}, field_name)


def name_strategy(value: Any, field_name: str) -> str:
    return choice(value, {"suffix", "same-name", "template"}, field_name)


def optional_path(value: Any) -> Path | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ConfigError("task.output_dir must be a string or null")
    if "\x00" in value:
        raise ConfigError("task.output_dir contains an invalid null character")
    return Path(value).expanduser()


def optional_string(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ConfigError("Optional string field must be a string or null")
    return value


def validate_template(template: str | None) -> None:
    if template is None:
        return
    allowed = {"stem", "name", "suffix"}
    try:
        fields = {field for _, field, _, _ in Formatter().parse(template) if field}
    except ValueError as exc:
        raise ConfigError(f"Invalid task.name_template: {exc}") from exc
    unknown = fields - allowed
    if unknown:
        raise ConfigError(f"Unknown task.name_template variable(s): {', '.join(sorted(unknown))}")


def get_config() -> dict[str, Any]:
    """Compatibility helper for callers that still expect raw config data."""
    data, _ = load_raw_config()
    return data
