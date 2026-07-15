from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from fnmatch import fnmatchcase

from .models import SourceTrackInfo, TrackFilterConfig


class TrackPolicyError(ValueError):
    """Raised when an explicit track policy would create an unsafe plan."""

    code = "AUDIO_FILTER_EXCLUDES_ALL"


def decide_source_tracks(
    tracks: list[SourceTrackInfo],
    config: TrackFilterConfig,
    overrides: Mapping[int, bool] | None = None,
) -> list[SourceTrackInfo]:
    """Apply deterministic, conservative source-track decisions.

    Manual decisions are accepted only for track IDs observed by mkvmerge. Unknown
    audio language is preserved by default, and filtering remains opt-in.
    """

    known_ids = {track.id for track in tracks}
    unknown_overrides = sorted(set(overrides or {}) - known_ids)
    if unknown_overrides:
        values = ", ".join(str(value) for value in unknown_overrides)
        raise TrackPolicyError(f"Track override references unknown source track ID(s): {values}")

    decided = [_decide_track(track, config, overrides or {}) for track in tracks]
    audio = [track for track in decided if track.type == "audio"]
    if audio and not config.allow_no_audio and not any(track.included for track in audio):
        raise TrackPolicyError(
            "Audio filtering would exclude every source audio track while tracks.allow_no_audio is false"
        )
    return decided


def _decide_track(
    track: SourceTrackInfo,
    config: TrackFilterConfig,
    overrides: Mapping[int, bool],
) -> SourceTrackInfo:
    if track.type != "audio":
        return replace(
            track,
            included=True,
            decision_reason="preserve_non_audio",
            decision_source="default",
            matched_rule=None,
        )
    if track.id in overrides:
        included = overrides[track.id]
        return replace(
            track,
            included=included,
            decision_reason="manual_keep" if included else "manual_exclude",
            decision_source="manual",
            matched_rule=f"track_id:{track.id}",
        )
    if not config.audio_filter_enabled:
        return replace(
            track,
            included=True,
            decision_reason="preserve_filter_disabled",
            decision_source="default",
            matched_rule=None,
        )
    language = (track.language or "").strip().casefold()
    if config.keep_all_when_unknown and language in {"", "und", "unknown"}:
        return replace(
            track,
            included=True,
            decision_reason="preserve_unknown_metadata",
            decision_source="rule",
            matched_rule="keep_all_when_unknown",
        )
    if config.keep_default_audio and track.default_track:
        return replace(
            track,
            included=True,
            decision_reason="preserve_default_audio",
            decision_source="rule",
            matched_rule="keep_default_audio",
        )
    pattern = _matching_title_pattern(track.title, config.exclude_audio_title_patterns)
    if pattern is not None:
        return replace(
            track,
            included=False,
            decision_reason="exclude_title_pattern",
            decision_source="rule",
            matched_rule=f"exclude_audio_title_patterns:{pattern}",
        )
    languages = {value.strip().casefold() for value in config.keep_audio_languages if value.strip()}
    if languages:
        included = language in languages
        return replace(
            track,
            included=included,
            decision_reason="keep_language" if included else "exclude_language_not_allowed",
            decision_source="rule",
            matched_rule=f"keep_audio_languages:{track.language or ''}",
        )
    return replace(
        track,
        included=True,
        decision_reason="preserve_no_rule_matched",
        decision_source="default",
        matched_rule=None,
    )


def _matching_title_pattern(title: str | None, patterns: list[str]) -> str | None:
    folded_title = (title or "").casefold()
    if not folded_title:
        return None
    for raw_pattern in patterns:
        pattern = raw_pattern.strip()
        if not pattern:
            continue
        folded = pattern.casefold()
        if any(character in folded for character in "*?["):
            if fnmatchcase(folded_title, folded):
                return pattern
        elif folded in folded_title:
            return pattern
    return None
