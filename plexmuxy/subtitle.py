from __future__ import annotations

import re
from pathlib import Path

from .models import LanguageProfile, SubtitleConfig, SubtitleInfo


AUTHOR_RE = re.compile(r"^\[([^\]]+)\]")


def detect_subtitle_info(path: str | Path, config: SubtitleConfig) -> SubtitleInfo:
    file_name = Path(path).name
    file_name_lower = file_name.lower()
    profile = select_subtitle_profile(file_name_lower, config)

    if profile is not None:
        language = profile.id
        return SubtitleInfo(
            language=language,
            track_name_language=language,
            mkv_language=profile.mkv_language,
            ietf_language=profile.ietf_language,
            sub_author=detect_subtitle_author(file_name),
            default_language=is_default_language(language, config.default_language),
        )

    return SubtitleInfo(
        language="",
        track_name_language="",
        mkv_language="",
        ietf_language="",
        sub_author=detect_subtitle_author(file_name),
        default_language=False,
    )


def select_subtitle_profile(file_name_lower: str, config: SubtitleConfig) -> LanguageProfile | None:
    best_match = None
    best_keyword_length = -1
    for profile_index, profile in enumerate(config.profiles):
        for keyword in profile.keywords:
            normalized_keyword = keyword.lower()
            if normalized_keyword not in file_name_lower:
                continue
            keyword_length = len(normalized_keyword)
            if keyword_length > best_keyword_length:
                best_match = (profile_index, profile)
                best_keyword_length = keyword_length
    if best_match is None:
        return None
    return best_match[1]


def detect_subtitle_author(file_name: str | Path) -> str:
    match = AUTHOR_RE.search(Path(file_name).name)
    if match is None:
        return ""
    return match.group(1)


def is_default_language(language: str, default_language: str) -> bool:
    if language == default_language:
        return True
    if language == "jp_sc" and default_language == "chs":
        return True
    if language == "jp_tc" and default_language == "cht":
        return True
    return False


def build_track_name(info: SubtitleInfo, config: SubtitleConfig) -> str:
    if not info.language:
        return ""
    if config.show_author_in_track_name and info.sub_author:
        return f"{info.track_name_language} {info.sub_author}"
    return info.track_name_language


def is_font_file(path: str | Path, allowed_extensions: list[str]) -> bool:
    normalized_extensions = {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in allowed_extensions
    }
    return Path(path).suffix.lower() in normalized_extensions
