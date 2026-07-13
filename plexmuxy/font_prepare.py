from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .ass_rewrite import AssRewriteError, rewrite_ass_file
from .font import extract_rar, safe_destination, seven_zip_members, validate_archive_file, validate_members
from .font_catalog import normalize_font_name
from .font_matching import match_font_usages
from .font_subset import (
    SUBSET_PROFILE_VERSION,
    UNSAFE_GLYPH_TABLES,
    FontSubsetError,
    output_extension,
    style_name,
    subset_font_face,
)
from .models import (
    AttachmentPlan,
    FontConfig,
    FontFaceRef,
    FontSubsetGroupIntent,
    FontSubsetIntent,
    FontSubsetIssue,
    FontSubsetSummary,
    FontUsage,
    MuxPlan,
    PreparedMuxPlan,
    SubtitleTrackPlan,
)

ANALYZER_VERSION = 1


class FontPreparationError(RuntimeError):
    pass


PreparationProgress = Callable[[str, int, int, str | None], None]


@dataclass
class _IntentGroup:
    canonical_name: str
    requested_names: set[str]
    faces: dict[tuple[str, int], FontFaceRef]
    codepoints: set[int]


class SubsetWorkspace:
    """Execution-scoped storage that is removed on every exit path."""

    def __init__(self, plan_id: str, root: Path | None = None) -> None:
        self.plan_id = plan_id
        self.root = Path(root) if root else None
        self.path: Path | None = None
        self.fonts: Path | None = None
        self.subtitles: Path | None = None
        self.sources: Path | None = None
        self.manifests: Path | None = None
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.subset_cache: dict[str, AttachmentPlan] = {}

    def __enter__(self) -> SubsetWorkspace:
        safe_plan_id = "".join(character for character in self.plan_id if character.isalnum())[:12] or "plan"
        prefix = f"plexmuxy-{safe_plan_id}-"
        self._temporary = tempfile.TemporaryDirectory(prefix=prefix, dir=self.root, ignore_cleanup_errors=True)
        self.path = Path(self._temporary.name)
        self.fonts = self.path / "fonts"
        self.subtitles = self.path / "subtitles"
        self.sources = self.path / "sources"
        self.manifests = self.path / "manifests"
        for directory in (self.fonts, self.subtitles, self.sources, self.manifests):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()

    def require_path(self, attribute: str) -> Path:
        value = getattr(self, attribute, None)
        if not isinstance(value, Path):
            raise RuntimeError("SubsetWorkspace has not been entered")
        return value


def build_subset_intent(
    subtitle_paths: list[Path],
    usages: list[FontUsage],
    catalog: list[FontFaceRef],
) -> FontSubsetIntent:
    matches = match_font_usages(usages, catalog)
    groups: dict[str, _IntentGroup] = {}
    issues: list[FontSubsetIssue] = []
    for result in matches:
        usage = result.usage
        if result.status == "missing":
            issues.append(FontSubsetIssue(
                "font_family_missing",
                f"Referenced font family was not found: {usage.requested_family}",
                requested_family=usage.requested_family,
            ))
            continue
        if result.status == "ambiguous":
            issues.append(FontSubsetIssue(
                "font_match_ambiguous",
                f"Multiple different font faces match equally: {usage.requested_family}",
                requested_family=usage.requested_family,
            ))
            continue
        if result.status == "missing-glyphs":
            issues.append(FontSubsetIssue(
                "font_codepoints_missing",
                f"Matched font is missing required characters: {usage.requested_family}",
                requested_family=usage.requested_family,
                codepoints=result.missing_codepoints,
            ))
            continue
        face = result.face
        if face is None:
            continue
        canonical = _canonical_family(face, usage)
        key = normalize_font_name(canonical)
        group = groups.setdefault(key, _IntentGroup(canonical, set(), {}, set()))
        group.requested_names.add(usage.requested_family.lstrip("@"))
        group.faces[(face.source_digest, face.face_index)] = face
        group.codepoints.update(usage.codepoints)

    intents: list[FontSubsetGroupIntent] = []
    for key in sorted(groups):
        group = groups[key]
        faces = tuple(sorted(group.faces.values(), key=lambda face: (face.source_digest, face.face_index)))
        alias = deterministic_alias(key, faces)
        intents.append(FontSubsetGroupIntent(
            requested_names=tuple(sorted(group.requested_names, key=str.casefold)),
            alias_family=alias,
            faces=faces,
            codepoint_ranges=compress_codepoints(group.codepoints),
        ))

    paths = sorted({Path(path).resolve() for path in subtitle_paths}, key=lambda path: str(path).casefold())
    digests = tuple((path, _sha256_path(path)) for path in paths)
    summary = FontSubsetSummary(
        subtitle_count=len(paths),
        requested_family_count=len({usage.normalized_family for usage in usages}),
        matched_face_count=len({(face.source_digest, face.face_index) for group in intents for face in group.faces}),
        expected_attachment_count=sum(len(group.faces) for group in intents),
        fallback_family_count=sum(
            1
            for group in intents
            if any(_face_requires_full_font(face) for face in group.faces)
        ),
    )
    return FontSubsetIntent(
        analyzer_version=ANALYZER_VERSION,
        subset_profile_version=SUBSET_PROFILE_VERSION,
        groups=tuple(intents),
        subtitle_digests=digests,
        issues=tuple(issues),
        summary=summary,
    )


def deterministic_alias(normalized_family: str, faces: tuple[FontFaceRef, ...]) -> str:
    digest = hashlib.sha256()
    digest.update(normalized_family.encode("utf-8"))
    for face in sorted(faces, key=lambda item: (item.source_digest, item.face_index)):
        digest.update(face.source_digest.encode("ascii"))
        digest.update(b":")
        digest.update(str(face.face_index).encode("ascii"))
        digest.update(b";")
    digest.update(str(SUBSET_PROFILE_VERSION).encode("ascii"))
    return f"PMX_{digest.hexdigest()[:12].upper()}"


def compress_codepoints(codepoints: set[int] | tuple[int, ...] | list[int]) -> tuple[tuple[int, int], ...]:
    values = sorted({int(value) for value in codepoints})
    if not values:
        return ()
    ranges: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append((start, previous))
        start = previous = value
    ranges.append((start, previous))
    return tuple(ranges)


def expand_codepoint_ranges(ranges: tuple[tuple[int, int], ...]) -> set[int]:
    result: set[int] = set()
    for start, end in ranges:
        if start < 0 or end < start or end > 0x10FFFF:
            raise FontPreparationError(f"Invalid codepoint range: {start}-{end}")
        result.update(range(start, end + 1))
    return result


def materialize_font_source(face: FontFaceRef, workspace: SubsetWorkspace, config: FontConfig) -> Path:
    """Resolve a stable face source and verify its payload digest at execution."""

    if face.source_path is not None:
        source = face.source_path.resolve()
        if not source.is_file() or _sha256_path(source) != face.source_digest:
            raise FontPreparationError(f"Direct font source changed: {source}")
        return source
    archive = face.archive_path
    member = face.archive_member
    if archive is None or not member:
        raise FontPreparationError("Archive-backed font face has no source identity")
    archive = archive.resolve()
    validate_archive_file(archive, config.archive_limits)
    if _sha256_path(archive) != face.archive_digest:
        raise FontPreparationError(f"Font archive changed: {archive}")
    sources = workspace.require_path("sources")
    suffix = Path(member).suffix.casefold() or ".font"
    destination = sources / f"{face.source_digest}{suffix}"
    if destination.is_file() and _sha256_path(destination) == face.source_digest:
        return destination
    payload = _read_archive_member(archive, member, face.source_digest, workspace, config)
    if hashlib.sha256(payload).hexdigest() != face.source_digest:
        raise FontPreparationError(f"Font archive member changed: {archive.name}/{member}")
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)
    return destination


def prepare_subset_plan(
    plan: MuxPlan,
    config: FontConfig,
    workspace: SubsetWorkspace,
    cancellation_event: threading.Event | None = None,
    progress_callback: PreparationProgress | None = None,
) -> PreparedMuxPlan:
    """Materialize one immutable subset intent into runtime-only mux inputs.

    Missing or ambiguous fonts are planning errors and are never converted to a
    full-font fallback here. Only failures after a concrete face was selected
    are eligible for ``subset_failure_action = fallback-full``.
    """

    intent = plan.font_subset_intent
    if intent is None:
        raise FontPreparationError("Subset plan has no font subset intent; create a new plan")
    if intent.analyzer_version != ANALYZER_VERSION:
        raise FontPreparationError("Subset analyzer version changed; create a new plan")
    if intent.subset_profile_version != SUBSET_PROFILE_VERSION:
        raise FontPreparationError("Font subset profile changed; create a new plan")
    _check_cancelled(cancellation_event)
    _validate_subtitle_digests(intent)

    # The explicit missing-font fallback-all policy is decided at planning time
    # and retains the original subtitles and complete attachments.
    if "font_subset_fallback_all" in plan.warnings:
        return PreparedMuxPlan.from_original(plan)
    if intent.issues:
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in intent.issues)
        raise FontPreparationError(f"Subset intent contains unresolved font issues: {details}")

    total_groups = len(intent.groups)
    aliases: dict[str, str] = {}
    attachments: list[AttachmentPlan] = []
    generated_files: list[Path] = []
    warnings: list[str] = []

    for completed, group in enumerate(intent.groups):
        _check_cancelled(cancellation_event)
        current = group.requested_names[0] if group.requested_names else group.alias_family
        _emit_preparation(progress_callback, "subsetting_fonts", total_groups, completed, current)
        group_attachments: list[AttachmentPlan] = []
        try:
            codepoints = expand_codepoint_ranges(group.codepoint_ranges)
            if not codepoints:
                raise FontPreparationError(f"Subset group has no characters: {current}")
            for face in group.faces:
                _check_cancelled(cancellation_event)
                source = materialize_font_source(face, workspace, config)
                attachment = _cached_subset_attachment(
                    face,
                    source,
                    codepoints,
                    group.alias_family,
                    workspace,
                )
                group_attachments.append(attachment)
        except (FontPreparationError, FontSubsetError, OSError, ValueError) as exc:
            if config.subset_failure_action != "fallback-full":
                raise FontPreparationError(f"Cannot subset {current}: {exc}") from exc
            group_attachments = _full_font_attachments(group.faces, workspace, config)
            warnings.append(f"subset_fallback_full_font:{current}:{exc}")
        else:
            for requested_name in group.requested_names:
                aliases[requested_name] = group.alias_family
            generated_files.extend(item.path for item in group_attachments)
        _extend_unique_attachments(attachments, group_attachments)
        _emit_preparation(progress_callback, "validating_subsets", total_groups, completed + 1, current)

    _check_cancelled(cancellation_event)
    subtitle_tracks = _rewrite_subtitle_tracks(plan, aliases, workspace, cancellation_event)
    generated_files.extend(
        track.path for original, track in zip(plan.subtitle_tracks, subtitle_tracks, strict=True)
        if track.path != original.path
    )
    alias_targets = set(aliases.values())
    attached_aliases = {
        item.name.split("-", 1)[0]
        for item in attachments
        if item.name.startswith("PMX_")
    }
    if not alias_targets.issubset(attached_aliases):
        missing = ", ".join(sorted(alias_targets - attached_aliases))
        raise FontPreparationError(f"Rewritten subtitle aliases have no matching font attachments: {missing}")
    return PreparedMuxPlan(
        original_plan=plan,
        subtitle_tracks=subtitle_tracks,
        attachments=attachments,
        generated_files=list(dict.fromkeys(generated_files)),
        subset_warnings=warnings,
    )


def _cached_subset_attachment(
    face: FontFaceRef,
    source: Path,
    codepoints: set[int],
    alias_family: str,
    workspace: SubsetWorkspace,
) -> AttachmentPlan:
    ranges = compress_codepoints(codepoints)
    cache_digest = hashlib.sha256()
    for part in (
        face.source_digest,
        str(face.face_index),
        alias_family,
        repr(ranges),
        str(SUBSET_PROFILE_VERSION),
    ):
        cache_digest.update(part.encode("utf-8"))
        cache_digest.update(b"\0")
    cache_key = cache_digest.hexdigest()
    cached = workspace.subset_cache.get(cache_key)
    if cached is not None and cached.path.is_file():
        return cached

    extension = output_extension(face)
    output = workspace.require_path("fonts") / f"{cache_key}{extension}"
    result = subset_font_face(face, source, codepoints, alias_family, output)
    style = style_name(face).replace(" ", "")
    expected_name = f"{alias_family}-{style}-{face.source_digest[:8]}{extension}"
    attachment = AttachmentPlan(
        result.path,
        expected_name=expected_name,
        expected_mime_type=result.mime_type,
    )
    workspace.subset_cache[cache_key] = attachment
    return attachment


def _full_font_attachments(
    faces: tuple[FontFaceRef, ...],
    workspace: SubsetWorkspace,
    config: FontConfig,
) -> list[AttachmentPlan]:
    result: list[AttachmentPlan] = []
    seen: set[str] = set()
    for face in faces:
        if face.source_digest in seen:
            continue
        seen.add(face.source_digest)
        path = materialize_font_source(face, workspace, config)
        original_name = (
            Path(face.archive_member).name
            if face.archive_member is not None
            else path.name
        )
        result.append(AttachmentPlan(
            path,
            expected_name=original_name,
            expected_mime_type=_full_font_mime(path),
        ))
    return result


def _rewrite_subtitle_tracks(
    plan: MuxPlan,
    aliases: dict[str, str],
    workspace: SubsetWorkspace,
    cancellation_event: threading.Event | None,
) -> list[SubtitleTrackPlan]:
    if not aliases:
        return list(plan.subtitle_tracks)
    result: list[SubtitleTrackPlan] = []
    for index, track in enumerate(plan.subtitle_tracks):
        _check_cancelled(cancellation_event)
        digest = _sha256_path(track.path)
        destination = workspace.require_path("subtitles") / (
            f"{digest[:16]}-{index}{track.path.suffix.casefold()}"
        )
        try:
            rewrite_ass_file(track.path, destination, aliases)
        except (AssRewriteError, OSError, UnicodeError, ValueError) as exc:
            # Unsafe ASS rewriting must terminate this video; falling back only
            # applies to a concrete font face that FontTools could not subset.
            raise FontPreparationError(f"Cannot safely rewrite subtitle {track.path.name}: {exc}") from exc
        result.append(SubtitleTrackPlan(
            path=destination,
            track_name=track.track_name,
            mkv_language=track.mkv_language,
            ietf_language=track.ietf_language,
            default_track=track.default_track,
            forced_track=track.forced_track,
            match_reason=track.match_reason,
        ))
    return result


def _validate_subtitle_digests(intent: FontSubsetIntent) -> None:
    for path, expected in intent.subtitle_digests:
        if not path.is_file() or _sha256_path(path) != expected:
            raise FontPreparationError(f"Subtitle changed after planning: {path}")


def _extend_unique_attachments(target: list[AttachmentPlan], additions: list[AttachmentPlan]) -> None:
    identities = {(item.path.resolve(), item.name.casefold()) for item in target}
    for item in additions:
        identity = (item.path.resolve(), item.name.casefold())
        if identity not in identities:
            target.append(item)
            identities.add(identity)


def _full_font_mime(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".ttf":
        return "application/x-truetype-font"
    if suffix in {".otf", ".ttc", ".otc"}:
        return "application/vnd.ms-opentype"
    return "application/octet-stream"


def _check_cancelled(event: threading.Event | None) -> None:
    if event is not None and event.is_set():
        raise FontPreparationError("Subset preparation was cancelled")


def _emit_preparation(
    callback: PreparationProgress | None,
    phase: str,
    total: int,
    completed: int,
    current: str | None,
) -> None:
    if callback is not None:
        callback(phase, total, completed, current)


def _read_archive_member(
    archive: Path,
    member: str,
    expected_digest: str,
    workspace: SubsetWorkspace,
    config: FontConfig,
) -> bytes:
    suffix = archive.suffix.casefold()
    if suffix == ".zip":
        with zipfile.ZipFile(archive, "r") as source:
            infos = [item for item in source.infolist() if not item.is_dir()]
            validate_members([(item.filename, item.file_size) for item in infos], config.archive_limits)
            matches = [item for item in infos if item.filename.replace("\\", "/").strip("/") == member]
            for info in matches:
                payload = source.read(info)
                if hashlib.sha256(payload).hexdigest() == expected_digest:
                    return payload
        raise FontPreparationError(f"Planned ZIP member no longer exists: {member}")
    staging = workspace.require_path("sources") / f"extract-{hashlib.sha256((str(archive) + member).encode()).hexdigest()[:12]}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if suffix == ".7z":
        import py7zr

        with py7zr.SevenZipFile(archive, mode="r") as source:
            members = seven_zip_members(source)
            validate_members(members, config.archive_limits)
            if member not in {name.replace("\\", "/").strip("/") for name, _size in members}:
                raise FontPreparationError(f"Planned 7z member no longer exists: {member}")
            safe_destination(staging, member)
            source.extract(path=staging, targets=[member])
    elif suffix == ".rar":
        if not config.archive_limits.allow_uninspected_archives:
            raise FontPreparationError("RAR materialization requires allow_uninspected_archives")
        extract_rar(archive, staging, config)
    else:
        raise FontPreparationError(f"Unsupported font archive: {archive.suffix}")
    path = safe_destination(staging, member)
    if not path.is_file():
        raise FontPreparationError(f"Planned archive member was not extracted: {member}")
    return path.read_bytes()


def _canonical_family(face: FontFaceRef, usage: FontUsage) -> str:
    for collection in (face.typographic_family_names, face.family_names):
        if collection:
            return collection[0]
    return usage.normalized_family or usage.requested_family


def _face_requires_full_font(face: FontFaceRef) -> bool:
    return (
        face.has_color
        or face.has_bitmap
        or face.outline_type == "unknown"
        or bool(set(face.table_tags) & UNSAFE_GLYPH_TABLES)
    )


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
