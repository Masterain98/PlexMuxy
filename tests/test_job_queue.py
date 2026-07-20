from __future__ import annotations

import threading
import time

from plexmuxy.job_store import JobStore
from plexmuxy.queue import JobQueue


def reviewed_job(store: JobStore, path):
    job = store.create_job(path)
    store.transition(job.id, "planning")
    store.transition(job.id, "awaiting_review")
    return job


def wait_for_state(store: JobStore, job_id: str, expected: str, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if store.get_job(job_id).state == expected:
            return
        time.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not reach {expected}; got {store.get_job(job_id).state}")


def test_queue_runs_one_directory_at_a_time_and_persists_terminal_reports(tmp_path):
    store = JobStore(tmp_path / "state.db")
    queue = JobQueue(store)
    queue.pause()
    first = reviewed_job(store, tmp_path / "one")
    second = reviewed_job(store, tmp_path / "two")
    running = 0
    peak = 0
    lock = threading.Lock()

    def runner(_cancel):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return {"cancelled": False, "failure_count": 0, "error": None}

    queue.submit(first.id, runner)
    queue.submit(second.id, runner)
    queue.reorder(second.id, 0)
    queue.resume()
    wait_for_state(store, first.id, "completed")
    wait_for_state(store, second.id, "completed")

    assert peak == 1
    assert store.load_report(first.id)["failure_count"] == 0
    assert store.list_events(first.id)[-1].event_type == "completed"
    queue.close()
    store.close()


def test_queue_cancel_distinguishes_pending_and_running_jobs(tmp_path):
    store = JobStore(tmp_path / "state.db")
    queue = JobQueue(store)
    queue.pause()
    pending = reviewed_job(store, tmp_path / "pending")
    queue.submit(pending.id, lambda _cancel: {})
    assert queue.cancel(pending.id) is True
    assert store.get_job(pending.id).state == "cancelled"

    running = reviewed_job(store, tmp_path / "running")

    def cancellable(cancel):
        cancel.wait(2)
        return {"cancelled": True, "failure_count": 0, "error": None}

    queue.submit(running.id, cancellable)
    queue.resume()
    wait_for_state(store, running.id, "running")
    assert queue.cancel(running.id) is True
    wait_for_state(store, running.id, "cancelled")
    queue.close()
    store.close()
