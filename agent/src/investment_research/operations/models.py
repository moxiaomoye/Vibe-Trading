"""Immutable operational records; no broker or order concepts belong here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class JobStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DeliveryChannel(StrEnum):
    EMAIL = "email"
    FEISHU = "feishu"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JobRun:
    run_id: str
    job_name: str
    trade_date: date
    mode: str
    status: JobStatus
    attempt_count: int
    started_at: datetime
    updated_at: datetime
    error: str | None = None

    def __post_init__(self) -> None:
        _aware(self.started_at, "started_at")
        _aware(self.updated_at, "updated_at")
        if not all((self.run_id, self.job_name, self.mode)) or self.attempt_count < 1:
            raise ValueError("job identity, mode, and a positive attempt count are required")
        if self.updated_at < self.started_at:
            raise ValueError("updated_at cannot precede started_at")
        if self.status == JobStatus.FAILED and not (self.error or "").strip():
            raise ValueError("a failed job requires an error")


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    message_id: str
    idempotency_key: str
    channel: DeliveryChannel
    message_type: str
    subject: str
    body: str
    source_id: str
    status: OutboxStatus
    attempt_count: int
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.available_at, "available_at"),
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
        ):
            _aware(value, name)
        if not all((self.message_id, self.idempotency_key, self.message_type, self.subject, self.body, self.source_id)):
            raise ValueError("outbox identity, content, and source are required")
        if self.attempt_count < 0:
            raise ValueError("outbox attempt count cannot be negative")
        if self.status == OutboxStatus.FAILED and not (self.last_error or "").strip():
            raise ValueError("a failed outbox message requires an error")
