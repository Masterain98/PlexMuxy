from pathlib import Path

from plexmuxy.matcher import match_audios, match_subtitles


def test_exact_stem_match_explains_reason():
    matches, skipped = match_subtitles(Path("Example.mkv"), [Path("Example.chs.ass")])

    assert skipped == []
    assert matches[0].reason == "exact_stem"


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
