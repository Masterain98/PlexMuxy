from pathlib import Path

import pytest

from plexmuxy.matcher import assign_candidates, match_candidate, parse_episode_identity
from plexmuxy.models import EpisodeIdentity, MatchingConfig


@pytest.mark.parametrize(
    ("name", "identity"),
    [
        ("Show [1]", EpisodeIdentity(None, 1, "episode")),
        ("Show [100]", EpisodeIdentity(None, 100, "episode")),
        ("Show S01E01", EpisodeIdentity(1, 1, "episode")),
        ("Show S01EP02", EpisodeIdentity(1, 2, "episode")),
        ("Show E03", EpisodeIdentity(None, 3, "episode")),
        ("Show EP04", EpisodeIdentity(None, 4, "episode")),
        ("Show.05.", EpisodeIdentity(None, 5, "episode")),
        ("Show SP01", EpisodeIdentity(None, 1, "special")),
        ("Show Special", EpisodeIdentity(None, 1, "special")),
        ("Show OVA", EpisodeIdentity(None, 1, "ova")),
    ],
)
def test_episode_identity_matrix(name, identity):
    assert parse_episode_identity(name) == identity


@pytest.mark.parametrize(
    ("video", "candidate"),
    [
        ("[VCB-Studio] 作品 [01][Ma10p_1080p].mkv", "[Kamigami] 作品 [01].chs.ass"),
        ("[Nekomoe kissaten] Show [02].mkv", "[Lilith-Raws] Show [02].cht.ass"),
        ("[Group A&Group B] 日本語タイトル [03].mkv", "日本語タイトル [03].jpn.ass"),
        ("English 中文 Title S01E04.mkv", "English 中文 Title EP04.chs.ass"),
    ],
)
def test_release_name_matrix_matches(video, candidate):
    result = match_candidate(Path(video), Path(candidate))
    assert result is not None
    assert result.confidence >= 0.7


def test_equal_best_candidates_are_ambiguous_and_not_assigned():
    videos = [Path("Group A Show [01].mkv"), Path("Group B Show [01].mkv")]
    candidate = Path("Show [01].chs.ass")
    assignments, skipped = assign_candidates(videos, [candidate], MatchingConfig())
    assert all(not values for values in assignments.values())
    assert skipped[0].reason == "ambiguous_match"


def test_default_matching_disables_movie_fallback():
    video = Path("Movie.mkv")
    assignments, skipped = assign_candidates([video], [Path("Signs.chs.ass")], MatchingConfig(), True)
    assert assignments[video] == []
    assert skipped[0].reason == "unmatched"
