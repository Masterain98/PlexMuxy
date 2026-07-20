from __future__ import annotations

import sqlite3

import pytest

from plexmuxy.job_store import JobStore, JobStoreError
from plexmuxy.jobs import InvalidJobTransition


def test_job_store_persists_state_plan_report_and_events(tmp_path):
    path = tmp_path / "state.db"
    store = JobStore(path)
    job = store.create_job(tmp_path / "media")
    store.transition(job.id, "planning", event_type="plan_started")
    store.save_plan(
        job.id,
        {"plan_id": "plan-1", "config_hash": "hash", "plans": []},
        {"plans": [], "snapshot": {"plan_id": "plan-1"}},
    )
    store.transition(job.id, "awaiting_review", event_type="plan_completed")
    store.close()

    reopened = JobStore(path)
    persisted = reopened.get_job(job.id)
    assert persisted.state == "awaiting_review"
    assert persisted.plan_id == "plan-1"
    assert reopened.load_snapshot(job.id)["plan_id"] == "plan-1"
    assert reopened.load_report(job.id)["plans"] == []
    assert [event.event_type for event in reopened.list_events(job.id)] == [
        "created", "plan_started", "plan_completed",
    ]
    reopened.close()


def test_job_store_rejects_invalid_transition_and_marks_active_jobs_interrupted(tmp_path):
    path = tmp_path / "state.db"
    store = JobStore(path)
    active = store.create_job(tmp_path / "active")
    store.transition(active.id, "planning")
    with pytest.raises(InvalidJobTransition):
        store.transition(active.id, "completed")
    store.close()

    reopened = JobStore(path)
    assert reopened.mark_interrupted() == 1
    interrupted = reopened.get_job(active.id)
    assert interrupted.state == "interrupted"
    assert interrupted.error_code == "APP_INTERRUPTED"
    assert reopened.mark_interrupted() == 0
    reopened.close()


def test_job_store_retry_links_new_job_and_queue_reorder_is_guarded(tmp_path):
    store = JobStore(tmp_path / "state.db")
    original = store.create_job(tmp_path / "one")
    retry = store.create_job(tmp_path / "two", retry_of=original.id)
    store.reorder([retry.id, original.id])

    assert retry.retry_of == original.id
    assert store.get_job(retry.id).position == 0
    assert store.list_events(retry.id)[0].event_type == "retried"

    store.transition(original.id, "planning")
    with pytest.raises(JobStoreError, match="Only queued"):
        store.reorder([original.id])
    store.close()


def test_damaged_database_is_preserved_with_clear_recovery_error(tmp_path):
    path = tmp_path / "state.db"
    path.write_bytes(b"not sqlite")

    with pytest.raises(JobStoreError, match="preserved"):
        JobStore(path)

    assert list(tmp_path.glob("state.db.corrupt-*"))
    with pytest.raises(sqlite3.DatabaseError):
        connection = sqlite3.connect(path)
        try:
            connection.execute("SELECT * FROM jobs").fetchall()
        finally:
            connection.close()
