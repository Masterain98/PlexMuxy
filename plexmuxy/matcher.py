from __future__ import annotations

import re
from pathlib import Path

from .models import MatchResult, SkippedFile


BRACKET_METADATA_RE = re.compile(r"\[(?![Ss][Pp]?\d{2}\]|\d{2}\]|Special\]|OVA\]).*?\]", re.IGNORECASE)
EPISODE_TOKEN_RE = re.compile(r"\[(?:[Ss][Pp]?\d{2}|\d{2}|Special|OVA)\]", re.IGNORECASE)


def match_subtitles(video: Path, subtitles: list[Path], movie_mode: bool = True) -> tuple[list[MatchResult], list[SkippedFile]]:
    return match_candidates(video, subtitles, allow_movie_mode=movie_mode)


def match_audios(video: Path, audios: list[Path]) -> tuple[list[MatchResult], list[SkippedFile]]:
    return match_candidates(video, audios, allow_movie_mode=False)


def match_candidates(
    video: Path,
    candidates: list[Path],
    allow_movie_mode: bool = False,
) -> tuple[list[MatchResult], list[SkippedFile]]:
    matches: list[MatchResult] = []
    matched_paths: set[Path] = set()
    episode_token = extract_episode_token(video.stem)

    for candidate in sorted(candidates, key=lambda item: item.name.lower()):
        result = match_candidate(video, candidate, episode_token)
        if result is None:
            continue
        matches.append(result)
        matched_paths.add(candidate)

    if allow_movie_mode and not matches and episode_token is None:
        for candidate in sorted(candidates, key=lambda item: item.name.lower()):
            matches.append(MatchResult(file=candidate, confidence=0.5, reason="movie_mode"))
            matched_paths.add(candidate)

    skipped = [
        SkippedFile(path=candidate, reason="unmatched")
        for candidate in sorted(candidates, key=lambda item: item.name.lower())
        if candidate not in matched_paths
    ]
    return matches, skipped


def match_candidate(video: Path, candidate: Path, episode_token: str | None = None) -> MatchResult | None:
    if candidate == video:
        return None
    if exact_stem_match(video, candidate):
        return MatchResult(file=candidate, confidence=1.0, reason="exact_stem")
    if normalized_title_match(video, candidate):
        return MatchResult(file=candidate, confidence=0.85, reason="normalized_title")
    token = episode_token if episode_token is not None else extract_episode_token(video.stem)
    if token and episode_token_match(token, candidate.name):
        return MatchResult(file=candidate, confidence=0.7, reason=f"episode_token={token}")
    return None


def exact_stem_match(video: Path, candidate: Path) -> bool:
    video_stem = video.stem.lower()
    candidate_stem = candidate.stem.lower()
    return (
        candidate_stem == video_stem
        or candidate_stem.startswith(f"{video_stem}.")
        or candidate_stem.startswith(f"{video_stem} ")
    )


def normalized_title_match(video: Path, candidate: Path) -> bool:
    video_title = normalize_title(video.stem)
    candidate_title = normalize_title(candidate.stem)
    if len(video_title) < 4 or len(candidate_title) < 4:
        return False
    return video_title in candidate_title or candidate_title in video_title


def normalize_title(stem: str) -> str:
    without_metadata = BRACKET_METADATA_RE.sub("", stem)
    without_language_tail = re.sub(r"(?i)(?:\.(?:chs|sc|gb|cht|tc|jp|jpn|jap|jpsc|jptc|ru|rus))+$", "", without_metadata)
    return re.sub(r"\s+", " ", without_language_tail).strip().lower()


def extract_episode_token(stem: str) -> str | None:
    match = EPISODE_TOKEN_RE.search(stem)
    if match is None:
        return None
    return match.group(0)


def episode_token_match(token: str, candidate_name: str) -> bool:
    candidate = candidate_name.lower()
    inner = token.strip("[]").lower()
    variants = {
        token.lower(),
        f" {inner} ",
        f".{inner}.",
        f" {inner}.",
    }
    return any(variant in candidate for variant in variants)
