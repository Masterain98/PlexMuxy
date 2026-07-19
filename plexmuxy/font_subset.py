from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

from .font_catalog import is_optional_codepoint
from .models import FontFaceRef, FontMimeMode, font_mime_type_for_outline

# Bump whenever the produced subset bytes can change for identical inputs.
# v2: stopped rewriting/collapsing the font name table -- the original name
# records (including GDI-packed weight families such as "HYXuanSong 65S" or
# "FOT-TsukuMin Pr6N E") are now preserved verbatim. This version bump forces
# every stale persistent-cache entry AND every previously stored plan intent to
# be regenerated, so a re-run cannot silently reuse the old name-collapsed
# subsets that broke libass font matching.
SUBSET_PROFILE_VERSION = 2
UNSAFE_GLYPH_TABLES = frozenset({"Silf", "Sill", "Glat", "Gloc", "morx", "mort", "kerx", "ankr"})


class FontSubsetError(RuntimeError):
    pass


@dataclass(frozen=True)
class FontSubsetResult:
    path: Path
    alias_family: str
    subfamily: str
    mime_type: str
    sha256: str
    source_size: int
    output_size: int
    codepoint_count: int


class _WarningCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def subset_font_face(
    face: FontFaceRef,
    source_path: Path,
    codepoints: set[int] | tuple[int, ...] | list[int],
    alias_family: str,
    output_path: Path,
    *,
    mime_mode: FontMimeMode = "legacy",
) -> FontSubsetResult:
    """Create and validate one deterministic, independently attachable face."""

    requested = {int(value) for value in codepoints}
    if not requested:
        raise FontSubsetError("Cannot create an empty font subset")
    if not alias_family.isascii() or not alias_family.replace("_", "").isalnum():
        raise FontSubsetError(f"Invalid subset alias: {alias_family}")
    if face.has_color or face.has_bitmap:
        raise FontSubsetError("Color and bitmap fonts use full-font fallback in subset profile 1")
    unsafe = sorted(set(face.table_tags) & UNSAFE_GLYPH_TABLES)
    if unsafe:
        raise FontSubsetError(f"Unsupported glyph-indexed font tables: {', '.join(unsafe)}")
    if face.outline_type == "unknown":
        raise FontSubsetError("Font outline type is unsupported")

    source = Path(source_path).resolve()
    if not source.is_file():
        raise FontSubsetError(f"Font source does not exist: {source}")
    if _sha256_path(source) != face.source_digest:
        raise FontSubsetError(f"Font source digest changed: {source}")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_extension = output_extension(face)
    if output.suffix.casefold() != expected_extension:
        raise FontSubsetError(f"Subset output must use {expected_extension}: {output}")

    font = TTFont(source, fontNumber=face.face_index, lazy=False, recalcTimestamp=False)
    original_modified = int(getattr(font.get("head"), "modified", 0) or 0)
    available = set((font.getBestCmap() or {}).keys())
    missing = requested - available
    if missing:
        mandatory_missing = sorted(cp for cp in missing if not is_optional_codepoint(cp))
        if mandatory_missing:
            font.close()
            raise FontSubsetError(
                f"Source font is missing requested codepoints: {_format_codepoints(mandatory_missing)}"
            )
        # The only absentees are whitespace/format codepoints the renderer
        # substitutes (e.g. NBSP). Drop them from the request so the family can
        # still be subset instead of falling back to the full source font.
        requested -= missing
    if not requested:
        font.close()
        raise FontSubsetError("Cannot create an empty font subset")

    options = subset.Options()
    options.layout_features = ["*"]
    options.layout_scripts = ["*"]
    options.hinting = True
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.legacy_cmap = True
    options.symbol_cmap = True
    options.glyph_names = True
    options.ignore_missing_unicodes = False
    options.passthrough_tables = False

    collector = _WarningCollector()
    logger = logging.getLogger("fontTools")
    logger.addHandler(collector)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=requested)
        subsetter.subset(font)
        # Preserve the ORIGINAL name table verbatim (the subsetter keeps every
        # record via ``name_IDs=["*"]``). Players/libass match embedded fonts by
        # the name records baked into the file, so the subset must expose the
        # exact same family names as the source -- including GDI-packed weight
        # variants such as "FOT-TsukuMin Pr6N E", "HYXuanSong 65S" or
        # "Hiragino Mincho StdN W7". Rewriting/collapsing these names to a single
        # normalized family made styles that reference the packed name fail to
        # match, so the renderer silently fell back to a default font.
        # The deterministic ``alias_family`` remains only an opaque
        # cache/attachment identifier and is never written into the font.
        if "head" in font:
            font["head"].modified = original_modified
        font.recalcTimestamp = False
        if collector.messages:
            raise FontSubsetError(f"FontTools emitted warnings: {'; '.join(dict.fromkeys(collector.messages))}")
        font.save(temporary, reorderTables=True)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, FontSubsetError):
            raise
        raise FontSubsetError(str(exc)) from exc
    finally:
        logger.removeHandler(collector)
        font.close()

    try:
        validate_subset_font(temporary, face, face.family_names[0], requested)
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return FontSubsetResult(
        path=output,
        alias_family=alias_family,
        subfamily=style_name(face),
        mime_type=font_mime_type(face, mime_mode=mime_mode),
        sha256=_sha256_path(output),
        source_size=source.stat().st_size,
        output_size=output.stat().st_size,
        codepoint_count=len(requested),
    )


def validate_subset_font(
    path: Path,
    source_face: FontFaceRef,
    target_family: str,
    requested_codepoints: set[int],
) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FontSubsetError(f"Subset font is empty: {path}")
    try:
        font = TTFont(path, lazy=False, recalcTimestamp=False)
    except Exception as exc:
        raise FontSubsetError(f"Subset font cannot be reopened: {exc}") from exc
    try:
        cmap_table = font.get("cmap")
        if cmap_table is None:
            raise FontSubsetError("Subset font has no cmap table")
        # Consider every cmap subtable, not just ``getBestCmap()``: that helper
        # returns a single (legacy) subtable, so codepoints the subsetter placed
        # only in another subtable (e.g. a format-12 full Unicode cmap) would be
        # falsely reported missing.
        present = set()
        for subtable in cmap_table.tables:
            present |= set(subtable.cmap.keys())
        missing = sorted(requested_codepoints - present)
        if missing:
            # Renderer-substituted codepoints (NBSP, ZWSP, word joiners, etc.)
            # need no dedicated glyph and may be dropped by the subsetter even
            # when requested; the renderer substitutes them, so their absence
            # never breaks rendering. Do not treat them as a subsetting failure.
            missing = [cp for cp in missing if not is_optional_codepoint(cp)]
            if missing:
                raise FontSubsetError(f"Subset cmap is missing codepoints: {_format_codepoints(missing)}")
        names = font.get("name")
        if names is None:
            raise FontSubsetError("Subset font has no name table")
        family_records = [
            record.toUnicode().strip()
            for record in names.names
            if int(record.nameID) in {1, 16, 21}
        ]
        if not family_records or target_family not in family_records:
            raise FontSubsetError(
                f"Subset family name was not set to {target_family!r}: found {sorted(set(family_records))}"
            )
        os2 = font.get("OS/2")
        head = font.get("head")
        if os2 is not None:
            if int(getattr(os2, "usWeightClass", 400)) != source_face.weight:
                raise FontSubsetError("Subset weight metadata changed")
            if int(getattr(os2, "usWidthClass", 5)) != source_face.width:
                raise FontSubsetError("Subset width metadata changed")
        if head is not None:
            italic = bool(int(getattr(head, "macStyle", 0)) & 0x02)
            if italic != source_face.italic:
                raise FontSubsetError("Subset italic metadata changed")
    finally:
        font.close()


def style_name(face: FontFaceRef) -> str:
    bold = face.weight >= 700
    if bold and face.italic:
        return "Bold Italic"
    if bold:
        return "Bold"
    if face.italic:
        return "Italic"
    return "Regular"


def output_extension(face: FontFaceRef) -> str:
    return ".ttf" if face.outline_type == "truetype" else ".otf"


def font_mime_type(face: FontFaceRef, *, mime_mode: FontMimeMode = "legacy") -> str:
    return font_mime_type_for_outline(face.outline_type, mode=mime_mode)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_codepoints(values: list[int]) -> str:
    preview = ", ".join(f"U+{value:04X}" for value in values[:12])
    return f"{preview}, …" if len(values) > 12 else preview
