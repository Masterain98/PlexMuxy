from __future__ import annotations

import copy
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .models import AppConfig, CleanupMode, EmbedScheme, FontMimeMode, FontMode, NameStrategy


@dataclass
class JobOverrides:
    cleanup: str | None = None
    extra_dir: str | None = None
    output_suffix: str | None = None
    output_dir: str | None = None
    name_strategy: str | None = None
    name_template: str | None = None
    font_mode: FontMode | None = None
    mime_mode: FontMimeMode | None = None
    embed_scheme: str | None = None
    overwrite: bool = False
    audio_filter_enabled: bool | None = None
    exclude_audio_title_patterns: list[str] | None = None
    keep_audio_languages: list[str] | None = None
    keep_default_audio: bool | None = None
    keep_all_when_unknown: bool | None = None
    allow_no_audio: bool | None = None


def apply_job_overrides(config: AppConfig, overrides: JobOverrides) -> AppConfig:
    updated = copy.deepcopy(config)
    if overrides.cleanup is not None:
        updated.task.cleanup = cast(CleanupMode, overrides.cleanup)
        updated.task.cleanup_overridden = True
    if overrides.extra_dir:
        updated.task.extra_dir = overrides.extra_dir
    if overrides.output_suffix is not None:
        updated.task.output_suffix = overrides.output_suffix or "_Plex"
    if overrides.output_dir:
        updated.task.output_dir = Path(overrides.output_dir).expanduser()
    if overrides.name_strategy:
        updated.task.name_strategy = cast(NameStrategy, overrides.name_strategy)
    if overrides.name_template:
        updated.task.name_template = overrides.name_template
    if overrides.font_mode is not None:
        updated.font.mode = overrides.font_mode
    if overrides.mime_mode is not None:
        updated.font.mime_mode = overrides.mime_mode
    if overrides.embed_scheme is not None:
        updated.font.embed_scheme = cast(EmbedScheme, overrides.embed_scheme)
    if overrides.overwrite:
        updated.task.overwrite = True
    if overrides.audio_filter_enabled is not None:
        updated.tracks.audio_filter_enabled = overrides.audio_filter_enabled
    if overrides.exclude_audio_title_patterns is not None:
        updated.tracks.exclude_audio_title_patterns = overrides.exclude_audio_title_patterns
    if overrides.keep_audio_languages is not None:
        updated.tracks.keep_audio_languages = overrides.keep_audio_languages
    if overrides.keep_default_audio is not None:
        updated.tracks.keep_default_audio = overrides.keep_default_audio
    if overrides.keep_all_when_unknown is not None:
        updated.tracks.keep_all_when_unknown = overrides.keep_all_when_unknown
    if overrides.allow_no_audio is not None:
        updated.tracks.allow_no_audio = overrides.allow_no_audio
    # Reuse the same validation path as persisted configuration so malformed
    # CLI/GUI overrides never reach the planner.
    from .config import config_to_dict, parse_config

    validated = parse_config(config_to_dict(updated))
    validated.source_path = config.source_path
    return validated


def overrides_from_namespace(args: Namespace) -> JobOverrides:
    return JobOverrides(
        cleanup=getattr(args, "cleanup", None),
        extra_dir=getattr(args, "extra_dir", None),
        output_suffix=getattr(args, "output_suffix", None),
        output_dir=getattr(args, "output_dir", None),
        name_strategy=getattr(args, "name_strategy", None),
        name_template=getattr(args, "name_template", None),
        font_mode=cast(FontMode | None, getattr(args, "font_mode", None)),
        mime_mode=cast(FontMimeMode | None, getattr(args, "mime_mode", None)),
        embed_scheme=optional_str(getattr(args, "embed_scheme", None)),
        overwrite=bool(getattr(args, "overwrite", False)),
    )


def overrides_from_payload(payload: dict[str, Any]) -> JobOverrides:
    return JobOverrides(
        cleanup=optional_str(payload.get("cleanup")),
        extra_dir=optional_str(payload.get("extra_dir")),
        output_suffix=optional_str(payload.get("output_suffix"), keep_empty=True),
        output_dir=optional_str(payload.get("output_dir")),
        name_strategy=optional_str(payload.get("name_strategy")),
        name_template=optional_str(payload.get("name_template")),
        font_mode=cast(FontMode | None, optional_str(payload.get("font_mode"))),
        mime_mode=cast(FontMimeMode | None, optional_str(payload.get("mime_mode"))),
        embed_scheme=optional_str(payload.get("embed_scheme")),
        overwrite=bool(payload.get("overwrite", False)),
        audio_filter_enabled=payload.get("audio_filter_enabled") if "audio_filter_enabled" in payload else None,
        exclude_audio_title_patterns=payload.get("exclude_audio_title_patterns") if "exclude_audio_title_patterns" in payload else None,
        keep_audio_languages=payload.get("keep_audio_languages") if "keep_audio_languages" in payload else None,
        keep_default_audio=payload.get("keep_default_audio") if "keep_default_audio" in payload else None,
        keep_all_when_unknown=payload.get("keep_all_when_unknown") if "keep_all_when_unknown" in payload else None,
        allow_no_audio=payload.get("allow_no_audio") if "allow_no_audio" in payload else None,
    )


def optional_str(value: Any, keep_empty: bool = False) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text == "" and not keep_empty:
        return None
    return text
