from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


class AssDecodeError(ValueError):
    """Raised when an ASS/SSA document cannot be decoded without replacement."""


@dataclass(frozen=True)
class AssIssue:
    code: str
    message: str
    line_number: int | None = None
    analysis_incomplete: bool = False
    rewrite_unsafe: bool = False


@dataclass(frozen=True)
class AssLine:
    number: int
    content: str
    ending: str
    raw_bytes: bytes


@dataclass(frozen=True)
class AssStyle:
    section: str
    line_index: int
    prefix: str
    format_fields: tuple[str, ...]
    fields: tuple[str, ...]
    name_index: int
    fontname_index: int
    bold_index: int | None
    italic_index: int | None
    name: str
    fontname: str
    bold: bool
    italic: bool


@dataclass(frozen=True)
class AssEvent:
    kind: str
    line_index: int
    prefix: str
    format_fields: tuple[str, ...]
    fields: tuple[str, ...]
    style_index: int
    text_index: int
    style_name: str
    text: str


@dataclass(frozen=True)
class OverrideTag:
    name: str
    parameter: str
    start: int
    end: int
    parameter_start: int
    parameter_end: int
    parenthesis_depth: int = 0


@dataclass(frozen=True)
class FontUsage:
    requested_family: str
    normalized_family: str
    weight: int
    italic: bool
    vertical: bool
    codepoints: tuple[int, ...]
    subtitle_paths: tuple[Path, ...]


@dataclass(frozen=True)
class AssDocument:
    source_path: Path | None
    encoding: str
    bom: bytes
    newline: str
    lines: tuple[AssLine, ...]
    styles: tuple[AssStyle, ...]
    events: tuple[AssEvent, ...]
    issues: tuple[AssIssue, ...]
    original_bytes: bytes

    @property
    def style_map(self) -> dict[str, AssStyle]:
        return {style.name: style for style in self.styles}

    @property
    def codec(self) -> str:
        return _codec_for_encoding(self.encoding)

    def to_bytes(self) -> bytes:
        """Return the exact input bytes, including the original BOM and newlines."""

        return self.original_bytes


@dataclass(frozen=True)
class AssAnalysis:
    document: AssDocument
    usages: tuple[FontUsage, ...]
    issues: tuple[AssIssue, ...]

    @property
    def safe_to_rewrite(self) -> bool:
        return not any(issue.rewrite_unsafe for issue in self.issues)

    @property
    def complete(self) -> bool:
        return not any(issue.analysis_incomplete for issue in self.issues)

    @property
    def warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        for issue in self.issues:
            location = f"line {issue.line_number}: " if issue.line_number is not None else ""
            warnings.append(f"{location}{issue.message}")
        return tuple(warnings)


@dataclass
class RenderState:
    family: str
    weight: int
    italic: bool
    drawing_level: int = 0


_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"
_STYLE_SECTIONS = {"v4 styles", "v4+ styles"}
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)]\s*$")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_family_name(name: str) -> str:
    """Normalize an ASS family for matching while ignoring the vertical ``@`` marker."""

    family, _ = split_vertical_family(name)
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", family)).strip().casefold()


def split_vertical_family(name: str) -> tuple[str, bool]:
    stripped = name.strip()
    vertical = stripped.startswith("@")
    if vertical:
        stripped = stripped[1:].strip()
    return stripped, vertical


def parse_ass_file(path: Path, *, encoding_hint: str | None = None) -> AssDocument:
    path = Path(path)
    return parse_ass_bytes(path.read_bytes(), source_path=path, encoding_hint=encoding_hint)


def parse_ass_bytes(
    raw: bytes,
    *,
    source_path: Path | None = None,
    encoding_hint: str | None = None,
) -> AssDocument:
    if encoding_hint is None:
        encoding, bom, payload, encoding_issue = _detect_encoding(raw)
    else:
        encoding, bom, payload = _use_encoding_hint(raw, encoding_hint)
        encoding_issue = None
    codec = _codec_for_encoding(encoding)
    # Decode the complete payload first so malformed trailing code units are rejected.
    payload.decode(codec, errors="strict")

    lines: list[AssLine] = []
    for index, raw_line in enumerate(_split_raw_lines(payload, encoding)):
        decoded = raw_line.decode(codec, errors="strict")
        content, ending = _split_line_ending(decoded)
        lines.append(AssLine(number=index + 1, content=content, ending=ending, raw_bytes=raw_line))

    styles, events, issues = _parse_structure(lines)
    if encoding_issue is not None:
        issues.insert(0, encoding_issue)
    newline = _dominant_newline(lines)
    return AssDocument(
        source_path=Path(source_path) if source_path is not None else None,
        encoding=encoding,
        bom=bom,
        newline=newline,
        lines=tuple(lines),
        styles=tuple(styles),
        events=tuple(events),
        issues=tuple(issues),
        original_bytes=raw,
    )


def parse_ass(source: Path | str | bytes, *, encoding_hint: str | None = None) -> AssDocument:
    if isinstance(source, bytes):
        return parse_ass_bytes(source, encoding_hint=encoding_hint)
    return parse_ass_file(Path(source), encoding_hint=encoding_hint)


def analyze_ass_file(path: Path, *, encoding_hint: str | None = None) -> AssAnalysis:
    return analyze_ass_document(parse_ass_file(path, encoding_hint=encoding_hint))


def analyze_ass_bytes(
    raw: bytes,
    *,
    source_path: Path | None = None,
    encoding_hint: str | None = None,
) -> AssAnalysis:
    return analyze_ass_document(
        parse_ass_bytes(raw, source_path=source_path, encoding_hint=encoding_hint)
    )


def analyze_ass(source: Path | str | bytes, *, encoding_hint: str | None = None) -> AssAnalysis:
    if isinstance(source, bytes):
        return analyze_ass_bytes(source, encoding_hint=encoding_hint)
    return analyze_ass_file(Path(source), encoding_hint=encoding_hint)


def analyze_ass_document(document: AssDocument) -> AssAnalysis:
    issues = list(document.issues)
    style_map = document.style_map
    codepoints: dict[tuple[str, int, bool, bool], set[int]] = {}
    display_names: dict[tuple[str, int, bool, bool], str] = {}
    missing_families_reported: set[tuple[int, str]] = set()

    def add_codepoint(state: RenderState, value: int, line_number: int) -> None:
        if state.drawing_level > 0:
            return
        family, vertical = split_vertical_family(state.family)
        normalized = normalize_family_name(family)
        if not normalized:
            marker = (line_number, state.family)
            if marker not in missing_families_reported:
                missing_families_reported.add(marker)
                issues.append(
                    AssIssue(
                        code="empty_font_family",
                        message="Rendered text has no resolvable font family",
                        line_number=line_number,
                        analysis_incomplete=True,
                    )
                )
            return
        key = (normalized, state.weight, state.italic, vertical)
        display_names.setdefault(key, family)
        codepoints.setdefault(key, set()).add(value)

    for event in document.events:
        if event.kind.casefold() != "dialogue":
            continue
        line_number = document.lines[event.line_index].number
        dialogue_style = style_map.get(event.style_name)
        if dialogue_style is None:
            issues.append(
                AssIssue(
                    code="unknown_dialogue_style",
                    message=f"Dialogue references unknown Style {event.style_name!r}",
                    line_number=line_number,
                    analysis_incomplete=True,
                )
            )
            _report_unclosed_override(event.text, line_number, issues)
            continue

        current_style = dialogue_style
        state = _state_from_style(dialogue_style)
        position = 0
        while position < len(event.text):
            character = event.text[position]
            if character == "{":
                block_end = event.text.find("}", position + 1)
                if block_end < 0:
                    issues.append(
                        AssIssue(
                            code="unclosed_override_block",
                            message="Dialogue contains an unclosed override block",
                            line_number=line_number,
                            analysis_incomplete=True,
                            rewrite_unsafe=True,
                        )
                    )
                    break
                block = event.text[position + 1 : block_end]
                state, current_style = _apply_override_block(
                    block,
                    state=state,
                    current_style=current_style,
                    dialogue_style=dialogue_style,
                    style_map=style_map,
                    line_number=line_number,
                    issues=issues,
                )
                position = block_end + 1
                continue

            if character == "\\" and position + 1 < len(event.text):
                escape = event.text[position + 1]
                if escape in {"N", "n"}:
                    position += 2
                    continue
                if escape == "h":
                    add_codepoint(state, 0x00A0, line_number)
                    position += 2
                    continue
                if escape == "\\":
                    add_codepoint(state, ord("\\"), line_number)
                    position += 2
                    continue

            add_codepoint(state, ord(character), line_number)
            position += 1

    subtitle_paths = (document.source_path,) if document.source_path is not None else ()
    usages: list[FontUsage] = []
    for key in sorted(codepoints, key=lambda item: (item[0], item[3], item[1], item[2])):
        normalized, weight, italic, vertical = key
        values = codepoints[key]
        values.update({0x0020, 0x00A0})
        usages.append(
            FontUsage(
                requested_family=display_names[key],
                normalized_family=normalized,
                weight=weight,
                italic=italic,
                vertical=vertical,
                codepoints=tuple(sorted(values)),
                subtitle_paths=subtitle_paths,
            )
        )

    return AssAnalysis(document=document, usages=tuple(usages), issues=tuple(issues))


def iter_override_tags(block: str) -> tuple[OverrideTag, ...]:
    """Parse the state-changing tags PlexMuxy needs from one override block."""

    tags: list[OverrideTag] = []
    position = 0
    while position < len(block):
        slash = block.find("\\", position)
        if slash < 0 or slash + 1 >= len(block):
            break
        tag_start = slash + 1
        remainder = block[tag_start:]
        lowered = remainder.casefold()
        parenthesis_depth = _parenthesis_depth_at(block, slash)

        if lowered.startswith("fn"):
            parameter_start = tag_start + 2
            parameter_end = _next_tag_parameter_end(block, parameter_start, parenthesis_depth)
            tags.append(
                OverrideTag(
                    name="fn",
                    parameter=block[parameter_start:parameter_end],
                    start=slash,
                    end=parameter_end,
                    parameter_start=parameter_start,
                    parameter_end=parameter_end,
                    parenthesis_depth=parenthesis_depth,
                )
            )
            position = parameter_end
            continue

        first = lowered[0]
        if first in {"b", "i", "p"} and _numeric_tag_boundary(remainder):
            parameter_start = tag_start + 1
            parameter_end = _signed_integer_end(block, parameter_start)
            tags.append(
                OverrideTag(
                    name=first,
                    parameter=block[parameter_start:parameter_end],
                    start=slash,
                    end=parameter_end,
                    parameter_start=parameter_start,
                    parameter_end=parameter_end,
                    parenthesis_depth=parenthesis_depth,
                )
            )
            position = max(parameter_end, parameter_start)
            continue

        if first == "r":
            parameter_start = tag_start + 1
            parameter_end = _next_tag_parameter_end(block, parameter_start, parenthesis_depth)
            tags.append(
                OverrideTag(
                    name="r",
                    parameter=block[parameter_start:parameter_end],
                    start=slash,
                    end=parameter_end,
                    parameter_start=parameter_start,
                    parameter_end=parameter_end,
                    parenthesis_depth=parenthesis_depth,
                )
            )
            position = parameter_end
            continue

        position = _next_tag_start(block, tag_start + 1)

    return tuple(tags)


def _apply_override_block(
    block: str,
    *,
    state: RenderState,
    current_style: AssStyle,
    dialogue_style: AssStyle,
    style_map: dict[str, AssStyle],
    line_number: int,
    issues: list[AssIssue],
) -> tuple[RenderState, AssStyle]:
    reported_nested_override = False
    for tag in iter_override_tags(block):
        if tag.parenthesis_depth > 0 and tag.name != "fn":
            if not reported_nested_override:
                issues.append(
                    AssIssue(
                        code="animated_font_override",
                        message=(
                            "Animated or nested font-state override cannot be reduced to one "
                            "deterministic render state"
                        ),
                        line_number=line_number,
                        analysis_incomplete=True,
                    )
                )
                reported_nested_override = True
            continue
        parameter = tag.parameter.strip()
        if tag.name == "fn":
            state.family = parameter if parameter and parameter != "0" else current_style.fontname
            continue

        if tag.name == "b":
            value = _parse_int(parameter)
            if value == 0:
                state.weight = 400
            elif value == -1:
                state.weight = 700 if current_style.bold else 400
            elif value == 1:
                state.weight = 700
            elif value is not None and 100 <= value <= 900:
                state.weight = value
            else:
                _invalid_override_issue(tag, line_number, issues)
            continue

        if tag.name == "i":
            value = _parse_int(parameter)
            if value == 0:
                state.italic = False
            elif value == -1:
                state.italic = current_style.italic
            elif value == 1:
                state.italic = True
            else:
                _invalid_override_issue(tag, line_number, issues)
            continue

        if tag.name == "p":
            value = _parse_int(parameter)
            if value is None:
                _invalid_override_issue(tag, line_number, issues)
            else:
                state.drawing_level = max(0, value)
            continue

        if tag.name == "r":
            if not parameter:
                current_style = dialogue_style
                state = _state_from_style(dialogue_style)
                continue
            reset_style = style_map.get(parameter)
            if reset_style is None:
                issues.append(
                    AssIssue(
                        code="unknown_reset_style",
                        message=f"Override tag references unknown Style {parameter!r}",
                        line_number=line_number,
                        analysis_incomplete=True,
                    )
                )
                continue
            current_style = reset_style
            state = _state_from_style(reset_style)

    return state, current_style


def _state_from_style(style: AssStyle) -> RenderState:
    return RenderState(
        family=style.fontname,
        weight=700 if style.bold else 400,
        italic=style.italic,
        drawing_level=0,
    )


def _invalid_override_issue(tag: OverrideTag, line_number: int, issues: list[AssIssue]) -> None:
    issues.append(
        AssIssue(
            code="invalid_override_parameter",
            message=f"Invalid \\{tag.name} override parameter {tag.parameter!r}",
            line_number=line_number,
            analysis_incomplete=True,
        )
    )


def _report_unclosed_override(text: str, line_number: int, issues: list[AssIssue]) -> None:
    position = 0
    while position < len(text):
        start = text.find("{", position)
        if start < 0:
            return
        end = text.find("}", start + 1)
        if end < 0:
            issues.append(
                AssIssue(
                    code="unclosed_override_block",
                    message="Dialogue contains an unclosed override block",
                    line_number=line_number,
                    analysis_incomplete=True,
                    rewrite_unsafe=True,
                )
            )
            return
        position = end + 1


def _parse_structure(lines: list[AssLine]) -> tuple[list[AssStyle], list[AssEvent], list[AssIssue]]:
    styles: list[AssStyle] = []
    events: list[AssEvent] = []
    issues: list[AssIssue] = []
    section = ""
    active_format: tuple[str, ...] | None = None
    seen_style_names: set[str] = set()

    for line_index, line in enumerate(lines):
        section_match = _SECTION_RE.match(line.content)
        if section_match:
            section = section_match.group(1).strip().casefold()
            active_format = None
            continue

        directive = _split_directive(line.content)
        if directive is None:
            continue
        kind, prefix, payload = directive
        normalized_kind = kind.casefold()

        if normalized_kind == "format" and (section in _STYLE_SECTIONS or section == "events"):
            fields = tuple(field.strip() for field in payload.split(","))
            if not fields or any(not field for field in fields):
                issues.append(
                    AssIssue(
                        code="invalid_format",
                        message=f"Invalid Format declaration in [{section}]",
                        line_number=line.number,
                        analysis_incomplete=True,
                        rewrite_unsafe=True,
                    )
                )
                active_format = None
            else:
                active_format = fields
            continue

        if section in _STYLE_SECTIONS and normalized_kind == "style":
            style = _parse_style_line(
                section=section,
                line_index=line_index,
                line=line,
                prefix=prefix,
                payload=payload,
                format_fields=active_format,
                issues=issues,
            )
            if style is not None:
                if style.name in seen_style_names:
                    issues.append(
                        AssIssue(
                            code="duplicate_style",
                            message=f"Duplicate Style name {style.name!r}",
                            line_number=line.number,
                            analysis_incomplete=True,
                        )
                    )
                seen_style_names.add(style.name)
                styles.append(style)
            continue

        if section == "events" and normalized_kind != "format":
            event = _parse_event_line(
                kind=kind,
                line_index=line_index,
                line=line,
                prefix=prefix,
                payload=payload,
                format_fields=active_format,
                issues=issues,
            )
            if event is not None:
                events.append(event)

    return styles, events, issues


def _parse_style_line(
    *,
    section: str,
    line_index: int,
    line: AssLine,
    prefix: str,
    payload: str,
    format_fields: tuple[str, ...] | None,
    issues: list[AssIssue],
) -> AssStyle | None:
    if format_fields is None:
        issues.append(
            AssIssue(
                code="style_without_format",
                message="Style appears before a valid Format declaration",
                line_number=line.number,
                analysis_incomplete=True,
                rewrite_unsafe=True,
            )
        )
        return None

    indexes = _field_indexes(format_fields)
    missing = [name for name in ("name", "fontname", "bold", "italic") if name not in indexes]
    if missing:
        issues.append(
            AssIssue(
                code="style_format_missing_fields",
                message=f"Style Format is missing required fields: {', '.join(missing)}",
                line_number=line.number,
                analysis_incomplete=True,
                rewrite_unsafe=True,
            )
        )
        return None

    fields = tuple(payload.split(",", max(0, len(format_fields) - 1)))
    if len(fields) != len(format_fields):
        issues.append(
            AssIssue(
                code="malformed_style",
                message="Style field count does not match its Format declaration",
                line_number=line.number,
                analysis_incomplete=True,
                rewrite_unsafe=True,
            )
        )
        return None

    return AssStyle(
        section=section,
        line_index=line_index,
        prefix=prefix,
        format_fields=format_fields,
        fields=fields,
        name_index=indexes["name"],
        fontname_index=indexes["fontname"],
        bold_index=indexes.get("bold"),
        italic_index=indexes.get("italic"),
        name=fields[indexes["name"]].strip(),
        fontname=fields[indexes["fontname"]].strip(),
        bold=_parse_ass_bool(fields[indexes["bold"]]),
        italic=_parse_ass_bool(fields[indexes["italic"]]),
    )


def _parse_event_line(
    *,
    kind: str,
    line_index: int,
    line: AssLine,
    prefix: str,
    payload: str,
    format_fields: tuple[str, ...] | None,
    issues: list[AssIssue],
) -> AssEvent | None:
    if format_fields is None:
        if kind.casefold() in {"dialogue", "comment"}:
            issues.append(
                AssIssue(
                    code="event_without_format",
                    message=f"{kind} appears before a valid Format declaration",
                    line_number=line.number,
                    analysis_incomplete=True,
                    rewrite_unsafe=True,
                )
            )
        return None

    indexes = _field_indexes(format_fields)
    if "style" not in indexes or "text" not in indexes:
        if kind.casefold() in {"dialogue", "comment"}:
            issues.append(
                AssIssue(
                    code="event_format_missing_fields",
                    message="Event Format must contain Style and Text fields",
                    line_number=line.number,
                    analysis_incomplete=True,
                    rewrite_unsafe=True,
                )
            )
        return None

    fields = _split_event_fields(payload, len(format_fields), indexes["text"])
    if fields is None:
        if kind.casefold() in {"dialogue", "comment"}:
            issues.append(
                AssIssue(
                    code="malformed_event",
                    message=f"{kind} field count does not match its Format declaration",
                    line_number=line.number,
                    analysis_incomplete=True,
                    rewrite_unsafe=True,
                )
            )
        return None

    return AssEvent(
        kind=kind,
        line_index=line_index,
        prefix=prefix,
        format_fields=format_fields,
        fields=fields,
        style_index=indexes["style"],
        text_index=indexes["text"],
        style_name=fields[indexes["style"]].strip(),
        text=fields[indexes["text"]],
    )


def _split_event_fields(payload: str, field_count: int, text_index: int) -> tuple[str, ...] | None:
    before_count = text_index
    after_count = field_count - text_index - 1

    left = payload.split(",", before_count)
    if len(left) != before_count + 1:
        return None
    before = left[:-1]
    remainder = left[-1]

    if after_count:
        right = remainder.rsplit(",", after_count)
        if len(right) != after_count + 1:
            return None
        text = right[0]
        after = right[1:]
    else:
        text = remainder
        after = []
    return tuple([*before, text, *after])


def _split_directive(content: str) -> tuple[str, str, str] | None:
    colon = content.find(":")
    if colon < 0:
        return None
    kind = content[:colon].strip()
    if not kind:
        return None
    payload_start = colon + 1
    while payload_start < len(content) and content[payload_start] in {" ", "\t"}:
        payload_start += 1
    return kind, content[:payload_start], content[payload_start:]


def _field_indexes(format_fields: tuple[str, ...]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, field in enumerate(format_fields):
        indexes.setdefault(field.strip().casefold(), index)
    return indexes


def _parse_ass_bool(value: str) -> bool:
    stripped = value.strip().casefold()
    try:
        return int(stripped) != 0
    except ValueError:
        return stripped in {"true", "yes", "on"}


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _numeric_tag_boundary(remainder: str) -> bool:
    return len(remainder) == 1 or remainder[1] in "+-0123456789\\"


def _signed_integer_end(value: str, start: int) -> int:
    position = start
    if position < len(value) and value[position] in "+-":
        position += 1
    while position < len(value) and value[position].isdigit():
        position += 1
    return position


def _next_tag_start(value: str, start: int) -> int:
    next_slash = value.find("\\", start)
    return len(value) if next_slash < 0 else next_slash


def _parenthesis_depth_at(value: str, target: int) -> int:
    depth = 0
    for character in value[:target]:
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
    return depth


def _next_tag_parameter_end(value: str, start: int, parenthesis_depth: int) -> int:
    """Stop a tag parameter at the next tag or its containing closing parenthesis."""

    depth = parenthesis_depth
    position = start
    while position < len(value):
        character = value[position]
        if character == "\\":
            return position
        if character == "(":
            depth += 1
        elif character == ")":
            if parenthesis_depth > 0 and depth == parenthesis_depth:
                return position
            if depth:
                depth -= 1
        position += 1
    return len(value)


def _dominant_newline(lines: list[AssLine]) -> str:
    counts = Counter(line.ending for line in lines if line.ending)
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def _split_line_ending(value: str) -> tuple[str, str]:
    if value.endswith("\r\n"):
        return value[:-2], "\r\n"
    if value.endswith("\n") or value.endswith("\r"):
        return value[:-1], value[-1]
    return value, ""


def _codec_for_encoding(encoding: str) -> str:
    return "utf-8" if encoding == "utf-8-sig" else encoding


def _detect_encoding(raw: bytes) -> tuple[str, bytes, bytes, AssIssue | None]:
    if raw.startswith(_UTF8_BOM):
        payload = raw[len(_UTF8_BOM) :]
        _strict_decode(payload, "utf-8", "UTF-8 BOM")
        return "utf-8-sig", _UTF8_BOM, payload, None
    if raw.startswith(_UTF16_LE_BOM):
        payload = raw[len(_UTF16_LE_BOM) :]
        _strict_decode(payload, "utf-16-le", "UTF-16 LE")
        return "utf-16-le", _UTF16_LE_BOM, payload, None
    if raw.startswith(_UTF16_BE_BOM):
        payload = raw[len(_UTF16_BE_BOM) :]
        _strict_decode(payload, "utf-16-be", "UTF-16 BE")
        return "utf-16-be", _UTF16_BE_BOM, payload, None

    utf16_candidates = _utf16_candidates(raw)
    try:
        utf8_text = raw.decode("utf-8", errors="strict")
        # BOM-less UTF-16 ASS is often also byte-valid UTF-8 because most of its
        # syntax is ASCII followed by NUL bytes. NULs are not valid ASS text, so
        # let the UTF-16 heuristic take precedence for that ambiguous case.
        if "\x00" not in utf8_text or not utf16_candidates:
            return "utf-8", b"", raw, None
    except UnicodeDecodeError:
        pass

    for encoding in utf16_candidates:
        try:
            raw.decode(encoding, errors="strict")
            return encoding, b"", raw, None
        except UnicodeDecodeError:
            continue

    legacy_decodings: dict[str, str] = {}
    for encoding in ("gb18030", "shift_jis"):
        try:
            legacy_decodings[encoding] = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
    if "gb18030" in legacy_decodings:
        issue = None
        if (
            "shift_jis" in legacy_decodings
            and legacy_decodings["shift_jis"] != legacy_decodings["gb18030"]
        ):
            issue = AssIssue(
                code="ambiguous_legacy_encoding",
                message=(
                    "Subtitle bytes are valid as both GB18030 and Shift-JIS; "
                    "font subsetting requires an unambiguous encoding"
                ),
                analysis_incomplete=True,
                rewrite_unsafe=True,
            )
        return "gb18030", b"", raw, issue
    if "shift_jis" in legacy_decodings:
        return "shift_jis", b"", raw, None

    raise AssDecodeError("ASS/SSA file is not valid UTF-8, UTF-16, GB18030, or Shift-JIS")


def _use_encoding_hint(raw: bytes, encoding_hint: str) -> tuple[str, bytes, bytes]:
    encoding = encoding_hint.casefold().replace("_", "-")
    aliases = {
        "utf8": "utf-8",
        "utf8-sig": "utf-8-sig",
        "utf16-le": "utf-16-le",
        "utf16-be": "utf-16-be",
        "shift-jis": "shift_jis",
    }
    encoding = aliases.get(encoding, encoding)
    supported = {"utf-8", "utf-8-sig", "utf-16-le", "utf-16-be", "gb18030", "shift_jis"}
    if encoding not in supported:
        raise AssDecodeError(f"Unsupported ASS/SSA encoding hint: {encoding_hint}")

    expected_bom = {
        "utf-8-sig": _UTF8_BOM,
        "utf-16-le": _UTF16_LE_BOM,
        "utf-16-be": _UTF16_BE_BOM,
    }.get(encoding, b"")
    bom = expected_bom if expected_bom and raw.startswith(expected_bom) else b""
    payload = raw[len(bom) :]
    _strict_decode(payload, _codec_for_encoding(encoding), encoding_hint)
    return encoding, bom, payload


def _strict_decode(payload: bytes, encoding: str, label: str) -> None:
    try:
        payload.decode(encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise AssDecodeError(f"ASS/SSA file has an invalid {label} byte sequence") from exc


def _utf16_candidates(raw: bytes) -> tuple[str, ...]:
    if len(raw) < 4 or len(raw) % 2:
        return ()
    even_nuls = sum(byte == 0 for byte in raw[0::2])
    odd_nuls = sum(byte == 0 for byte in raw[1::2])
    threshold = max(2, len(raw) // 20)
    if max(even_nuls, odd_nuls) < threshold:
        return ()
    if odd_nuls >= even_nuls:
        return ("utf-16-le", "utf-16-be")
    return ("utf-16-be", "utf-16-le")


def _split_raw_lines(payload: bytes, encoding: str) -> list[bytes]:
    if not payload:
        return []
    if encoding in {"utf-16-le", "utf-16-be"}:
        return _split_utf16_raw_lines(payload, little_endian=encoding == "utf-16-le")

    lines: list[bytes] = []
    start = 0
    position = 0
    while position < len(payload):
        byte = payload[position]
        if byte == 0x0D:
            end = position + 1
            if end < len(payload) and payload[end] == 0x0A:
                end += 1
            lines.append(payload[start:end])
            start = end
            position = end
            continue
        if byte == 0x0A:
            end = position + 1
            lines.append(payload[start:end])
            start = end
            position = end
            continue
        position += 1
    if start < len(payload):
        lines.append(payload[start:])
    return lines


def _split_utf16_raw_lines(payload: bytes, *, little_endian: bool) -> list[bytes]:
    lines: list[bytes] = []
    start = 0
    position = 0

    def code_unit(offset: int) -> int:
        return int.from_bytes(payload[offset : offset + 2], "little" if little_endian else "big")

    while position + 1 < len(payload):
        unit = code_unit(position)
        if unit == 0x000D:
            end = position + 2
            if end + 1 < len(payload) and code_unit(end) == 0x000A:
                end += 2
            lines.append(payload[start:end])
            start = end
            position = end
            continue
        if unit == 0x000A:
            end = position + 2
            lines.append(payload[start:end])
            start = end
            position = end
            continue
        position += 2
    if start < len(payload):
        lines.append(payload[start:])
    return lines
