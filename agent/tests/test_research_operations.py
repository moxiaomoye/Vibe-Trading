from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timezone

import pytest

from src.investment_research.operations.models import (
    DeliveryChannel,
    JobRun,
    JobStatus,
    OutboxMessage,
    OutboxStatus,
)
from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository


NOW = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)


def _run(run_id: str = "run-1") -> JobRun:
    return JobRun(run_id, "daily-research", date(2026, 7, 21), "shadow", JobStatus.RUNNING, 1, NOW, NOW)


def _message(message_id: str = "message-1") -> OutboxMessage:
    return OutboxMessage(
        message_id, "daily:2026-07-21:feishu", DeliveryChannel.FEISHU, "daily_research",
        "AI Investment Research Daily", "No new high-quality opportunity. Continue waiting.",
        "report-1", OutboxStatus.PENDING, 0, NOW, NOW, NOW,
    )


def test_trading_day_schedule_uses_exchange_local_time_and_overrides() -> None:
    schedule = TradingDaySchedule(run_after=time(18, 30))
    assert schedule.is_due(NOW)  # 18:30 in Asia/Shanghai
    assert not schedule.is_due(datetime(2026, 7, 21, 10, 29, tzinfo=timezone.utc))
    assert not schedule.is_trading_day(date(2026, 7, 25))
    holiday = TradingDaySchedule(excluded_dates=frozenset({date(2026, 7, 21)}))
    assert not holiday.is_due(NOW)
    weekend_override = TradingDaySchedule(included_dates=frozenset({date(2026, 7, 25)}))
    assert weekend_override.is_trading_day(date(2026, 7, 25))
    with pytest.raises(ValueError, match="timezone-aware"):
        schedule.is_due(NOW.replace(tzinfo=None))


def test_daily_job_is_idempotent_and_failed_runs_can_retry(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    assert repository.acquire_run(_run())
    assert not repository.acquire_run(replace(_run(), run_id="run-duplicate"))
    repository.finish_run("run-1", JobStatus.FAILED, NOW, "fixture failure")
    assert repository.acquire_run(replace(_run(), run_id="run-2"))
    retry = repository.get_run("daily-research", date(2026, 7, 21), "shadow")
    assert retry.run_id == "run-2"
    assert retry.attempt_count == 2
    repository.finish_run("run-2", JobStatus.SUCCEEDED, NOW)
    assert not repository.acquire_run(replace(_run(), run_id="run-3"))


def test_job_state_transitions_are_guarded(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    with pytest.raises(ValueError, match="running"):
        repository.acquire_run(replace(_run(), status=JobStatus.SUCCEEDED))
    repository.acquire_run(_run())
    with pytest.raises(ValueError, match="succeed or fail"):
        repository.finish_run("run-1", JobStatus.RUNNING, NOW)
    with pytest.raises(ValueError, match="requires an error"):
        repository.finish_run("run-1", JobStatus.FAILED, NOW)
    with pytest.raises(ValueError, match="missing"):
        repository.finish_run("missing", JobStatus.SUCCEEDED, NOW)


def test_outbox_deduplicates_claims_and_records_delivery(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    assert repository.enqueue(_message())
    assert not repository.enqueue(replace(_message(), message_id="message-duplicate"))
    claimed = repository.claim_due(NOW)
    assert len(claimed) == 1
    assert claimed[0].status == OutboxStatus.SENDING
    assert claimed[0].attempt_count == 1
    assert repository.claim_due(NOW) == ()
    repository.finish_message("message-1", True, NOW)
    assert repository.get_message("message-1").status == OutboxStatus.DELIVERED


def test_failed_outbox_delivery_is_retryable(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    repository.enqueue(_message())
    repository.claim_due(NOW)
    repository.finish_message("message-1", False, NOW, "fixture transport failure")
    retried = repository.claim_due(NOW)
    assert retried[0].attempt_count == 2
    assert retried[0].status == OutboxStatus.SENDING


def test_outbox_rejects_invalid_state_and_transitions(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    with pytest.raises(ValueError, match="pending"):
        repository.enqueue(replace(_message(), status=OutboxStatus.SENDING))
    with pytest.raises(ValueError, match="positive"):
        repository.claim_due(NOW, 0)
    repository.enqueue(_message())
    with pytest.raises(ValueError, match="requires an error"):
        repository.finish_message("message-1", False, NOW)
    with pytest.raises(ValueError, match="not claimed"):
        repository.finish_message("message-1", True, NOW)
