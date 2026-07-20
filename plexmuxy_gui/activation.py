from __future__ import annotations

import urllib.parse
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ActivationRequest:
    job_id: str
    action: str = "view"


def parse_activation_uri(value: str) -> ActivationRequest | None:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme.casefold() != "plexmuxy" or parsed.netloc.casefold() != "job":
        return None
    path = parsed.path.strip("/")
    try:
        job_id = str(uuid.UUID(path))
    except (ValueError, AttributeError):
        return None
    query = urllib.parse.parse_qs(parsed.query, strict_parsing=False)
    if set(query) - {"action"}:
        return None
    action = (query.get("action") or ["view"])[0]
    if action not in {"view", "output"}:
        return None
    return ActivationRequest(job_id, action)


def parse_activation_args(argv: list[str]) -> ActivationRequest | None:
    if len(argv) != 1:
        return None
    return parse_activation_uri(argv[0])
