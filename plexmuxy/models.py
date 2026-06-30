from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


CleanupMode = Literal["none", "move", "delete"]
NameStrategy = Literal["suffix", "same-name", "template"]


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
    delete_original_video: bool = False
    delete_original_audio: bool = False
    delete_subtitle: bool = False


@dataclass
class SubtitleConfig:
    default_language: str = "chs"
    show_author_in_track_name: bool = True
    profiles: list[LanguageProfile] = field(default_factory=list)


@dataclass
class FontConfig:
    delete_fonts_after_mux: bool = False
    unrar_path: str = ""


@dataclass
class MkvMergeConfig:
    path: str = ""


@dataclass
class ConcurrencyConfig:
    thread_count: int | Literal["auto"] = "auto"


@dataclass
class AppConfig:
    config_version: int = 2
    media: MediaConfig = field(default_factory=MediaConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    font: FontConfig = field(default_factory=FontConfig)
    mkvmerge: MkvMergeConfig = field(default_factory=MkvMergeConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    source_path: Path | None = None


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


@dataclass
class FontResult:
    fonts: list[Path] = field(default_factory=list)
    extracted_files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fonts_dir: Path | None = None


@dataclass
class MuxPlan:
    source_video: Path
    output_path: Path
    subtitle_tracks: list[SubtitleTrackPlan] = field(default_factory=list)
    audio_tracks: list[AudioTrackPlan] = field(default_factory=list)
    attachments: list[AttachmentPlan] = field(default_factory=list)
    cleanup_candidates: list[Path] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)


@dataclass
class PlanBuildResult:
    plans: list[MuxPlan] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)


@dataclass
class MuxResult:
    plan: MuxPlan
    success: bool
    output_path: Path
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    verified: bool = False


@dataclass(frozen=True)
class CleanupResult:
    path: Path
    action: CleanupMode
    success: bool
    destination: Path | None = None
    error: str | None = None


@dataclass
class JobReport:
    input_dir: Path
    plans: list[MuxPlan] = field(default_factory=list)
    results: list[MuxResult] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)
    cleanup_results: list[CleanupResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)
