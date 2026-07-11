from __future__ import annotations

import os
from pathlib import Path

from .models import MediaConfig, ScanResult


def scan_media_dir(
    input_dir: str | Path,
    media_config: MediaConfig,
    excluded_dirs: list[Path] | None = None,
) -> ScanResult:
    root = Path(input_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")
    result = ScanResult(input_dir=root)
    fonts_path = root / "Fonts"
    if fonts_path.is_dir():
        result.fonts_dir = fonts_path
    elif fonts_path.exists():
        result.warnings.append(f"Fonts path is not a directory: {fonts_path}")

    exclusions = {path.expanduser().resolve() for path in (excluded_dirs or [])}
    for path in iter_files(root, media_config, result, exclusions):
        suffix = path.suffix.casefold()
        if suffix in media_config.video_extensions:
            result.videos.append(path)
        elif suffix in media_config.audio_extensions:
            result.audios.append(path)
        elif suffix in media_config.subtitle_extensions:
            result.subtitles.append(path)
        elif suffix in media_config.font_archive_extensions and "font" in path.name.casefold():
            result.font_archives.append(path)
        else:
            result.others.append(path)
    for values in (result.videos, result.audios, result.subtitles, result.font_archives, result.others):
        values.sort(key=lambda item: str(item).casefold())
    return result


def iter_files(root: Path, config: MediaConfig, result: ScanResult, exclusions: set[Path]):
    if not config.recursive:
        try:
            entries = list(root.iterdir())
        except PermissionError as exc:
            result.warnings.append(f"Permission denied: {exc.filename or root}")
            return
        for path in entries:
            if should_skip(path, root, config, exclusions):
                continue
            try:
                if path.is_file():
                    yield path
            except OSError as exc:
                result.warnings.append(f"Cannot inspect {path}: {exc}")
        return

    def onerror(exc: OSError) -> None:
        result.warnings.append(f"Cannot scan {exc.filename or root}: {exc}")

    for current, dirs, files in os.walk(root, followlinks=config.follow_symlinks, onerror=onerror):
        current_path = Path(current)
        dirs[:] = [
            name for name in dirs
            if not should_skip(current_path / name, root, config, exclusions)
            and (current_path / name).name.casefold() != "fonts"
        ]
        for name in files:
            path = current_path / name
            if not should_skip(path, root, config, exclusions):
                yield path


def should_skip(path: Path, root: Path, config: MediaConfig, exclusions: set[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    if resolved in exclusions or any(excluded in resolved.parents for excluded in exclusions):
        return True
    if not config.include_hidden and any(part.startswith(".") for part in path.relative_to(root).parts):
        return True
    if path.is_symlink() and not config.follow_symlinks:
        return True
    return False
