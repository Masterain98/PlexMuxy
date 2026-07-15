from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .font_catalog import FontCatalogResult
from .models import (
    AppConfig,
    AttachmentPlan,
    AudioTrackPlan,
    FontResult,
    MuxPlan,
    PlanEdit,
    ScanResult,
    SkippedFile,
    SubtitleOverride,
    SubtitleTrackPlan,
    TrackOverride,
)
from .planner import plan_font_subsets, select_plan_fonts, unique_paths
from .subtitle import build_track_name, detect_subtitle_info


class PlanEditError(ValueError):
    code = "INVALID_PLAN_EDIT"


def plan_edits_from_payload(payload: Any) -> dict[Path, PlanEdit]:
    if payload is None or payload == ():
        return {}
    if not isinstance(payload, list):
        raise PlanEditError("plan_edits must be a list")
    result: dict[Path, PlanEdit] = {}
    allowed = {
        "source_video",
        "revision",
        "enabled",
        "included_subtitles",
        "included_external_audio",
        "source_track_overrides",
        "subtitle_metadata_overrides",
        "external_track_order",
    }
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise PlanEditError(f"plan_edits[{index}] must be an object")
        unknown = sorted(set(item) - allowed)
        if unknown:
            raise PlanEditError(f"Unknown plan edit field(s): {', '.join(unknown)}")
        source = _payload_path(item.get("source_video"), f"plan_edits[{index}].source_video")
        if source in result:
            raise PlanEditError(f"Duplicate plan edit source_video: {source}")
        revision = item.get("revision", 1)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise PlanEditError(f"plan_edits[{index}].revision must be a positive integer")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise PlanEditError(f"plan_edits[{index}].enabled must be a boolean")
        result[source] = PlanEdit(
            source_video=source,
            revision=revision,
            enabled=enabled,
            included_subtitles=_payload_paths(item, "included_subtitles", index),
            included_external_audio=_payload_paths(item, "included_external_audio", index),
            source_track_overrides=_payload_track_overrides(item.get("source_track_overrides", []), index),
            subtitle_metadata_overrides=_payload_subtitle_overrides(
                item.get("subtitle_metadata_overrides", []), index
            ),
            external_track_order=_payload_strings(item.get("external_track_order", []), index),
        )
    return result


def _payload_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PlanEditError(f"{field} must be a non-empty absolute path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise PlanEditError(f"{field} must be absolute")
    return path.resolve()


def _payload_paths(item: dict[str, Any], key: str, index: int) -> tuple[Path, ...] | None:
    if key not in item:
        return None
    value = item[key]
    if not isinstance(value, list):
        raise PlanEditError(f"plan_edits[{index}].{key} must be a list")
    return tuple(_payload_path(path, f"plan_edits[{index}].{key}") for path in value)


def _payload_track_overrides(value: Any, index: int) -> tuple[TrackOverride, ...]:
    if not isinstance(value, list):
        raise PlanEditError(f"plan_edits[{index}].source_track_overrides must be a list")
    result: list[TrackOverride] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"track_id", "included"}:
            raise PlanEditError("Each source track override requires only track_id and included")
        track_id = raw["track_id"]
        included = raw["included"]
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id < 0:
            raise PlanEditError("Source track override track_id must be a non-negative integer")
        if not isinstance(included, bool):
            raise PlanEditError("Source track override included must be a boolean")
        result.append(TrackOverride(track_id, included))
    return tuple(result)


def _payload_subtitle_overrides(value: Any, index: int) -> tuple[SubtitleOverride, ...]:
    if not isinstance(value, list):
        raise PlanEditError(f"plan_edits[{index}].subtitle_metadata_overrides must be a list")
    allowed = {"path", "track_name", "mkv_language", "ietf_language", "default_track", "forced_track"}
    result: list[SubtitleOverride] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise PlanEditError("Each subtitle metadata override must be an object")
        unknown = set(raw) - allowed
        if unknown:
            raise PlanEditError(f"Unknown subtitle override field(s): {', '.join(sorted(unknown))}")
        for flag in ("default_track", "forced_track"):
            if flag in raw and not isinstance(raw[flag], bool):
                raise PlanEditError(f"Subtitle override {flag} must be a boolean")
        for field in ("track_name", "mkv_language", "ietf_language"):
            if field in raw and (not isinstance(raw[field], str) or not raw[field].strip()):
                raise PlanEditError(f"Subtitle override {field} must be a non-empty string")
        result.append(SubtitleOverride(
            path=_payload_path(raw.get("path"), "subtitle override path"),
            track_name=raw.get("track_name"),
            mkv_language=raw.get("mkv_language"),
            ietf_language=raw.get("ietf_language"),
            default_track=raw.get("default_track"),
            forced_track=raw.get("forced_track"),
        ))
    return tuple(result)


def _payload_strings(value: Any, index: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise PlanEditError(f"plan_edits[{index}].external_track_order must be a list of strings")
    return tuple(value)


def apply_plan_edits(
    plans: list[MuxPlan],
    edits: Mapping[Path, PlanEdit],
    scan: ScanResult,
    config: AppConfig,
    fonts: FontResult,
    font_catalog: FontCatalogResult,
) -> tuple[list[MuxPlan], list[SkippedFile]]:
    if not edits:
        return plans, []
    known_videos = _known(scan.videos)
    known_subtitles = _known(scan.subtitles)
    known_audio = _known(scan.audios)
    normalized_edits: dict[Path, PlanEdit] = {}
    for raw_path, requested_edit in edits.items():
        target = raw_path.expanduser().resolve()
        if target != requested_edit.source_video.expanduser().resolve():
            raise PlanEditError("Plan edit key and source_video do not match")
        if target not in known_videos:
            raise PlanEditError(f"Plan edit references an unknown source video: {target}")
        if requested_edit.revision < 1:
            raise PlanEditError("Plan edit revision must be a positive integer")
        normalized_edits[target] = requested_edit

    result: list[MuxPlan] = []
    skipped: list[SkippedFile] = []
    claimed_subtitles: dict[Path, Path] = {}
    claimed_audio: dict[Path, Path] = {}
    for plan in plans:
        source = plan.source_video.resolve()
        edit = normalized_edits.get(source)
        if edit is not None and not edit.enabled:
            skipped.append(SkippedFile(plan.source_video, "disabled_by_user", "plan_edit"))
            continue
        subtitle_paths = _selected_paths(
            edit.included_subtitles if edit else None,
            [track.path for track in plan.subtitle_tracks],
            known_subtitles,
            "subtitle",
        )
        audio_paths = _selected_paths(
            edit.included_external_audio if edit else None,
            [track.path for track in plan.audio_tracks],
            known_audio,
            "external audio",
        )
        _claim_unique(claimed_subtitles, subtitle_paths, source, "subtitle")
        _claim_unique(claimed_audio, audio_paths, source, "external audio")
        subtitle_overrides = {
            override.path.expanduser().resolve(): override
            for override in (edit.subtitle_metadata_overrides if edit else ())
        }
        if not set(subtitle_overrides).issubset(set(subtitle_paths)):
            raise PlanEditError("Subtitle metadata override references a subtitle excluded from the draft")
        subtitle_tracks = [
            _subtitle_track(path, plan.subtitle_tracks, subtitle_overrides.get(path), config)
            for path in subtitle_paths
        ]
        audio_tracks = [
            _audio_track(path, plan.audio_tracks)
            for path in audio_paths
        ]
        selected_fonts, intent, warnings = _rebuild_fonts(
            subtitle_paths,
            fonts,
            font_catalog,
            config,
        )
        order = _validate_external_order(
            edit.external_track_order if edit else (),
            subtitle_paths,
            audio_paths,
        )
        result.append(replace(
            plan,
            subtitle_tracks=subtitle_tracks,
            audio_tracks=audio_tracks,
            attachments=[AttachmentPlan(path) for path in selected_fonts],
            cleanup_candidates=unique_paths([plan.source_video, *subtitle_paths, *audio_paths]),
            warnings=warnings,
            font_subset_intent=intent,
            edit_revision=edit.revision if edit else 0,
            external_track_order=order,
        ))
    missing_targets = set(normalized_edits) - {plan.source_video.resolve() for plan in plans}
    if missing_targets:
        names = ", ".join(str(path) for path in sorted(missing_targets, key=str))
        raise PlanEditError(f"Plan edit target has no executable base plan: {names}")
    return result, skipped


def source_track_overrides_from_edits(edits: Mapping[Path, PlanEdit]) -> dict[Path, dict[int, bool]]:
    result: dict[Path, dict[int, bool]] = {}
    for path, edit in edits.items():
        values: dict[int, bool] = {}
        for override in edit.source_track_overrides:
            if override.track_id in values:
                raise PlanEditError(f"Duplicate source track override ID: {override.track_id}")
            values[override.track_id] = override.included
        if values:
            result[path.expanduser().resolve()] = values
    return result


def _known(paths: Sequence[Path]) -> dict[Path, Path]:
    return {path.expanduser().resolve(): path for path in paths}


def _selected_paths(
    requested: tuple[Path, ...] | None,
    automatic: list[Path],
    known: dict[Path, Path],
    kind: str,
) -> list[Path]:
    raw_paths = automatic if requested is None else list(requested)
    result: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_paths:
        path = raw_path.expanduser().resolve()
        if path not in known:
            raise PlanEditError(f"Plan edit references an unknown {kind} file: {path}")
        if path in seen:
            raise PlanEditError(f"Plan edit repeats a {kind} file: {path}")
        seen.add(path)
        result.append(path)
    return result


def _claim_unique(claims: dict[Path, Path], paths: list[Path], source: Path, kind: str) -> None:
    for path in paths:
        owner = claims.get(path)
        if owner is not None and owner != source:
            raise PlanEditError(f"A {kind} file cannot be assigned to multiple videos: {path}")
        claims[path] = source


def _subtitle_track(
    path: Path,
    automatic: list[SubtitleTrackPlan],
    override: SubtitleOverride | None,
    config: AppConfig,
) -> SubtitleTrackPlan:
    existing = next((track for track in automatic if track.path.resolve() == path), None)
    if existing is None:
        info = detect_subtitle_info(path, config.subtitle)
        if not info.language and override is None:
            raise PlanEditError(f"Reassigned subtitle has no recognized language: {path}")
        existing = SubtitleTrackPlan(
            path=path,
            track_name=build_track_name(info, config.subtitle) if info.language else path.stem,
            mkv_language=info.mkv_language or "und",
            ietf_language=info.ietf_language or "und",
            default_track=info.default_language,
            forced_track=False,
            match_reason="manual_assignment",
        )
    if override is None:
        return existing
    track_name = existing.track_name if override.track_name is None else override.track_name.strip()
    mkv_language = existing.mkv_language if override.mkv_language is None else override.mkv_language.strip()
    ietf_language = existing.ietf_language if override.ietf_language is None else override.ietf_language.strip()
    if not track_name or not mkv_language or not ietf_language:
        raise PlanEditError("Subtitle track name and languages cannot be empty")
    return replace(
        existing,
        track_name=track_name,
        mkv_language=mkv_language,
        ietf_language=ietf_language,
        default_track=existing.default_track if override.default_track is None else override.default_track,
        forced_track=existing.forced_track if override.forced_track is None else override.forced_track,
        match_reason="manual_metadata" if override != SubtitleOverride(path) else existing.match_reason,
    )


def _audio_track(path: Path, automatic: list[AudioTrackPlan]) -> AudioTrackPlan:
    return next(
        (track for track in automatic if track.path.resolve() == path),
        AudioTrackPlan(path, None, "manual_assignment"),
    )


def _rebuild_fonts(
    subtitles: list[Path],
    fonts: FontResult,
    catalog: FontCatalogResult,
    config: AppConfig,
):
    if config.font.mode == "subset":
        selected, intent, warnings, skip_reason = plan_font_subsets(
            subtitles,
            fonts.fonts,
            catalog.faces,
            config,
        )
    else:
        selected, warnings, skip = select_plan_fonts(subtitles, fonts.fonts, config)
        intent = None
        skip_reason = "missing_referenced_font" if skip else None
    if skip_reason:
        raise PlanEditError(f"Edited plan cannot be finalized: {skip_reason}")
    return selected, intent, warnings


def _validate_external_order(
    requested: tuple[str, ...],
    subtitles: list[Path],
    audio: list[Path],
) -> list[str]:
    expected = [
        *[f"subtitle:{path}" for path in subtitles],
        *[f"audio:{path}" for path in audio],
    ]
    if not requested:
        return expected
    if len(requested) != len(expected) or set(requested) != set(expected):
        raise PlanEditError("external_track_order must contain every selected external track exactly once")
    return list(requested)
