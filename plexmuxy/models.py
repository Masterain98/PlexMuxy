from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

CleanupMode = Literal["none", "move", "delete"]
NameStrategy = Literal["suffix", "same-name", "template"]
FailedOutputAction = Literal["keep", "delete", "rename"]
AmbiguousAction = Literal["skip"]
FontMode = Literal["all", "referenced", "subset"]
MissingFontAction = Literal["warn", "skip-video", "fail-job", "fallback-all"]


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
    font_extensions: list[str] = field(default_factory=lambda: [".ttf", ".otf", ".ttc"])
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
    missing_font_action: MissingFontAction = "warn"
    archive_limits: ArchiveLimits = field(default_factory=ArchiveLimits)


@dataclass
class MkvMergeConfig:
    path: str = ""


@dataclass
class ConcurrencyConfig:
    max_parallel_mux_jobs: int = 1

    @property
    def thread_count(self) -> int:
        """Read-only compatibility alias for pre-0.2 callers."""
        return self.max_parallel_mux_jobs


@dataclass
class TrackFilterConfig:
    exclude_audio_title_patterns: list[str] = field(default_factory=list)
    keep_audio_languages: list[str] = field(default_factory=list)
    keep_all_when_unknown: bool = True


@dataclass
class AppConfig:
    config_version: int = 2
    media: MediaConfig = field(default_factory=MediaConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    font: FontConfig = field(default_factory=FontConfig)
    mkvmerge: MkvMergeConfig = field(default_factory=MkvMergeConfig)
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


@dataclass(frozen=True)
class AttachmentPlan:
    path: Path


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


@dataclass
class PlanBuildResult:
    plans: list[MuxPlan] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    size: int
    modified_time_ns: int


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

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)
