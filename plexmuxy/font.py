from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

from .dependencies import resolve_unrar
from .models import ArchiveLimits, FontConfig, FontResult, MediaConfig
from .subtitle import is_font_file


def prepare_fonts(
    input_dir: str | Path,
    media_config: MediaConfig,
    font_config: FontConfig,
    extract_archives: bool = True,
    preview_archives: bool = False,
) -> FontResult:
    root = Path(input_dir).expanduser().resolve()
    fonts_dir = root / "Fonts"
    result = FontResult(fonts_dir=fonts_dir if fonts_dir.exists() else None)

    if fonts_dir.exists() and not fonts_dir.is_dir():
        result.errors.append(f"Fonts path exists but is not a directory: {fonts_dir}")
        return result

    if fonts_dir.is_dir():
        result.fonts = list_font_files(fonts_dir, media_config.font_extensions)
        return result

    archives = find_font_archives(root, media_config)
    if not archives:
        return result
    if not extract_archives:
        if preview_archives:
            result.fonts = preview_font_archives(archives, fonts_dir, media_config, font_config, result)
        return result

    fonts_dir.mkdir(parents=True, exist_ok=True)
    result.fonts_dir = fonts_dir
    for archive in archives:
        try:
            validate_archive_file(archive, font_config.archive_limits)
            extracted, conflicts = extract_font_archive_with_conflicts(archive, fonts_dir, font_config)
            result.extracted_files.extend(extracted)
            result.conflicts.extend(conflicts)
        except Exception as exc:  # noqa: BLE001 - archive tools raise many library-specific errors.
            result.errors.append(f"{archive.name}: {exc}")
    result.fonts = list_font_files(fonts_dir, media_config.font_extensions)
    return result


def preview_font_archives(
    archives: list[Path],
    fonts_dir: Path,
    media_config: MediaConfig,
    font_config: FontConfig,
    result: FontResult,
) -> list[Path]:
    previewed: list[Path] = []
    for archive in archives:
        try:
            previewed.extend(preview_font_archive(archive, fonts_dir, media_config, font_config))
        except Exception as exc:  # noqa: BLE001 - preview follows the same archive error reporting path.
            result.errors.append(f"{archive.name}: {exc}")
    return sorted(previewed, key=lambda item: str(item).lower())


def preview_font_archive(
    archive: Path,
    destination: Path,
    media_config: MediaConfig,
    font_config: FontConfig,
) -> list[Path]:
    suffix = archive.suffix.lower()
    validate_archive_file(archive, font_config.archive_limits)
    if suffix == ".zip":
        names = preview_zip_names(archive, font_config.archive_limits)
    elif suffix == ".7z":
        names = preview_7z_names(archive, font_config.archive_limits)
    elif suffix == ".rar":
        raise ValueError("RAR archive preview is not supported; run without dry-run to extract it")
    else:
        raise ValueError(f"Unsupported font archive extension: {archive.suffix}")
    paths = [safe_destination(destination, name) for name in names]
    return [path for path in paths if is_font_file(path, media_config.font_extensions)]


def preview_zip_names(archive: Path, limits: ArchiveLimits | None = None) -> list[str]:
    with zipfile.ZipFile(archive, "r") as this_zip:
        infos = [item for item in this_zip.infolist() if not item.is_dir()]
        validate_members([(item.filename, item.file_size) for item in infos], limits or ArchiveLimits())
        return [decode_zip_member_name(item.filename) for item in infos]


def preview_7z_names(archive: Path, limits: ArchiveLimits | None = None) -> list[str]:
    import py7zr

    with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
        members = seven_zip_members(seven_zip)
        names = [name for name, _ in members]
        validate_members(members, limits or ArchiveLimits())
        return names


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
    extracted, _ = extract_font_archive_with_conflicts(archive, destination, font_config)
    return extracted


def extract_font_archive_with_conflicts(
    archive: Path, destination: Path, font_config: FontConfig
) -> tuple[list[Path], list[str]]:
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        return _extract_zip_with_conflicts(archive, destination, font_config.archive_limits)
    if suffix == ".7z":
        return extract_7z(archive, destination, font_config.archive_limits), []
    if suffix == ".rar":
        if not font_config.archive_limits.allow_uninspected_archives:
            raise ValueError("RAR metadata cannot be inspected safely; set allow_uninspected_archives to continue")
        return extract_rar(archive, destination, font_config), []
    raise ValueError(f"Unsupported font archive extension: {archive.suffix}")


def extract_zip(
    archive: Path, destination: Path, limits: ArchiveLimits | None = None
) -> list[Path]:
    extracted, _ = _extract_zip_with_conflicts(archive, destination, limits)
    return extracted


def _extract_zip_with_conflicts(
    archive: Path, destination: Path, limits: ArchiveLimits | None = None
) -> tuple[list[Path], list[str]]:
    extracted: list[Path] = []
    conflicts: list[str] = []
    active_limits = limits or ArchiveLimits()
    with zipfile.ZipFile(archive, "r") as this_zip:
        validate_members([(item.filename, item.file_size) for item in this_zip.infolist() if not item.is_dir()], active_limits)
        for info in this_zip.infolist():
            member = info.filename
            decoded_name = decode_zip_member_name(member)
            target = safe_destination(destination, decoded_name)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = this_zip.read(info)
            resolved_target, conflict = resolve_font_conflict(target, payload)
            if resolved_target is None:
                continue
            if conflict:
                conflicts.append(conflict)
            with resolved_target.open("xb") as output:
                output.write(payload)
            extracted.append(resolved_target)
    return extracted, conflicts


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


def extract_7z(archive: Path, destination: Path, limits: ArchiveLimits | None = None) -> list[Path]:
    import py7zr

    with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
        names = seven_zip.getnames()
        validate_members(seven_zip_members(seven_zip), limits or ArchiveLimits())
        safe_paths = [safe_destination(destination, name) for name in names]
        seven_zip.extract(path=destination, targets=names)
    return safe_paths


def extract_rar(archive: Path, destination: Path, font_config: FontConfig) -> list[Path]:
    resolution = resolve_unrar(font_config.unrar_path)
    if resolution.resolved_path is None:
        raise ValueError("Unrar path is not configured")
    import patoolib

    before = set(destination.rglob("*"))
    patoolib.extract_archive(str(archive), outdir=str(destination), program=resolution.resolved_path)
    after = set(destination.rglob("*"))
    return sorted((path for path in after - before if path.is_file()), key=lambda item: str(item).lower())


def remove_fonts_dir(fonts_dir: Path) -> None:
    if fonts_dir.exists():
        shutil.rmtree(fonts_dir)


def validate_archive_file(archive: Path, limits: ArchiveLimits) -> None:
    if archive.exists() and archive.stat().st_size > limits.max_archive_size:
        raise ValueError(f"Archive exceeds maximum size: {archive.name}")


def seven_zip_members(seven_zip) -> list[tuple[str, int | None]]:
    list_members = getattr(seven_zip, "list", None)
    if callable(list_members):
        result: list[tuple[str, int | None]] = []
        for item in list_members():
            name = str(getattr(item, "filename", ""))
            if not name or bool(getattr(item, "is_directory", False)):
                continue
            size = getattr(item, "uncompressed", None)
            result.append((name, int(size) if size is not None else None))
        return result
    return [(name, None) for name in seven_zip.getnames() if not name.endswith("/")]


def validate_members(members: list[tuple[str, int | None]], limits: ArchiveLimits) -> None:
    if len(members) > limits.max_files:
        raise ValueError("Archive contains too many files")
    total = 0
    for name, size in members:
        normalized = name.replace("\\", "/").strip("/")
        depth = len([part for part in normalized.split("/") if part])
        if depth > limits.max_depth:
            raise ValueError(f"Archive member exceeds maximum depth: {name}")
        if size is not None:
            if size > limits.max_file_size:
                raise ValueError(f"Archive member exceeds maximum size: {name}")
            total += size
    if total > limits.max_total_size:
        raise ValueError("Archive exceeds maximum uncompressed size")


def resolve_font_conflict(target: Path, payload: bytes) -> tuple[Path | None, str | None]:
    if not target.exists():
        return target, None
    existing_hash = hashlib.sha256(target.read_bytes()).digest()
    incoming_hash = hashlib.sha256(payload).digest()
    if existing_hash == incoming_hash:
        return None, None
    counter = 1
    while True:
        candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
        if not candidate.exists():
            return candidate, f"Renamed conflicting font {target.name} to {candidate.name}"
        counter += 1
