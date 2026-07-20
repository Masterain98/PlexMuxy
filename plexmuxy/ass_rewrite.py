from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from .ass_analysis import (
    AssDocument,
    analyze_ass_document,
    iter_override_tags,
    normalize_family_name,
    parse_ass_bytes,
    parse_ass_file,
    split_vertical_family,
)


class AssRewriteError(ValueError):
    """Raised when a subtitle cannot be rewritten without risking semantic damage."""


@dataclass(frozen=True)
class AssRewriteResult:
    output_bytes: bytes
    document: AssDocument
    replacement_count: int
    rewritten_families: tuple[tuple[str, str], ...]
    source_path: Path | None = None
    output_path: Path | None = None


def rewrite_ass_file(
    source_path: Path,
    destination_path: Path,
    aliases: Mapping[str, str],
) -> AssRewriteResult:
    """Write an atomically committed temporary subtitle without modifying the source."""

    source = Path(source_path)
    destination = Path(destination_path)
    if source.resolve(strict=False) == destination.resolve(strict=False):
        raise AssRewriteError("Temporary subtitle destination must differ from the source subtitle")

    source_document = parse_ass_file(source)
    result = rewrite_ass_document(source_document, aliases)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output:
            output.write(result.output_bytes)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return replace(result, source_path=source, output_path=destination)


def rewrite_ass_bytes(
    raw: bytes,
    aliases: Mapping[str, str],
    *,
    source_path: Path | None = None,
) -> bytes:
    document = parse_ass_bytes(raw, source_path=source_path)
    return rewrite_ass_document(document, aliases).output_bytes


def rewrite_ass_document(document: AssDocument, aliases: Mapping[str, str]) -> AssRewriteResult:
    analysis = analyze_ass_document(document)
    if not analysis.safe_to_rewrite:
        details = "; ".join(analysis.warnings) or "unknown structural error"
        raise AssRewriteError(f"ASS/SSA document is not safe to rewrite: {details}")

    alias_map = _normalize_aliases(aliases)
    replacements: dict[int, str] = {}
    replacement_count = 0
    rewritten_pairs: set[tuple[str, str]] = set()

    for style in document.styles:
        raw_fontname = style.fields[style.fontname_index]
        rewritten = _rewrite_family_value(raw_fontname, alias_map)
        if rewritten is None:
            continue
        new_value, original_family, alias_family = rewritten
        fields = list(style.fields)
        fields[style.fontname_index] = new_value
        replacements[style.line_index] = style.prefix + ",".join(fields)
        replacement_count += 1
        rewritten_pairs.add((original_family, alias_family))

    for event in document.events:
        if event.kind.casefold() != "dialogue":
            continue
        new_text, count, pairs = _rewrite_dialogue_text(event.text, alias_map)
        if count == 0:
            continue
        fields = list(event.fields)
        fields[event.text_index] = new_text
        replacements[event.line_index] = event.prefix + ",".join(fields)
        replacement_count += count
        rewritten_pairs.update(pairs)

    output = _serialize_with_replacements(document, replacements)
    try:
        rewritten_document = parse_ass_bytes(
            output,
            source_path=document.source_path,
            encoding_hint=document.encoding,
        )
    except (UnicodeError, ValueError) as exc:
        raise AssRewriteError(f"Rewritten ASS/SSA could not be parsed: {exc}") from exc

    rewritten_analysis = analyze_ass_document(rewritten_document)
    if not rewritten_analysis.safe_to_rewrite:
        details = "; ".join(rewritten_analysis.warnings) or "unknown structural error"
        raise AssRewriteError(f"Rewritten ASS/SSA failed structural validation: {details}")
    if rewritten_document.encoding != document.encoding or rewritten_document.bom != document.bom:
        raise AssRewriteError("Rewritten ASS/SSA did not preserve the source encoding and BOM")
    _validate_alias_references(rewritten_document, alias_map)

    return AssRewriteResult(
        output_bytes=output,
        document=rewritten_document,
        replacement_count=replacement_count,
        rewritten_families=tuple(sorted(rewritten_pairs, key=lambda item: (normalize_family_name(item[0]), item[1]))),
        source_path=document.source_path,
    )


def _normalize_aliases(aliases: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for requested_name, alias_name in aliases.items():
        key = normalize_family_name(str(requested_name))
        alias, _ = split_vertical_family(str(alias_name))
        if not key:
            raise AssRewriteError("Alias mappings cannot contain an empty source family")
        if not alias:
            raise AssRewriteError(f"Alias for {requested_name!r} cannot be empty")
        if any(character in alias for character in ",\\{}\r\n"):
            raise AssRewriteError(f"Alias {alias!r} contains characters that are unsafe in ASS font names")
        previous = normalized.get(key)
        if previous is not None and previous != alias:
            raise AssRewriteError(f"Conflicting aliases were supplied for family {requested_name!r}")
        normalized[key] = alias
    return normalized


def _rewrite_dialogue_text(
    text: str,
    alias_map: Mapping[str, str],
) -> tuple[str, int, set[tuple[str, str]]]:
    output: list[str] = []
    replacement_count = 0
    rewritten_pairs: set[tuple[str, str]] = set()
    position = 0
    while position < len(text):
        block_start = text.find("{", position)
        if block_start < 0:
            output.append(text[position:])
            break
        output.append(text[position : block_start + 1])
        block_end = text.find("}", block_start + 1)
        if block_end < 0:
            raise AssRewriteError("Dialogue contains an unclosed override block")
        block = text[block_start + 1 : block_end]
        rewritten_block, count, pairs = _rewrite_override_block(block, alias_map)
        output.append(rewritten_block)
        output.append("}")
        replacement_count += count
        rewritten_pairs.update(pairs)
        position = block_end + 1
    return "".join(output), replacement_count, rewritten_pairs


def _rewrite_override_block(
    block: str,
    alias_map: Mapping[str, str],
) -> tuple[str, int, set[tuple[str, str]]]:
    output: list[str] = []
    cursor = 0
    replacement_count = 0
    rewritten_pairs: set[tuple[str, str]] = set()
    for tag in iter_override_tags(block):
        if tag.name != "fn" or not tag.parameter.strip() or tag.parameter.strip() == "0":
            continue
        rewritten = _rewrite_family_value(tag.parameter, alias_map)
        if rewritten is None:
            continue
        new_parameter, original_family, alias_family = rewritten
        output.append(block[cursor : tag.parameter_start])
        output.append(new_parameter)
        cursor = tag.parameter_end
        replacement_count += 1
        rewritten_pairs.add((original_family, alias_family))
    if replacement_count == 0:
        return block, 0, set()
    output.append(block[cursor:])
    return "".join(output), replacement_count, rewritten_pairs


def _rewrite_family_value(
    raw_value: str,
    alias_map: Mapping[str, str],
) -> tuple[str, str, str] | None:
    leading_length = len(raw_value) - len(raw_value.lstrip())
    trailing_length = len(raw_value) - len(raw_value.rstrip())
    leading = raw_value[:leading_length]
    trailing = raw_value[len(raw_value) - trailing_length :] if trailing_length else ""
    core_end = len(raw_value) - trailing_length if trailing_length else len(raw_value)
    core = raw_value[leading_length:core_end]
    original_family, vertical = split_vertical_family(core)
    alias = alias_map.get(normalize_family_name(original_family))
    if alias is None:
        return None
    replacement = f"{'@' if vertical else ''}{alias}"
    return f"{leading}{replacement}{trailing}", original_family, alias


def _serialize_with_replacements(document: AssDocument, replacements: Mapping[int, str]) -> bytes:
    output = bytearray(document.bom)
    codec = document.codec
    for line_index, line in enumerate(document.lines):
        replacement = replacements.get(line_index)
        if replacement is None or replacement == line.content:
            output.extend(line.raw_bytes)
            continue
        try:
            output.extend((replacement + line.ending).encode(codec, errors="strict"))
        except UnicodeEncodeError as exc:
            raise AssRewriteError(
                f"Rewritten font alias cannot be represented in source encoding {document.encoding}"
            ) from exc
    return bytes(output)


def _validate_alias_references(document: AssDocument, alias_map: Mapping[str, str]) -> None:
    remaining: list[str] = []
    alias_targets = {normalize_family_name(alias) for alias in alias_map.values()}
    for style in document.styles:
        normalized = normalize_family_name(style.fontname)
        if normalized in alias_map and normalized not in alias_targets:
            remaining.append(f"Style {style.name!r}")
    for event in document.events:
        if event.kind.casefold() != "dialogue":
            continue
        position = 0
        while position < len(event.text):
            block_start = event.text.find("{", position)
            if block_start < 0:
                break
            block_end = event.text.find("}", block_start + 1)
            if block_end < 0:
                break
            block = event.text[block_start + 1 : block_end]
            for tag in iter_override_tags(block):
                normalized = normalize_family_name(tag.parameter)
                if (
                    tag.name == "fn"
                    and tag.parameter.strip()
                    and tag.parameter.strip() != "0"
                    and normalized in alias_map
                    and normalized not in alias_targets
                ):
                    remaining.append(f"Dialogue line {document.lines[event.line_index].number}")
            position = block_end + 1
    if remaining:
        locations = ", ".join(remaining[:5])
        raise AssRewriteError(f"Rewritten ASS/SSA still contains aliased source font references: {locations}")
