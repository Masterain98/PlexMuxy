from __future__ import annotations

import hashlib
import io
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from .font import (
    extract_rar,
    is_font_file,
    safe_destination,
    seven_zip_members,
    validate_archive_file,
    validate_members,
)
from .models import FontConfig, FontFaceRef, FontOutlineType, MediaConfig


@dataclass
class FontCatalogResult:
    faces: list[FontFaceRef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_font_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).strip()
    if value.startswith("@"):
        value = value[1:]
    return " ".join(value.split()).casefold()


# Whitespace/format codepoints a renderer resolves without a dedicated glyph
# (e.g. libass draws a NO-BREAK SPACE using the regular space advance). Many CJK
# fonts omit these from their cmap even though the glyph is effectively present.
# Treating a missing entry here as a fatal "missing glyph" would force an entire
# family back to a full-font attachment, defeating font subsetting for scripts
# that merely contain a ``\h`` (U+00A0).
_RENDERER_SUBSTITUTED_CODEPOINTS = frozenset({
    0x00A0,  # NO-BREAK SPACE (ASS \h)
    0x2007,  # FIGURE SPACE
    0x202F,  # NARROW NO-BREAK SPACE
    0x2060,  # WORD JOINER
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
})


def is_optional_codepoint(codepoint: int) -> bool:
    """Return True when a font need not provide a glyph for ``codepoint``.

    Whitespace separators, control and format characters are rendered via
    substitution rather than an outline, so their absence must never block font
    matching or subsetting.
    """
    if codepoint in _RENDERER_SUBSTITUTED_CODEPOINTS:
        return True
    try:
        category = unicodedata.category(chr(codepoint))
    except (ValueError, OverflowError):
        return False
    return category in {"Zs", "Zl", "Zp", "Cc", "Cf"}


def build_font_catalog(
    font_paths: Iterable[Path],
    *,
    archives: Iterable[Path] = (),
    media_config: MediaConfig | None = None,
    font_config: FontConfig | None = None,
) -> FontCatalogResult:
    """Build a deterministic multi-face catalog without modifying user input."""

    media = media_config or MediaConfig()
    fonts = font_config or FontConfig()
    result = FontCatalogResult()
    seen_direct: set[Path] = set()
    seen_archives: set[Path] = set()

    for raw_path in sorted((Path(item) for item in font_paths), key=lambda item: str(item).casefold()):
        path = raw_path.expanduser()
        if not path.is_file() or not is_font_file(path, media.font_extensions):
            continue
        resolved = path.resolve()
        if resolved in seen_direct:
            continue
        seen_direct.add(resolved)
        try:
            payload = resolved.read_bytes()
            result.faces.extend(read_font_faces(payload, source_path=resolved))
        except Exception as exc:  # noqa: BLE001 - one bad font must be reported without hiding the remaining catalog.
            result.errors.append(f"{resolved.name}: {exc}")

    for raw_archive in sorted((Path(item) for item in archives), key=lambda item: str(item).casefold()):
        archive = raw_archive.expanduser()
        if not archive.is_file():
            continue
        resolved = archive.resolve()
        if resolved in seen_archives:
            continue
        seen_archives.add(resolved)
        try:
            result.faces.extend(_read_archive_faces(resolved, media, fonts))
        except Exception as exc:  # noqa: BLE001 - archive diagnostics belong in the plan report.
            result.errors.append(f"{resolved.name}: {exc}")

    result.faces.sort(key=font_face_sort_key)
    return result


def read_font_faces(
    payload: bytes,
    *,
    source_path: Path | None = None,
    archive_path: Path | None = None,
    archive_member: str | None = None,
    archive_digest: str | None = None,
) -> list[FontFaceRef]:
    if (source_path is None) == (archive_path is None):
        raise ValueError("Specify exactly one direct source or archive source")
    source_digest = hashlib.sha256(payload).hexdigest()
    stream = io.BytesIO(payload)
    fonts: list[TTFont] = []
    collection: TTCollection | None = None
    try:
        if payload[:4] == b"ttcf":
            collection = TTCollection(stream, lazy=False)
            fonts = list(collection.fonts)
        else:
            fonts = [TTFont(stream, lazy=False, recalcTimestamp=False)]
        return [
            _font_face_ref(
                font,
                index,
                source_digest,
                source_path=source_path,
                archive_path=archive_path,
                archive_member=archive_member,
                archive_digest=archive_digest,
            )
            for index, font in enumerate(fonts)
        ]
    finally:
        if collection is not None:
            collection.close()
        else:
            for font in fonts:
                font.close()


def font_face_sort_key(face: FontFaceRef) -> tuple[str, str, int]:
    location = face.archive_member or str(face.source_path or "")
    return (face.source_digest, location.casefold(), face.face_index)


def _font_face_ref(
    font: TTFont,
    face_index: int,
    source_digest: str,
    *,
    source_path: Path | None,
    archive_path: Path | None,
    archive_member: str | None,
    archive_digest: str | None,
) -> FontFaceRef:
    os2 = font.get("OS/2")
    head = font.get("head")
    post = font.get("post")
    weight = int(getattr(os2, "usWeightClass", 400) or 400)
    width = int(getattr(os2, "usWidthClass", 5) or 5)
    fs_selection = int(getattr(os2, "fsSelection", 0) or 0)
    mac_style = int(getattr(head, "macStyle", 0) or 0)
    italic = bool(fs_selection & 0x01 or mac_style & 0x02 or float(getattr(post, "italicAngle", 0) or 0))
    best_cmap = font.getBestCmap() or {}
    tags = tuple(sorted(str(tag) for tag in font.keys()))
    outline_type: FontOutlineType
    if "glyf" in font:
        outline_type = "truetype"
    elif "CFF2" in font:
        outline_type = "cff2"
    elif "CFF " in font:
        outline_type = "cff"
    else:
        outline_type = "unknown"
    return FontFaceRef(
        source_path=source_path,
        face_index=face_index,
        source_digest=source_digest,
        family_names=_name_values(font, {1, 21}),
        typographic_family_names=_name_values(font, {16}),
        subfamily_names=_name_values(font, {2, 17, 22}),
        full_names=_name_values(font, {4}),
        postscript_names=_name_values(font, {6}),
        weight=max(1, min(weight, 1000)),
        width=max(1, min(width, 9)),
        italic=italic,
        unicode_codepoints=tuple(sorted(int(codepoint) for codepoint in best_cmap)),
        archive_path=archive_path,
        archive_member=archive_member,
        archive_digest=archive_digest,
        outline_type=outline_type,
        is_variable="fvar" in font,
        has_color=any(tag in font for tag in ("COLR", "CPAL", "SVG ")),
        has_bitmap=any(tag in font for tag in ("CBDT", "CBLC", "EBDT", "EBLC", "sbix")),
        has_vertical_metrics="vhea" in font and "vmtx" in font,
        table_tags=tags,
    )


def _name_values(font: TTFont, name_ids: set[int]) -> tuple[str, ...]:
    table = font.get("name")
    if table is None:
        return ()
    values: dict[str, str] = {}
    for record in table.names:
        if int(record.nameID) not in name_ids:
            continue
        try:
            value = unicodedata.normalize("NFC", record.toUnicode()).strip()
        except Exception:  # noqa: BLE001 - malformed localized records should not discard usable records.
            continue
        if value:
            values.setdefault(value.casefold(), value)
    return tuple(values[key] for key in sorted(values))


def _read_archive_faces(archive: Path, media: MediaConfig, config: FontConfig) -> list[FontFaceRef]:
    validate_archive_file(archive, config.archive_limits)
    archive_digest = _sha256_path(archive)
    suffix = archive.suffix.casefold()
    if suffix == ".zip":
        return _read_zip_faces(archive, archive_digest, media, config)
    if suffix == ".7z":
        return _read_7z_faces(archive, archive_digest, media, config)
    if suffix == ".rar":
        return _read_rar_faces(archive, archive_digest, media, config)
    raise ValueError(f"Unsupported font archive extension: {archive.suffix}")


def _read_zip_faces(
    archive: Path, archive_digest: str, media: MediaConfig, config: FontConfig
) -> list[FontFaceRef]:
    result: list[FontFaceRef] = []
    with zipfile.ZipFile(archive, "r") as source:
        infos = [item for item in source.infolist() if not item.is_dir()]
        validate_members([(item.filename, item.file_size) for item in infos], config.archive_limits)
        for info in infos:
            member = info.filename.replace("\\", "/").strip("/")
            if not member or not is_font_file(Path(member), media.font_extensions):
                continue
            result.extend(read_font_faces(
                source.read(info),
                archive_path=archive,
                archive_member=member,
                archive_digest=archive_digest,
            ))
    return result


def _read_7z_faces(
    archive: Path, archive_digest: str, media: MediaConfig, config: FontConfig
) -> list[FontFaceRef]:
    import py7zr

    result: list[FontFaceRef] = []
    with tempfile.TemporaryDirectory(prefix="plexmuxy-font-catalog-") as temp_name:
        root = Path(temp_name)
        with py7zr.SevenZipFile(archive, mode="r") as source:
            members = seven_zip_members(source)
            validate_members(members, config.archive_limits)
            names = [name for name, _size in members]
            for name in names:
                safe_destination(root, name)
            source.extract(path=root, targets=names)
        for member, _size in members:
            normalized = member.replace("\\", "/").strip("/")
            path = (root / normalized).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                continue
            if is_font_file(path, media.font_extensions):
                result.extend(read_font_faces(
                    path.read_bytes(),
                    archive_path=archive,
                    archive_member=normalized,
                    archive_digest=archive_digest,
                ))
    return result


def _read_rar_faces(
    archive: Path, archive_digest: str, media: MediaConfig, config: FontConfig
) -> list[FontFaceRef]:
    if not config.archive_limits.allow_uninspected_archives:
        raise ValueError("RAR metadata cannot be inspected safely; enable allow_uninspected_archives to continue")
    result: list[FontFaceRef] = []
    with tempfile.TemporaryDirectory(prefix="plexmuxy-font-catalog-") as temp_name:
        root = Path(temp_name)
        extract_rar(archive, root, config)
        for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
            if not path.is_file() or not is_font_file(path, media.font_extensions):
                continue
            member = path.relative_to(root).as_posix()
            result.extend(read_font_faces(
                path.read_bytes(),
                archive_path=archive,
                archive_member=member,
                archive_digest=archive_digest,
            ))
    return result


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
