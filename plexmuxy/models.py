from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal

CleanupMode = Literal["none", "move", "delete"]
NameStrategy = Literal["suffix", "same-name", "template"]
FailedOutputAction = Literal["keep", "delete", "rename"]
AmbiguousAction = Literal["skip"]
FontMode = Literal["all", "referenced", "subset"]
FontMimeMode = Literal["legacy", "modern"]
MissingFontAction = Literal["warn", "skip-video", "fail-job", "fallback-all"]
SubsetFailureAction = Literal["fallback-full", "skip-video", "fail-job"]
FontOutlineType = Literal["truetype", "cff", "cff2", "unknown"]
TrackDecisionSource = Literal["default", "rule", "manual"]
PLAN_SCHEMA_VERSION = 3

# Mapping of font file suffixes to the MIME type mkvmerge stores for the
# attachment. Legacy types are what MKVToolNix used before v66; the modern
# `font/...` scheme is written by default since MKVToolNix v66 unless
# --enable-legacy-font-mime-types is passed.
_LEGACY_FONT_MIME_TYPES: dict[str, str] = {
    ".ttf": "application/x-truetype-font",
    ".otf": "application/vnd.ms-opentype",
    ".ttc": "application/vnd.ms-opentype",
    ".otc": "application/vnd.ms-opentype",
}
_MODERN_FONT_MIME_TYPES: dict[str, str] = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".ttc": "font/collection",
    ".otc": "font/collection",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".sfnt": "font/sfnt",
}


def font_mime_type_for_suffix(suffix: str, *, mode: FontMimeMode = "legacy") -> str:
    """Return the MIME type to declare for a font attachment of the given path suffix."""
    suffix = Path(suffix).suffix if not suffix.startswith(".") else suffix
    suffix = suffix.casefold()
    if mode == "modern":
        return _MODERN_FONT_MIME_TYPES.get(suffix, "font/sfnt")
    return _LEGACY_FONT_MIME_TYPES.get(suffix, "application/octet-stream")


def font_mime_type_for_outline(outline_type: str, *, mode: FontMimeMode = "legacy") -> str:
    """Return the MIME type for a (subset) font of the given outline type."""
    if mode == "modern":
        return "font/otf" if outline_type in ("cff", "cff2") else "font/ttf"
    return "application/vnd.ms-opentype" if outline_type in ("cff", "cff2") else "application/x-truetype-font"

PLAN_DIGEST_SCHEMA_VERSION = 2


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class LanguageProfile:
    id: str
    mkv_language: str
    ietf_language: str
    keywords: list[str]


@dataclass
class MediaConfig:
    video_extensions: list[str] = field(default_factory=lambda: [".mkv", ".mp4", ".avi", ".flv"])
    audio_extensions: list[str] = field(default_factory=lambda: [".mka"])
    subtitle_extensions: list[str] = field(default_factory=lambda: [".ass", ".ssa"])
    font_extensions: list[str] = field(default_factory=lambda: [".ttf", ".otf", ".ttc", ".otc"])
    font_archive_extensions: list[str] = field(default_factory=lambda: [".zip", ".7z", ".rar"])
    recursive: bool = False
    include_hidden: bool = False
    follow_symlinks: bool = False


@dataclass
class TaskConfig:
    output_suffix: str = "_Plex"
    output_dir: Path | None = None
    overwrite: bool = False
    cleanup: CleanupMode = "move"
    cleanup_overridden: bool = False
    extra_dir: str = "Extra"
    name_strategy: NameStrategy = "suffix"
    name_template: str | None = None
    failed_output_action: FailedOutputAction = "rename"
    delete_original_video: bool = False
    delete_original_audio: bool = False
    delete_subtitle: bool = False


@dataclass
class MatchingConfig:
    movie_fallback: bool = False
    allow_episode_only_match: bool = True
    minimum_confidence: float = 0.7
    ambiguous_action: AmbiguousAction = "skip"


@dataclass
class SubtitleConfig:
    default_language: str = "chs"
    show_author_in_track_name: bool = True
    profiles: list[LanguageProfile] = field(default_factory=list)


@dataclass
class ArchiveLimits:
    max_archive_size: int = 256 * 1024 * 1024
    max_files: int = 2000
    max_total_size: int = 1024 * 1024 * 1024
    max_file_size: int = 256 * 1024 * 1024
    max_depth: int = 8
    allow_uninspected_archives: bool = False


@dataclass
class FontConfig:
    delete_fonts_after_mux: bool = False
    unrar_path: str = ""
    mode: FontMode = "all"
    mime_mode: FontMimeMode = "legacy"
    missing_font_action: MissingFontAction = "warn"
    subset_failure_action: SubsetFailureAction = "fallback-full"
    archive_limits: ArchiveLimits = field(default_factory=ArchiveLimits)


@dataclass
class FontCacheConfig:
    enabled: bool = True
    max_size_mb: int = 2048
    max_age_days: int = 90


@dataclass
class MkvMergeConfig:
    path: str = ""


@dataclass
class FfmpegConfig:
    path: str = ""


@dataclass
class NotificationConfig:
    enabled: bool = False


@dataclass
class UpdateConfig:
    enabled: bool = False
    interval_hours: int = 24
    timeout_seconds: float = 3.0


@dataclass(frozen=True)
class PlexPathMapping:
    local_root: Path
    server_root: str


@dataclass
class PlexConfig:
    enabled: bool = False
    server_url: str = ""
    section_id: str = ""
    token_env: str = "PLEXMUXY_PLEX_TOKEN"
    path_mappings: list[PlexPathMapping] = field(default_factory=list)


@dataclass
class ConcurrencyConfig:
    max_parallel_mux_jobs: int = 1

    @property
    def thread_count(self) -> int:
        """Read-only compatibility alias for pre-0.2 callers."""
        return self.max_parallel_mux_jobs


@dataclass
class TrackFilterConfig:
    audio_filter_enabled: bool = False
    exclude_audio_title_patterns: list[str] = field(default_factory=list)
    keep_audio_languages: list[str] = field(default_factory=list)
    keep_default_audio: bool = True
    keep_all_when_unknown: bool = True
    allow_no_audio: bool = False


@dataclass
class AppConfig:
    config_version: int = 4
    media: MediaConfig = field(default_factory=MediaConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    font: FontConfig = field(default_factory=FontConfig)
    font_cache: FontCacheConfig = field(default_factory=FontCacheConfig)
    mkvmerge: MkvMergeConfig = field(default_factory=MkvMergeConfig)
    ffmpeg: FfmpegConfig = field(default_factory=FfmpegConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    updates: UpdateConfig = field(default_factory=UpdateConfig)
    plex: PlexConfig = field(default_factory=PlexConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    tracks: TrackFilterConfig = field(default_factory=TrackFilterConfig)
    source_path: Path | None = None


@dataclass(frozen=True)
class EpisodeIdentity:
    season: int | None = None
    episode: int | None = None
    category: str | None = None


@dataclass(frozen=True)
class SubtitleInfo:
    language: str
    track_name_language: str
    mkv_language: str
    ietf_language: str
    sub_author: str
    default_language: bool


@dataclass(frozen=True)
class SubtitleTrackPlan:
    path: Path
    track_name: str
    mkv_language: str
    ietf_language: str
    default_track: bool
    forced_track: bool
    match_reason: str


@dataclass(frozen=True)
class AudioTrackPlan:
    path: Path
    language: str | None
    match_reason: str
    expected_track_count: int = 1


@dataclass(frozen=True)
class TrackOverride:
    track_id: int
    included: bool


@dataclass(frozen=True)
class SubtitleOverride:
    path: Path
    track_name: str | None = None
    mkv_language: str | None = None
    ietf_language: str | None = None
    default_track: bool | None = None
    forced_track: bool | None = None


@dataclass(frozen=True)
class PlanEdit:
    source_video: Path
    revision: int = 1
    enabled: bool = True
    included_subtitles: tuple[Path, ...] | None = None
    included_external_audio: tuple[Path, ...] | None = None
    source_track_overrides: tuple[TrackOverride, ...] = ()
    subtitle_metadata_overrides: tuple[SubtitleOverride, ...] = ()
    external_track_order: tuple[str, ...] = ()
    # External files the user picked manually (not discovered by the scan). They
    # are registered into the scan's known inputs so the rest of the pipeline
    # treats them like discovered tracks; the per-track builders synthesize plan
    # entries for paths that are not already in a plan's track list.
    extra_subtitles: tuple[Path, ...] = ()
    extra_audio: tuple[Path, ...] = ()


@dataclass(frozen=True)
class AttachmentPlan:
    path: Path
    expected_name: str | None = None
    expected_mime_type: str | None = None

    @property
    def name(self) -> str:
        return self.expected_name or self.path.name


@dataclass(frozen=True)
class FontFaceRef:
    """Stable reference to one face in a direct font file or archive member.

    ``source_digest`` identifies the font payload itself. Archive-backed faces
    additionally carry the archive digest so execution can reject a replaced
    archive before materializing ``archive_member``.
    """

    source_path: Path | None
    face_index: int
    source_digest: str
    family_names: tuple[str, ...]
    typographic_family_names: tuple[str, ...]
    subfamily_names: tuple[str, ...]
    full_names: tuple[str, ...]
    postscript_names: tuple[str, ...]
    weight: int
    width: int
    italic: bool
    unicode_codepoints: tuple[int, ...]
    archive_path: Path | None = None
    archive_member: str | None = None
    archive_digest: str | None = None
    outline_type: FontOutlineType = "unknown"
    is_variable: bool = False
    has_color: bool = False
    has_bitmap: bool = False
    has_vertical_metrics: bool = False
    table_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        direct = self.source_path is not None
        archived = any(value is not None for value in (
            self.archive_path, self.archive_member, self.archive_digest,
        ))
        if direct == archived:
            raise ValueError("FontFaceRef must use exactly one direct or archive source")
        if archived and (self.archive_path is None or not self.archive_member):
            raise ValueError("Archive-backed FontFaceRef requires archive_path and archive_member")
        if archived and not self.archive_digest:
            raise ValueError("Archive-backed FontFaceRef requires archive_digest")
        if not _is_sha256(self.source_digest):
            raise ValueError("FontFaceRef source_digest must be a SHA-256 hex digest")
        if self.archive_digest is not None and not _is_sha256(self.archive_digest):
            raise ValueError("FontFaceRef archive_digest must be a SHA-256 hex digest")
        if self.archive_member is not None:
            member = PurePosixPath(self.archive_member.replace("\\", "/"))
            if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
                raise ValueError("FontFaceRef archive_member must be a safe relative path")
        if self.face_index < 0:
            raise ValueError("Font face_index cannot be negative")
        if any(
            isinstance(codepoint, bool)
            or not isinstance(codepoint, int)
            or not 0 <= codepoint <= 0x10FFFF
            for codepoint in self.unicode_codepoints
        ):
            raise ValueError("FontFaceRef unicode_codepoints must be sorted unique Unicode values")
        normalized_codepoints = tuple(sorted(set(self.unicode_codepoints)))
        if normalized_codepoints != self.unicode_codepoints:
            raise ValueError("FontFaceRef unicode_codepoints must be sorted unique Unicode values")

    @property
    def is_archive_backed(self) -> bool:
        return self.archive_path is not None

    @property
    def stable_source_path(self) -> Path:
        source = self.archive_path if self.is_archive_backed else self.source_path
        if source is None:  # Guard for type checkers; __post_init__ rejects it.
            raise ValueError("Font face has no stable source path")
        return source


@dataclass(frozen=True)
class FontUsage:
    requested_family: str
    normalized_family: str
    weight: int
    italic: bool
    codepoints: tuple[int, ...]
    subtitle_paths: tuple[Path, ...]


@dataclass(frozen=True)
class FontSubsetIssue:
    code: str
    message: str
    requested_family: str | None = None
    subtitle_path: Path | None = None
    codepoints: tuple[int, ...] = ()
    fatal: bool = True


@dataclass(frozen=True)
class FontSubsetSummary:
    subtitle_count: int = 0
    requested_family_count: int = 0
    matched_face_count: int = 0
    expected_attachment_count: int = 0
    fallback_family_count: int = 0


@dataclass(frozen=True)
class FontSubsetGroupIntent:
    requested_names: tuple[str, ...]
    alias_family: str
    faces: tuple[FontFaceRef, ...]
    codepoint_ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class FontSubsetIntent:
    analyzer_version: int
    subset_profile_version: int
    groups: tuple[FontSubsetGroupIntent, ...]
    subtitle_digests: tuple[tuple[Path, str], ...]
    issues: tuple[FontSubsetIssue, ...] = ()
    summary: FontSubsetSummary = field(default_factory=FontSubsetSummary)


@dataclass(frozen=True)
class SourceTrackInfo:
    id: int
    type: str
    codec: str | None = None
    language: str | None = None
    title: str | None = None
    default_track: bool = False
    forced_track: bool = False
    channels: int | None = None
    included: bool = True
    decision_reason: str = "preserve_by_default"
    decision_source: TrackDecisionSource = "default"
    matched_rule: str | None = None


@dataclass(frozen=True)
class SkippedFile:
    path: Path
    reason: str
    stage: str = "matching"


@dataclass(frozen=True)
class MatchResult:
    file: Path
    confidence: float
    reason: str


@dataclass
class ScanResult:
    input_dir: Path
    videos: list[Path] = field(default_factory=list)
    audios: list[Path] = field(default_factory=list)
    subtitles: list[Path] = field(default_factory=list)
    font_archives: list[Path] = field(default_factory=list)
    fonts_dir: Path | None = None
    others: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FontResult:
    fonts: list[Path] = field(default_factory=list)
    extracted_files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    fonts_dir: Path | None = None


@dataclass
class MuxPlan:
    source_video: Path
    output_path: Path
    subtitle_tracks: list[SubtitleTrackPlan] = field(default_factory=list)
    audio_tracks: list[AudioTrackPlan] = field(default_factory=list)
    attachments: list[AttachmentPlan] = field(default_factory=list)
    source_tracks: list[SourceTrackInfo] = field(default_factory=list)
    cleanup_candidates: list[Path] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    font_subset_intent: FontSubsetIntent | None = None
    edit_revision: int = 0
    external_track_order: list[str] = field(default_factory=list)


@dataclass
class PreparedMuxPlan:
    original_plan: MuxPlan
    subtitle_tracks: list[SubtitleTrackPlan]
    attachments: list[AttachmentPlan]
    generated_files: list[Path] = field(default_factory=list)
    subset_warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_original(cls, plan: MuxPlan) -> PreparedMuxPlan:
        return cls(
            original_plan=plan,
            subtitle_tracks=list(plan.subtitle_tracks),
            attachments=list(plan.attachments),
        )


@dataclass
class PlanBuildResult:
    plans: list[MuxPlan] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    size: int
    modified_time_ns: int
    sha256: str | None = None


@dataclass
class MuxPlanSnapshot:
    plan_id: str
    config_hash: str
    created_at: str
    input_dir: Path
    config: dict[str, Any]
    plans: list[MuxPlan]
    files: list[FileSnapshot]
    outputs_existing: list[Path] = field(default_factory=list)
    schema_version: int = PLAN_SCHEMA_VERSION

    @classmethod
    def timestamp(cls) -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class VerificationResult:
    success: bool
    error_code: str | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MuxResult:
    plan: MuxPlan
    success: bool
    output_path: Path
    error_code: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    verified: bool = False
    verification: VerificationResult | None = None


@dataclass(frozen=True)
class CleanupResult:
    path: Path
    action: CleanupMode
    success: bool
    destination: Path | None = None
    error: str | None = None


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    total: int = 0
    completed: int = 0
    succeeded: int = 0
    failed: int = 0
    current_file: str | None = None
    total_families: int = 0
    completed_families: int = 0
    current_family: str | None = None


@dataclass
class JobReport:
    input_dir: Path
    plans: list[MuxPlan] = field(default_factory=list)
    results: list[MuxResult] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)
    cleanup_results: list[CleanupResult] = field(default_factory=list)
    snapshot: MuxPlanSnapshot | None = None
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False
    error_code: str | None = None
    error: str | None = None
    available_subtitles: list[Path] = field(default_factory=list)
    available_audio: list[Path] = field(default_factory=list)
    post_actions: list[dict[str, object]] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)
