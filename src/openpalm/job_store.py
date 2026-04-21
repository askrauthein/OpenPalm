from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import threading

from openpalm.agent_models import Job


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    base_ref TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    work_branch TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_summary TEXT,
                    error_message TEXT,
                    cancelled INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oneoff_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    raw_output TEXT NOT NULL,
                    tokens_used INTEGER,
                    exit_code INTEGER NOT NULL,
                    error TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    agent TEXT PRIMARY KEY,
                    total_tokens INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create_job(self, job: Job) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    job_id, project_id, agent, instruction, base_ref,
                    workspace_path, work_branch, status, created_at, updated_at,
                    result_summary, error_message, cancelled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.project_id,
                    job.agent,
                    job.instruction,
                    job.base_ref,
                    job.workspace_path,
                    job.work_branch,
                    job.status,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    job.result_summary,
                    job.error_message,
                    1 if job.cancelled else 0,
                ),
            )

    def update_status(self, job_id: str, status: str, *, summary: str | None = None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, result_summary=COALESCE(?, result_summary), error_message=COALESCE(?, error_message) WHERE job_id=?",
                (status, now, summary, error, job_id),
            )

    def cancel(self, job_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute("UPDATE jobs SET cancelled=1, status='cancelled', updated_at=? WHERE job_id=?", (now, job_id))

    def is_cancelled(self, job_id: str) -> bool:
        row = self._conn.execute("SELECT cancelled FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return bool(row and row["cancelled"])

    def get(self, job_id: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def list_jobs(self, limit: int = 20) -> list[Job]:
        rows = self._conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_row_to_job(r) for r in rows]

    def list_active_jobs(self, limit: int = 100) -> list[Job]:
        rows = self._conn.execute(
            """
            SELECT * FROM jobs
            WHERE status NOT IN ('succeeded', 'failed', 'cancelled')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]

    def add_event(self, job_id: str, event_type: str, payload: str = "") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO job_events (job_id, ts, event_type, payload) VALUES (?, ?, ?, ?)",
                (job_id, datetime.now(timezone.utc).isoformat(), event_type, payload),
            )

    def list_events(self, job_id: str, limit: int = 100) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()

    def record_oneoff_run(
        self,
        *,
        agent: str,
        prompt: str,
        answer: str,
        raw_output: str,
        tokens_used: int | None,
        exit_code: int,
        error: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO oneoff_runs (ts, agent, prompt, answer, raw_output, tokens_used, exit_code, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, agent, prompt, answer, raw_output, tokens_used, exit_code, error),
            )
            if tokens_used is not None:
                row = self._conn.execute("SELECT total_tokens FROM token_usage WHERE agent=?", (agent,)).fetchone()
                if row:
                    self._conn.execute(
                        "UPDATE token_usage SET total_tokens=?, updated_at=? WHERE agent=?",
                        (int(row["total_tokens"]) + int(tokens_used), now, agent),
                    )
                else:
                    self._conn.execute(
                        "INSERT INTO token_usage (agent, total_tokens, updated_at) VALUES (?, ?, ?)",
                        (agent, int(tokens_used), now),
                    )

    def token_totals(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT agent, total_tokens FROM token_usage ORDER BY agent ASC").fetchall()
        return {str(r["agent"]): int(r["total_tokens"]) for r in rows}


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        job_id=row["job_id"],
        project_id=row["project_id"],
        agent=row["agent"],
        instruction=row["instruction"],
        base_ref=row["base_ref"],
        workspace_path=row["workspace_path"],
        work_branch=row["work_branch"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        result_summary=row["result_summary"],
        error_message=row["error_message"],
        cancelled=bool(row["cancelled"]),
    )
