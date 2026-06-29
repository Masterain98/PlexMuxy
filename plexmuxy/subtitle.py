from __future__ import annotations

import re
from pathlib import Path

from .models import SubtitleConfig, SubtitleInfo


AUTHOR_RE = re.compile(r"^\[([^\]]+)\]")


def detect_subtitle_info(path: str | Path, config: SubtitleConfig) -> SubtitleInfo:
    file_name = Path(path).name
    file_name_lower = file_name.lower()

    for profile in config.profiles:
        if any(keyword.lower() in file_name_lower for keyword in profile.keywords):
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
    return Path(path).suffix.lower() in {extension.lower() for extension in allowed_extensions}
