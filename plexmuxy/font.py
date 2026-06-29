from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .models import FontConfig, FontResult, MediaConfig
from .subtitle import is_font_file


def prepare_fonts(
    input_dir: str | Path,
    media_config: MediaConfig,
    font_config: FontConfig,
    extract_archives: bool = True,
) -> FontResult:
    root = Path(input_dir).expanduser().resolve()
    fonts_dir = root / "Fonts"
    result = FontResult(fonts_dir=fonts_dir if fonts_dir.exists() else None)

    if fonts_dir.is_dir():
        result.fonts = list_font_files(fonts_dir, media_config.font_extensions)
        return result

    archives = find_font_archives(root, media_config)
    if not archives or not extract_archives:
        return result

    fonts_dir.mkdir(parents=True, exist_ok=True)
    result.fonts_dir = fonts_dir
    for archive in archives:
        try:
            result.extracted_files.extend(extract_font_archive(archive, fonts_dir, font_config))
        except Exception as exc:  # noqa: BLE001 - archive tools raise many library-specific errors.
            result.errors.append(f"{archive.name}: {exc}")
    result.fonts = list_font_files(fonts_dir, media_config.font_extensions)
    return result


def list_font_files(fonts_dir: Path, allowed_extensions: list[str]) -> list[Path]:
    if not fonts_dir.is_dir():
        return []
    return [
        path
        for path in sorted(fonts_dir.rglob("*"), key=lambda item: str(item).lower())
        if path.is_file() and is_font_file(path, allowed_extensions)
    ]


def find_font_archives(input_dir: Path, media_config: MediaConfig) -> list[Path]:
    archive_extensions = set(media_config.font_archive_extensions)
    return [
        path
        for path in sorted(input_dir.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in archive_extensions and "font" in path.name.lower()
    ]


def extract_font_archive(archive: Path, destination: Path, font_config: FontConfig) -> list[Path]:
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        return extract_zip(archive, destination)
    if suffix == ".7z":
        return extract_7z(archive, destination)
    if suffix == ".rar":
        return extract_rar(archive, destination, font_config)
    raise ValueError(f"Unsupported font archive extension: {archive.suffix}")


def extract_zip(archive: Path, destination: Path) -> list[Path]:
    extracted: list[Path] = []
    with zipfile.ZipFile(archive, "r") as this_zip:
        for member in this_zip.namelist():
            decoded_name = decode_zip_member_name(member)
            target = safe_destination(destination, decoded_name)
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as output:
                output.write(this_zip.read(member))
            extracted.append(target)
    return extracted


def decode_zip_member_name(name: str) -> str:
    for encoding in ("utf-8", "gbk", "cp932"):
        try:
            return name.encode("cp437").decode(encoding)
        except UnicodeError:
            continue
    return name


def safe_destination(root: Path, member_name: str) -> Path:
    destination = (root / member_name).resolve()
    root_resolved = root.resolve()
    if root_resolved not in destination.parents and destination != root_resolved:
        raise ValueError(f"Archive member escapes destination: {member_name}")
    return destination


def extract_7z(archive: Path, destination: Path) -> list[Path]:
    import py7zr

    with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
        names = seven_zip.getnames()
        seven_zip.extractall(destination)
    return [safe_destination(destination, name) for name in names]


def extract_rar(archive: Path, destination: Path, font_config: FontConfig) -> list[Path]:
    if not font_config.unrar_path:
        raise ValueError("Unrar path is not configured")
    import patoolib

    before = set(destination.rglob("*"))
    patoolib.extract_archive(str(archive), outdir=str(destination), program=font_config.unrar_path)
    after = set(destination.rglob("*"))
    return sorted((path for path in after - before if path.is_file()), key=lambda item: str(item).lower())


def remove_fonts_dir(fonts_dir: Path) -> None:
    if fonts_dir.exists():
        shutil.rmtree(fonts_dir)
