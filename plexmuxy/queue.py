from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .job_store import JobStore
from .jobs import JobRecord

JobRunner = Callable[[threading.Event], dict[str, Any]]
TerminalCallback = Callable[[JobRecord], None]


@dataclass
class QueuedExecution:
    job_id: str
    runner: JobRunner
    cancel_event: threading.Event = field(default_factory=threading.Event)


class JobQueue:
    """Sequential directory-level scheduler with persistent state transitions."""

    def __init__(self, store: JobStore, terminal_callback: TerminalCallback | None = None) -> None:
        self.store = store
        self.store.mark_interrupted()
        self._condition = threading.Condition()
        self._pending: list[QueuedExecution] = []
        self._active: QueuedExecution | None = None
        self._paused = False
        self._stopping = False
        self._terminal_callback = terminal_callback
        self._worker = threading.Thread(target=self._work, name="plexmuxy-job-queue", daemon=True)
        self._worker.start()

    def submit(self, job_id: str, runner: JobRunner) -> None:
        with self._condition:
            if self._stopping:
                raise RuntimeError("Job queue is closed")
            if self.store.get_job(job_id).state != "awaiting_review":
                raise ValueError("Only reviewed jobs can be queued for execution")
            self.store.transition(job_id, "queued_for_execution", event_type="execution_queued")
            self._pending.append(QueuedExecution(job_id, runner))
            self._sync_positions()
            self._condition.notify_all()

    def pause(self) -> None:
        with self._condition:
            self._paused = True

    def resume(self) -> None:
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    @property
    def paused(self) -> bool:
        with self._condition:
            return self._paused

    def reorder(self, job_id: str, position: int) -> None:
        with self._condition:
            current = next((index for index, item in enumerate(self._pending) if item.job_id == job_id), None)
            if current is None:
                raise ValueError("Only pending jobs can be reordered")
            item = self._pending.pop(current)
            target = max(0, min(int(position), len(self._pending)))
            self._pending.insert(target, item)
            self._sync_positions()

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            for index, item in enumerate(self._pending):
                if item.job_id == job_id:
                    item.cancel_event.set()
                    self._pending.pop(index)
                    self.store.transition(job_id, "cancelled", event_type="cancellation_requested")
                    self._sync_positions()
                    return True
            if self._active is not None and self._active.job_id == job_id:
                current = self.store.get_job(job_id)
                if current.state == "running":
                    self.store.transition(job_id, "cancelling", event_type="cancellation_requested")
                self._active.cancel_event.set()
                return True
        return False

    def close(self) -> None:
        with self._condition:
            self._stopping = True
            if self._active is not None:
                self._active.cancel_event.set()
            self._condition.notify_all()
        self._worker.join(timeout=5)

    def _sync_positions(self) -> None:
        if self._pending:
            self.store.reorder([item.job_id for item in self._pending])

    def _work(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopping or (not self._paused and bool(self._pending))
                )
                if self._stopping:
                    return
                item = self._pending.pop(0)
                self._active = item
                self._sync_positions()
            self._run(item)
            with self._condition:
                self._active = None

    def _run(self, item: QueuedExecution) -> None:
        started = time.perf_counter()
        try:
            self.store.transition(item.job_id, "running", event_type="execution_started")
            report = item.runner(item.cancel_event)
            self.store.save_report(item.job_id, report)
            current = self.store.get_job(item.job_id)
            if bool(report.get("cancelled")) or item.cancel_event.is_set():
                if current.state == "running":
                    self.store.transition(item.job_id, "cancelling", event_type="cancellation_requested")
                self.store.transition(item.job_id, "cancelled")
            elif report.get("error") is not None or int(report.get("failure_count", 0)) > 0:
                self.store.transition(
                    item.job_id,
                    "failed",
                    error_code=report.get("error_code"),
                    error_message=report.get("error") or "One or more mux operations failed",
                )
            else:
                self.store.transition(item.job_id, "completed")
        except Exception as exc:  # noqa: BLE001 - queue must persist terminal failure.
            logging.exception("Queued job failed")
            current = self.store.get_job(item.job_id)
            if current.state in {"running", "cancelling"}:
                self.store.transition(
                    item.job_id,
                    "failed",
                    error_code="UNHANDLED_JOB_ERROR",
                    error_message=str(exc),
                )
        finally:
            terminal = self.store.get_job(item.job_id)
            logging.info(
                "Queued job reached terminal state",
                extra={
                    "job_id": item.job_id,
                    "plan_id": terminal.plan_id,
                    "phase": terminal.state,
                    "error_code": terminal.error_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            if self._terminal_callback is not None:
                try:
                    self._terminal_callback(terminal)
                except Exception:  # noqa: BLE001 - observers cannot change job results.
                    logging.exception("Job terminal callback failed")
