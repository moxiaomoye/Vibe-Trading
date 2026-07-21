"""Concurrency-safe job idempotency and notification outbox persistence."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..operations.models import DeliveryChannel, JobRun, JobStatus, OutboxMessage, OutboxStatus
from .sqlite import SQLiteResearchRepository


OPERATIONS_SCHEMA_VERSION = 6


class SQLiteOperationsRepository:
    def __init__(self, path: Path):
        self.path = path
        SQLiteResearchRepository(path)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_job_runs (
                    run_id TEXT PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(job_name, trade_date, mode)
                );
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    message_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    available_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_due
                    ON notification_outbox(status, available_at, created_at);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (OPERATIONS_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def acquire_run(self, run: JobRun, retry_failed: bool = True) -> bool:
        if run.status != JobStatus.RUNNING:
            raise ValueError("a newly acquired job must be running")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT status, attempt_count FROM research_job_runs WHERE job_name = ? AND trade_date = ? AND mode = ?",
                (run.job_name, run.trade_date.isoformat(), run.mode),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO research_job_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run.run_id, run.job_name, run.trade_date.isoformat(), run.mode, run.status.value,
                        run.attempt_count, run.started_at.isoformat(), run.updated_at.isoformat(), run.error,
                        OPERATIONS_SCHEMA_VERSION,
                    ),
                )
                connection.commit()
                return True
            if existing["status"] != JobStatus.FAILED.value or not retry_failed:
                connection.rollback()
                return False
            connection.execute(
                """UPDATE research_job_runs SET run_id = ?, status = ?, attempt_count = ?,
                started_at = ?, updated_at = ?, error = NULL WHERE job_name = ? AND trade_date = ? AND mode = ?""",
                (
                    run.run_id, JobStatus.RUNNING.value, existing["attempt_count"] + 1,
                    run.started_at.isoformat(), run.updated_at.isoformat(), run.job_name,
                    run.trade_date.isoformat(), run.mode,
                ),
            )
            connection.commit()
            return True

    def finish_run(self, run_id: str, status: JobStatus, updated_at: datetime, error: str | None = None) -> None:
        if status not in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
            raise ValueError("a finished job must succeed or fail")
        if updated_at.tzinfo is None or updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        if status == JobStatus.FAILED and not (error or "").strip():
            raise ValueError("a failed job requires an error")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE research_job_runs SET status = ?, updated_at = ?, error = ? WHERE run_id = ? AND status = ?",
                (status.value, updated_at.isoformat(), error, run_id, JobStatus.RUNNING.value),
            )
        if cursor.rowcount != 1:
            raise ValueError("job run is missing or no longer running")

    def get_run(self, job_name: str, trade_date: date, mode: str) -> JobRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_job_runs WHERE job_name = ? AND trade_date = ? AND mode = ?",
                (job_name, trade_date.isoformat(), mode),
            ).fetchone()
        if row is None:
            raise KeyError((job_name, trade_date, mode))
        return JobRun(
            row["run_id"], row["job_name"], date.fromisoformat(row["trade_date"]), row["mode"],
            JobStatus(row["status"]), row["attempt_count"], datetime.fromisoformat(row["started_at"]),
            datetime.fromisoformat(row["updated_at"]), row["error"],
        )

    def enqueue(self, message: OutboxMessage) -> bool:
        if message.status != OutboxStatus.PENDING or message.attempt_count != 0:
            raise ValueError("new outbox messages must be pending with zero attempts")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO notification_outbox VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message.message_id, message.idempotency_key, message.channel.value, message.message_type,
                    message.subject, message.body, message.source_id, message.status.value, message.attempt_count,
                    message.available_at.isoformat(), message.created_at.isoformat(), message.updated_at.isoformat(),
                    message.last_error, OPERATIONS_SCHEMA_VERSION,
                ),
            )
        return cursor.rowcount == 1

    def claim_due(self, now: datetime, limit: int = 20, max_attempts: int = 5) -> tuple[OutboxMessage, ...]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if limit < 1 or max_attempts < 1:
            raise ValueError("claim limit and maximum attempts must be positive")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT * FROM notification_outbox
                WHERE status IN (?, ?) AND available_at <= ? AND attempt_count < ?
                ORDER BY created_at LIMIT ?""",
                (OutboxStatus.PENDING.value, OutboxStatus.FAILED.value, now.isoformat(), max_attempts, limit),
            ).fetchall()
            ids = [row["message_id"] for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(
                    f"UPDATE notification_outbox SET status = ?, attempt_count = attempt_count + 1, "
                    f"updated_at = ?, last_error = NULL WHERE message_id IN ({placeholders})",
                    (OutboxStatus.SENDING.value, now.isoformat(), *ids),
                )
            connection.commit()
        return tuple(self.get_message(message_id) for message_id in ids)

    def finish_message(
        self,
        message_id: str,
        delivered: bool,
        updated_at: datetime,
        error: str | None = None,
        retry_at: datetime | None = None,
    ) -> None:
        status = OutboxStatus.DELIVERED if delivered else OutboxStatus.FAILED
        if not delivered and not (error or "").strip():
            raise ValueError("a failed delivery requires an error")
        if retry_at is not None and (retry_at.tzinfo is None or retry_at.utcoffset() is None):
            raise ValueError("retry_at must be timezone-aware")
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE notification_outbox SET status = ?, updated_at = ?, last_error = ?, available_at = ?
                WHERE message_id = ? AND status = ?""",
                (
                    status.value, updated_at.isoformat(), error,
                    (retry_at or updated_at).isoformat(), message_id, OutboxStatus.SENDING.value,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("outbox message is missing or not claimed")

    def get_message(self, message_id: str) -> OutboxMessage:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM notification_outbox WHERE message_id = ?", (message_id,)
            ).fetchone()
        if row is None:
            raise KeyError(message_id)
        return OutboxMessage(
            row["message_id"], row["idempotency_key"], DeliveryChannel(row["channel"]),
            row["message_type"], row["subject"], row["body"], row["source_id"],
            OutboxStatus(row["status"]), row["attempt_count"], datetime.fromisoformat(row["available_at"]),
            datetime.fromisoformat(row["created_at"]), datetime.fromisoformat(row["updated_at"]), row["last_error"],
        )
