from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jobs import INTERRUPT_ON_STARTUP, JobEvent, JobRecord, JobState, require_transition

STATE_DB_SCHEMA_VERSION = 1


class JobStoreError(RuntimeError):
    pass


def platform_state_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "PlexMuxy" / "state.db"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PlexMuxy" / "state.db"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "plexmuxy" / "state.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or platform_state_path()).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            self._configure()
            self._migrate()
        except sqlite3.DatabaseError as exc:
            self._connection.close()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
            if self.path.exists():
                shutil.copy2(self.path, backup)
            raise JobStoreError(
                f"Task history database is damaged. The original was preserved and copied to {backup}"
            ) from exc

    def _configure(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            current = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if current > STATE_DB_SCHEMA_VERSION:
                raise JobStoreError(
                    f"State database schema {current} is newer than supported {STATE_DB_SCHEMA_VERSION}"
                )
            if current < 1:
                self._connection.executescript("""
                    CREATE TABLE jobs (
                        id TEXT PRIMARY KEY,
                        input_dir TEXT NOT NULL,
                        state TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        plan_id TEXT,
                        config_hash TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        retry_of TEXT REFERENCES jobs(id),
                        position INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX jobs_state_position ON jobs(state, position, created_at);
                    CREATE TABLE job_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                        event_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        data_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE INDEX job_events_job_created ON job_events(job_id, created_at);
                    CREATE TABLE job_snapshots (
                        job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                        snapshot_json TEXT NOT NULL
                    );
                    CREATE TABLE job_reports (
                        job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                        report_json TEXT NOT NULL
                    );
                """)
                self._connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (1, utc_now()),
                )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create_job(self, input_dir: Path, *, retry_of: str | None = None) -> JobRecord:
        path = input_dir.expanduser().resolve()
        now = utc_now()
        job_id = str(uuid.uuid4())
        with self._lock, self._connection:
            position = self._connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM jobs WHERE state IN ('queued', 'queued_for_execution')"
            ).fetchone()[0]
            self._connection.execute(
                """INSERT INTO jobs(
                    id, input_dir, state, created_at, updated_at, retry_of, position
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?)""",
                (job_id, str(path), now, now, retry_of, position),
            )
            self._append_event_locked(job_id, "retried" if retry_of else "created", {
                "retry_of": retry_of,
            })
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM jobs WHERE id = ?", (str(job_id),)).fetchone()
        if row is None:
            raise JobStoreError(f"Unknown job ID: {job_id}")
        return _job_from_row(row)

    def list_jobs(self, *, limit: int = 100) -> list[JobRecord]:
        safe_limit = max(1, min(int(limit), 1000))
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def transition(
        self,
        job_id: str,
        target: JobState,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        event_type: str | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> JobRecord:
        with self._lock, self._connection:
            current = self.get_job(job_id)
            require_transition(current.state, target)
            now = utc_now()
            started_at = now if target == "running" and current.started_at is None else current.started_at
            finished_at = now if target in {"completed", "failed", "cancelled", "interrupted"} else None
            self._connection.execute(
                """UPDATE jobs SET state = ?, updated_at = ?, started_at = ?, finished_at = ?,
                    error_code = ?, error_message = ? WHERE id = ?""",
                (target, now, started_at, finished_at, error_code, error_message, job_id),
            )
            self._append_event_locked(job_id, event_type or target, event_data or {})
        return self.get_job(job_id)

    def save_plan(
        self,
        job_id: str,
        snapshot: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        plan_id = str(snapshot.get("plan_id") or "") or None
        config_hash = str(snapshot.get("config_hash") or "") or None
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO job_snapshots(job_id, snapshot_json) VALUES (?, ?)",
                (job_id, _json(snapshot)),
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO job_reports(job_id, report_json) VALUES (?, ?)",
                (job_id, _json(report)),
            )
            self._connection.execute(
                "UPDATE jobs SET plan_id = ?, config_hash = ?, updated_at = ? WHERE id = ?",
                (plan_id, config_hash, utc_now(), job_id),
            )

    def save_report(self, job_id: str, report: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO job_reports(job_id, report_json) VALUES (?, ?)",
                (job_id, _json(report)),
            )

    def load_snapshot(self, job_id: str) -> dict[str, Any] | None:
        return self._load_json("job_snapshots", "snapshot_json", job_id)

    def load_report(self, job_id: str) -> dict[str, Any] | None:
        return self._load_json("job_reports", "report_json", job_id)

    def _load_json(self, table: str, column: str, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                f"SELECT {column} FROM {table} WHERE job_id = ?", (job_id,)  # noqa: S608 - fixed identifiers.
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def append_event(self, job_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
        with self._lock, self._connection:
            self._append_event_locked(job_id, event_type, data or {})

    def _append_event_locked(self, job_id: str, event_type: str, data: dict[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO job_events(job_id, event_type, created_at, data_json) VALUES (?, ?, ?, ?)",
            (job_id, event_type, utc_now(), _json(data)),
        )

    def list_events(self, job_id: str) -> list[JobEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
        return [JobEvent(
            id=row["id"],
            job_id=row["job_id"],
            event_type=row["event_type"],
            created_at=row["created_at"],
            data=json.loads(row["data_json"]),
        ) for row in rows]

    def latest_event(self, job_id: str, event_type: str | None = None) -> JobEvent | None:
        query = "SELECT * FROM job_events WHERE job_id = ?"
        parameters: tuple[Any, ...] = (job_id,)
        if event_type is not None:
            query += " AND event_type = ?"
            parameters = (job_id, event_type)
        query += " ORDER BY id DESC LIMIT 1"
        with self._lock:
            row = self._connection.execute(query, parameters).fetchone()
        if row is None:
            return None
        return JobEvent(
            id=row["id"],
            job_id=row["job_id"],
            event_type=row["event_type"],
            created_at=row["created_at"],
            data=json.loads(row["data_json"]),
        )

    def mark_interrupted(self) -> int:
        placeholders = ",".join("?" for _ in INTERRUPT_ON_STARTUP)
        states = tuple(INTERRUPT_ON_STARTUP)
        with self._lock, self._connection:
            rows = self._connection.execute(
                f"SELECT id, state FROM jobs WHERE state IN ({placeholders})", states  # noqa: S608
            ).fetchall()
            now = utc_now()
            for row in rows:
                self._connection.execute(
                    "UPDATE jobs SET state = 'interrupted', updated_at = ?, finished_at = ?, error_code = ?, error_message = ? WHERE id = ?",
                    (now, now, "APP_INTERRUPTED", "Application exited before the task reached a terminal state", row["id"]),
                )
                self._append_event_locked(row["id"], "interrupted", {"previous_state": row["state"]})
        return len(rows)

    def reorder(self, ordered_job_ids: list[str]) -> None:
        if len(ordered_job_ids) != len(set(ordered_job_ids)):
            raise JobStoreError("Queue order contains duplicate job IDs")
        with self._lock, self._connection:
            for position, job_id in enumerate(ordered_job_ids):
                row = self._connection.execute(
                    "SELECT state FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                if row is None or row["state"] not in {"queued", "queued_for_execution"}:
                    raise JobStoreError("Only queued jobs can be reordered")
                self._connection.execute(
                    "UPDATE jobs SET position = ?, updated_at = ? WHERE id = ?",
                    (position, utc_now(), job_id),
                )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        input_dir=row["input_dir"],
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        plan_id=row["plan_id"],
        config_hash=row["config_hash"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        retry_of=row["retry_of"],
        position=row["position"],
    )
