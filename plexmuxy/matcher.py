from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from .models import EpisodeIdentity, MatchingConfig, MatchResult, SkippedFile

LANGUAGE_TAIL_RE = re.compile(
    r"(?i)(?:[. _-](?:chs|sc|gb|cht|tc|jp|jpn|jap|jpsc|jptc|ru|rus|zh-hans|zh-hant))+$"
)
SEASON_EPISODE_RE = re.compile(r"(?i)(?<![A-Za-z0-9])S(\d{1,2})[ ._-]*E(?:P)?(\d{1,4})(?!\d)")
EPISODE_RE = re.compile(r"(?i)(?<![A-Za-z0-9])E(?:P)?[ ._-]?(\d{1,4})(?!\d)")
SPECIAL_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(?:SP|SPECIAL)[ ._-]?(\d{0,3})(?!\d)")
OVA_RE = re.compile(r"(?i)(?<![A-Za-z0-9])OVA[ ._-]?(\d{0,3})(?!\d)")
BRACKET_NUMBER_RE = re.compile(r"\[(\d{1,4})\]")
DOT_NUMBER_RE = re.compile(r"(?<!\d)\.(\d{1,4})\.(?!\d)")
TRAILING_NUMBER_RE = re.compile(r"(?:^|[ _.-])(\d{1,4})$")
BRACKETS_RE = re.compile(r"\[([^\]]*)\]")
NOISE_RE = re.compile(
    r"(?i)\b(?:1080p|2160p|720p|x26[45]|h26[45]|hevc|avc|aac|flac|web-?dl|bluray|bdrip|ma10p|hi10p)\b"
)


def parse_episode_identity(stem: str) -> EpisodeIdentity | None:
    text = LANGUAGE_TAIL_RE.sub("", unicodedata.normalize("NFKC", stem))
    match = SEASON_EPISODE_RE.search(text)
    if match:
        return EpisodeIdentity(season=int(match.group(1)), episode=int(match.group(2)), category="episode")
    match = SPECIAL_RE.search(text)
    if match:
        return EpisodeIdentity(episode=int(match.group(1) or 1), category="special")
    match = OVA_RE.search(text)
    if match:
        return EpisodeIdentity(episode=int(match.group(1) or 1), category="ova")
    match = EPISODE_RE.search(text)
    if match:
        return EpisodeIdentity(episode=int(match.group(1)), category="episode")
    match = BRACKET_NUMBER_RE.search(text)
    if match:
        return EpisodeIdentity(episode=int(match.group(1)), category="episode")
    match = DOT_NUMBER_RE.search(text)
    if match:
        return EpisodeIdentity(episode=int(match.group(1)), category="episode")
    match = TRAILING_NUMBER_RE.search(text)
    if match:
        return EpisodeIdentity(episode=int(match.group(1)), category="episode")
    return None


def extract_episode_token(stem: str) -> str | None:
    identity = parse_episode_identity(stem)
    if identity is None:
        return None
    if identity.category in {"ova", "special"}:
        return f"{identity.category}:{identity.episode or 1}"
    return f"s{identity.season or 0}:e{identity.episode}"


def normalize_title(stem: str) -> str:
    text = unicodedata.normalize("NFKC", stem)
    text = LANGUAGE_TAIL_RE.sub("", text)
    identity = parse_episode_identity(text)
    text = SEASON_EPISODE_RE.sub(" ", text)
    text = SPECIAL_RE.sub(" ", text)
    text = OVA_RE.sub(" ", text)
    text = EPISODE_RE.sub(" ", text)
    text = BRACKET_NUMBER_RE.sub(" ", text)
    text = DOT_NUMBER_RE.sub(" ", text)
    if identity is not None:
        text = TRAILING_NUMBER_RE.sub(" ", text)

    def strip_bracket(match: re.Match[str]) -> str:
        content = match.group(1)
        return " " if parse_episode_identity(f"[{content}]") is None else content

    text = BRACKETS_RE.sub(strip_bracket, text)
    text = NOISE_RE.sub(" ", text)
    text = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().casefold()


def exact_stem_match(video: Path, candidate: Path) -> bool:
    video_stem = video.stem.casefold()
    candidate_stem = candidate.stem.casefold()
    return candidate_stem == video_stem or candidate_stem.startswith((f"{video_stem}.", f"{video_stem} "))


def normalized_title_match(video: Path, candidate: Path) -> bool:
    video_title = normalize_title(video.stem)
    candidate_title = normalize_title(candidate.stem)
    if len(video_title) < 2 or len(candidate_title) < 2:
        return False
    video_episode = parse_episode_identity(video.stem)
    candidate_episode = parse_episode_identity(candidate.stem)
    if video_episode and candidate_episode and not episode_identities_match(video_episode, candidate_episode):
        return False
    return video_title == candidate_title or (
        min(len(video_title), len(candidate_title)) >= 4
        and (video_title in candidate_title or candidate_title in video_title)
    )


def episode_token_match(token: str, candidate_name: str) -> bool:
    return token == extract_episode_token(Path(candidate_name).stem)


def match_candidate(video: Path, candidate: Path, episode_token: str | None = None) -> MatchResult | None:
    if candidate.resolve() == video.resolve():
        return None
    if exact_stem_match(video, candidate):
        return MatchResult(candidate, 1.0, "exact_stem")
    if normalized_title_match(video, candidate):
        return MatchResult(candidate, 0.85, "normalized_title")
    video_identity = parse_episode_identity(video.stem)
    candidate_identity = parse_episode_identity(candidate.stem)
    if video_identity is not None and candidate_identity is not None and episode_identities_match(video_identity, candidate_identity):
        bracket = BRACKET_NUMBER_RE.search(video.stem)
        reason = f"episode_token={bracket.group(0)}" if bracket else f"episode_identity={extract_episode_token(video.stem)}"
        return MatchResult(candidate, 0.7, reason)
    return None


def episode_identities_match(left: EpisodeIdentity, right: EpisodeIdentity) -> bool:
    return (
        left.episode == right.episode
        and left.category == right.category
        and (left.season is None or right.season is None or left.season == right.season)
    )


def assign_candidates(
    videos: list[Path],
    candidates: list[Path],
    matching: MatchingConfig,
    allow_movie_fallback: bool = False,
) -> tuple[dict[Path, list[MatchResult]], list[SkippedFile]]:
    """Assign each resource once; equal best scores are reported as ambiguous."""
    assignments: dict[Path, list[MatchResult]] = {video: [] for video in videos}
    skipped: list[SkippedFile] = []
    for candidate in sorted(candidates, key=lambda item: item.name.casefold()):
        scored: list[tuple[Path, MatchResult]] = []
        for video in videos:
            result = match_candidate(video, candidate)
            if result is None:
                continue
            if result.reason.startswith(("episode_identity", "episode_token")) and not matching.allow_episode_only_match:
                continue
            if result.confidence >= matching.minimum_confidence:
                scored.append((video, result))
        if (
            not scored and allow_movie_fallback and matching.movie_fallback and len(videos) == 1
            and parse_episode_identity(videos[0].stem) is None
        ):
            video = videos[0]
            similarity = SequenceMatcher(None, normalize_title(video.stem), normalize_title(candidate.stem)).ratio()
            if similarity >= 0.35 and len(candidates) <= 5:
                scored.append((video, MatchResult(candidate, max(0.7, similarity), "controlled_movie_fallback")))
        if not scored:
            skipped.append(SkippedFile(candidate, "unmatched"))
            continue
        best = max(item[1].confidence for item in scored)
        winners = [(video, result) for video, result in scored if abs(result.confidence - best) < 1e-9]
        if len(winners) != 1:
            skipped.append(SkippedFile(candidate, "ambiguous_match"))
            continue
        video, result = winners[0]
        assignments[video].append(result)
    for results in assignments.values():
        results.sort(key=lambda item: (-item.confidence, item.file.name.casefold()))
    return assignments, skipped


def match_candidates(
    video: Path,
    candidates: list[Path],
    allow_movie_mode: bool = False,
    matching: MatchingConfig | None = None,
) -> tuple[list[MatchResult], list[SkippedFile]]:
    config = matching or MatchingConfig(movie_fallback=allow_movie_mode)
    assignments, skipped = assign_candidates([video], candidates, config, allow_movie_fallback=allow_movie_mode)
    return assignments[video], skipped


def match_subtitles(
    video: Path,
    subtitles: list[Path],
    movie_mode: bool = True,
    matching: MatchingConfig | None = None,
) -> tuple[list[MatchResult], list[SkippedFile]]:
    # Preserve the pre-0.2 helper behavior for direct callers. The planner
    # always supplies the explicit conservative MatchingConfig.
    if matching is None:
        matches = [match_candidate(video, item) for item in sorted(subtitles, key=lambda path: path.name.casefold())]
        filtered = [item for item in matches if item is not None]
        if not filtered and movie_mode and parse_episode_identity(video.stem) is None:
            return [MatchResult(item, 0.5, "movie_mode") for item in sorted(subtitles, key=lambda path: path.name.casefold())], []
        matched = {item.file for item in filtered}
        filtered.sort(key=lambda item: (-item.confidence, item.file.name.casefold()))
        return filtered, [SkippedFile(item, "unmatched") for item in subtitles if item not in matched]
    return match_candidates(video, subtitles, allow_movie_mode=movie_mode, matching=matching)


def match_audios(
    video: Path, audios: list[Path], matching: MatchingConfig | None = None
) -> tuple[list[MatchResult], list[SkippedFile]]:
    return match_candidates(video, audios, allow_movie_mode=False, matching=matching)
