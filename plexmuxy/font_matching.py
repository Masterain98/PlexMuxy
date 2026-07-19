from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .font_catalog import is_optional_codepoint, normalize_font_name
from .models import FontFaceRef, FontUsage

FontMatchStatus = Literal["matched", "missing", "ambiguous", "missing-glyphs"]


@dataclass(frozen=True)
class FontMatchResult:
    usage: FontUsage
    status: FontMatchStatus
    face: FontFaceRef | None = None
    candidates: tuple[FontFaceRef, ...] = ()
    missing_codepoints: tuple[int, ...] = ()

    @property
    def matched(self) -> bool:
        return self.status == "matched" and self.face is not None


def match_font_usage(usage: FontUsage, catalog: list[FontFaceRef]) -> FontMatchResult:
    requested = normalize_font_name(usage.normalized_family or usage.requested_family)
    ranked: list[tuple[tuple[int, int, bool, int], FontFaceRef]] = []
    for face in catalog:
        rank = _name_match_rank(requested, face)
        if rank is None:
            continue
        score = (
            rank,
            abs(int(face.weight) - int(usage.weight)),
            bool(face.italic) != bool(usage.italic),
            abs(int(face.width) - 5),
        )
        ranked.append((score, face))
    if not ranked:
        return FontMatchResult(usage, "missing")
    ranked.sort(key=lambda item: (*item[0], item[1].source_digest, item[1].face_index, _face_location(item[1])))
    best_score = ranked[0][0]
    semantic_best = [face for score, face in ranked if score == best_score]
    unique: dict[tuple[str, int], FontFaceRef] = {}
    for face in semantic_best:
        unique.setdefault((face.source_digest, face.face_index), face)
    if len(unique) > 1:
        return FontMatchResult(
            usage,
            "ambiguous",
            candidates=tuple(sorted(unique.values(), key=lambda face: (face.source_digest, face.face_index))),
        )
    face = next(iter(unique.values()))
    available = set(face.unicode_codepoints)
    missing = set(usage.codepoints) - available
    # Whitespace/format codepoints the renderer substitutes (e.g. NBSP) must not
    # count as missing glyphs; otherwise a single ``\h`` would fail the match and
    # force the whole family to a full-font fallback instead of subsetting.
    mandatory_missing = tuple(sorted(cp for cp in missing if not is_optional_codepoint(cp)))
    if mandatory_missing:
        return FontMatchResult(usage, "missing-glyphs", face=face, missing_codepoints=mandatory_missing)
    return FontMatchResult(usage, "matched", face=face)


def match_font_usages(usages: list[FontUsage], catalog: list[FontFaceRef]) -> list[FontMatchResult]:
    return [match_font_usage(usage, catalog) for usage in usages]


def _name_match_rank(requested: str, face: FontFaceRef) -> int | None:
    if requested in _normalized(face.typographic_family_names):
        return 0
    if requested in _normalized(face.family_names):
        return 1
    if requested in _normalized((*face.full_names, *face.postscript_names)):
        return 2
    stems = {_font_stem(face)}
    if requested and requested in stems:
        return 3
    return None


def _normalized(values: tuple[str, ...]) -> set[str]:
    return {normalize_font_name(value) for value in values if value}


def _font_stem(face: FontFaceRef) -> str:
    location = face.archive_member or str(face.source_path or "")
    return normalize_font_name(Path(location).stem)


def _face_location(face: FontFaceRef) -> str:
    return (face.archive_member or str(face.source_path or "")).casefold()
