from pathlib import Path

from plexmuxy.config import load_config
from plexmuxy.subtitle import detect_subtitle_info, is_font_file as _is_font_file


def subtitle_info_checker(subtitle_file_name: str) -> dict:
    config = load_config()
    info = detect_subtitle_info(Path(subtitle_file_name), config.subtitle)
    return {
        "language": info.language,
        "sub_author": info.sub_author,
        "default_language": info.default_language,
        "mkv_language": info.mkv_language,
        "ietf_language": info.ietf_language,
    }


def is_font_file(f: str) -> bool:
    config = load_config()
    return _is_font_file(f, config.media.font_extensions)
