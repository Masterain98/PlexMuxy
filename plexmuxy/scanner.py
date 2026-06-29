from __future__ import annotations

from pathlib import Path

from .models import MediaConfig, ScanResult


def scan_media_dir(input_dir: str | Path, media_config: MediaConfig) -> ScanResult:
    root = Path(input_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    result = ScanResult(input_dir=root)
    fonts_dir = root / "Fonts"
    if fonts_dir.is_dir():
        result.fonts_dir = fonts_dir

    paths = root.rglob("*") if media_config.recursive else root.iterdir()
    for path in sorted(paths, key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in media_config.video_extensions:
            result.videos.append(path)
        elif suffix in media_config.audio_extensions:
            result.audios.append(path)
        elif suffix in media_config.subtitle_extensions:
            result.subtitles.append(path)
        elif suffix in media_config.font_archive_extensions and "font" in path.name.lower():
            result.font_archives.append(path)
        else:
            result.others.append(path)

    return result
