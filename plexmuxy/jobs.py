from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

JobState = Literal[
    "queued",
    "planning",
    "awaiting_review",
    "queued_for_execution",
    "running",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]

TERMINAL_STATES: frozenset[JobState] = frozenset({"completed", "failed", "cancelled", "interrupted"})
INTERRUPT_ON_STARTUP: frozenset[JobState] = frozenset({
    "planning",
    "queued_for_execution",
    "running",
    "cancelling",
})

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    "queued": frozenset({"planning", "cancelled"}),
    "planning": frozenset({"awaiting_review", "failed", "cancelled", "interrupted"}),
    "awaiting_review": frozenset({"queued_for_execution", "planning", "cancelled"}),
    "queued_for_execution": frozenset({"running", "cancelled", "interrupted"}),
    "running": frozenset({"completed", "failed", "cancelling", "cancelled", "interrupted"}),
    "cancelling": frozenset({"cancelled", "failed", "interrupted"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
}


class InvalidJobTransition(ValueError):
    pass


def require_transition(current: JobState, target: JobState) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidJobTransition(f"Invalid job transition: {current} -> {target}")


@dataclass(frozen=True)
class JobRecord:
    id: str
    input_dir: str
    state: JobState
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    plan_id: str | None = None
    config_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_of: str | None = None
    position: int = 0


@dataclass(frozen=True)
class JobEvent:
    id: int
    job_id: str
    event_type: str
    created_at: str
    data: dict
