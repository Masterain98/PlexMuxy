from __future__ import annotations

from dataclasses import replace

import pytest

from plexmuxy.models import SourceTrackInfo, TrackFilterConfig
from plexmuxy.track_policy import TrackPolicyError, decide_source_tracks


def audio(track_id: int, **values) -> SourceTrackInfo:
    return SourceTrackInfo(id=track_id, type="audio", **values)


def test_filter_is_opt_in_and_non_audio_is_always_preserved():
    tracks = [
        SourceTrackInfo(id=0, type="video"),
        audio(1, language="eng", title="Director Commentary"),
    ]

    decided = decide_source_tracks(
        tracks,
        TrackFilterConfig(exclude_audio_title_patterns=["commentary"]),
    )

    assert [track.included for track in decided] == [True, True]
    assert decided[1].decision_reason == "preserve_filter_disabled"


def test_manual_override_precedes_rules_and_records_audit_fields():
    track = audio(1, language="eng", title="Director Commentary")
    config = TrackFilterConfig(
        audio_filter_enabled=True,
        exclude_audio_title_patterns=["*commentary*"],
        allow_no_audio=True,
    )

    decided = decide_source_tracks([track], config, {1: True})[0]

    assert decided.included is True
    assert decided.decision_source == "manual"
    assert decided.decision_reason == "manual_keep"
    assert decided.matched_rule == "track_id:1"


def test_unknown_language_and_default_audio_are_conservatively_preserved():
    config = TrackFilterConfig(
        audio_filter_enabled=True,
        exclude_audio_title_patterns=["commentary"],
        keep_audio_languages=["jpn"],
    )

    unknown, default = decide_source_tracks([
        audio(1, language="und", title="Mystery"),
        audio(2, language="eng", title="Commentary", default_track=True),
    ], config)

    assert unknown.included is True
    assert unknown.decision_reason == "preserve_unknown_metadata"
    assert default.included is True
    assert default.decision_reason == "preserve_default_audio"


def test_title_pattern_then_language_allowlist_are_applied_case_insensitively():
    config = TrackFilterConfig(
        audio_filter_enabled=True,
        exclude_audio_title_patterns=["Commentary"],
        keep_audio_languages=["JPN"],
        keep_default_audio=False,
        allow_no_audio=True,
    )

    commentary, japanese, english = decide_source_tracks([
        audio(1, language="jpn", title="DIRECTOR COMMENTARY"),
        audio(2, language="jpn", title="Main"),
        audio(3, language="eng", title="Main"),
    ], config)

    assert commentary.included is False
    assert commentary.decision_reason == "exclude_title_pattern"
    assert japanese.included is True
    assert japanese.decision_reason == "keep_language"
    assert english.included is False
    assert english.decision_reason == "exclude_language_not_allowed"


def test_excluding_every_source_audio_is_blocked_unless_explicitly_allowed():
    config = TrackFilterConfig(
        audio_filter_enabled=True,
        keep_audio_languages=["jpn"],
        keep_default_audio=False,
    )

    with pytest.raises(TrackPolicyError, match="exclude every source audio"):
        decide_source_tracks([audio(1, language="eng")], config)

    allowed = decide_source_tracks(
        [audio(1, language="eng")],
        replace(config, allow_no_audio=True),
    )
    assert allowed[0].included is False


def test_unknown_track_override_is_rejected():
    with pytest.raises(TrackPolicyError, match="unknown source track"):
        decide_source_tracks([audio(1)], TrackFilterConfig(), {99: False})
