from pathlib import Path

from plexmuxy.matcher import match_audios, match_subtitles


def test_exact_stem_match_explains_reason():
    matches, skipped = match_subtitles(Path("Example.mkv"), [Path("Example.chs.ass")])

    assert skipped == []
    assert matches[0].reason == "exact_stem"


def test_candidate_with_multiple_mechanisms_uses_highest_priority_reason():
    matches, skipped = match_subtitles(Path("Show [02].mkv"), [Path("Show [02].chs.ass")])

    assert skipped == []
    assert len(matches) == 1
    assert matches[0].reason == "exact_stem"


def test_multiple_subtitle_candidates_are_sorted_by_priority():
    video = Path("Show [02].mkv")
    exact_stem_subtitle = Path("Show [02].chs.ass")
    episode_token_only_subtitle = Path("Other Release [02].chs.ass")

    matches, skipped = match_subtitles(video, [episode_token_only_subtitle, exact_stem_subtitle])

    assert skipped == []
    assert [match.file for match in matches] == [exact_stem_subtitle, episode_token_only_subtitle]
    assert [match.reason for match in matches] == ["exact_stem", "episode_token=[02]"]
    assert matches[0].confidence >= matches[1].confidence


def test_normalized_title_match_keeps_old_subgroup_pattern():
    video = Path("[VCB-Studio] Example Show [01][Ma10p_1080p].mkv")
    subtitle = Path("[Kamigami] Example Show [01].chs.ass")

    matches, _ = match_subtitles(video, [subtitle])

    assert matches[0].file == subtitle
    assert matches[0].reason == "normalized_title"


def test_episode_token_match_supports_dot_and_space_patterns():
    video = Path("Example Show [02].mkv")
    subtitle = Path("Other Release Example 02.chs.ass")

    matches, _ = match_subtitles(video, [subtitle])

    assert matches[0].reason == "episode_token=[02]"


def test_movie_mode_adds_all_subtitles_when_no_episode_token_matches():
    video = Path("Example Movie.mkv")
    subtitles = [Path("Commentary.chs.ass"), Path("Signs.cht.ass")]

    matches, skipped = match_subtitles(video, subtitles)

    assert skipped == []
    assert [match.reason for match in matches] == ["movie_mode", "movie_mode"]


def test_adjacent_episode_does_not_match_by_episode_token():
    video = Path("Example Show [01].mkv")
    subtitle = Path("Example Show [02].chs.ass")

    matches, skipped = match_subtitles(video, [subtitle])

    assert matches == []
    assert skipped[0].reason == "unmatched"


def test_audio_matching_does_not_use_movie_fallback():
    matches, skipped = match_audios(Path("Example Movie.mkv"), [Path("External.mka")])

    assert matches == []
    assert skipped[0].reason == "unmatched"
