from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone

from src.investment_research.application.panic_orchestration import (
    InMemoryOrchestrationState,
    OrchestrationRequest,
    OrchestrationStatus,
    PanicResearchOrchestrator,
    PanicRuntimeFlags,
    RunState,
    TriggerSource,
)
from src.investment_research.operations.scheduling import TradingDaySchedule


NOW = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)
DATE = date(2026, 7, 21)
SCHEDULE = TradingDaySchedule(run_after=time(18, 30))


def _request(**changes):
    values = dict(run_id="run-1", now=NOW, data_date=DATE, data_available_at=NOW - timedelta(minutes=1))
    values.update(changes)
    return OrchestrationRequest(**values)


def _orchestrator(state=None, flags=None, max_attempts=2):
    return PanicResearchOrchestrator(
        state or InMemoryOrchestrationState(), schedule=SCHEDULE,
        flags=flags or PanicRuntimeFlags(feature_enabled=True), max_attempts=max_attempts,
    )


def test_all_runtime_capabilities_are_default_off_and_separate() -> None:
    result = PanicResearchOrchestrator(InMemoryOrchestrationState(), schedule=SCHEDULE).run(
        _request(), lambda: "not-run"
    )
    assert result.status == OrchestrationStatus.DISABLED
    assert result.reasons == ("feature_disabled",)

    flags = PanicRuntimeFlags(feature_enabled=True, routes_enabled=False, scheduler_enabled=False)
    manual = _orchestrator(flags=flags).run(_request(), lambda: "manual-output")
    assert manual.status == OrchestrationStatus.SUCCEEDED
    scheduled = _orchestrator(flags=flags).run(
        _request(trigger=TriggerSource.SCHEDULER), lambda: "not-run"
    )
    assert scheduled.status == OrchestrationStatus.DISABLED
    assert scheduled.reasons == ("scheduler_disabled",)


def test_post_close_trading_day_and_data_freshness_gates() -> None:
    orchestrator = _orchestrator()
    before_close = orchestrator.run(_request(now=NOW - timedelta(minutes=1)), lambda: None)
    assert before_close.status == OrchestrationStatus.NOT_DUE
    stale = orchestrator.run(_request(data_date=date(2026, 7, 18)), lambda: None)
    assert stale.status == OrchestrationStatus.STALE_DATA
    future = orchestrator.run(_request(data_available_at=NOW + timedelta(seconds=1)), lambda: None)
    assert future.status == OrchestrationStatus.STALE_DATA
    weekend = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    assert orchestrator.run(
        _request(now=weekend, data_date=weekend.date(), data_available_at=weekend), lambda: None
    ).status == OrchestrationStatus.NOT_DUE


def test_same_store_preserves_idempotency_across_orchestrator_restart() -> None:
    state = InMemoryOrchestrationState()
    first = _orchestrator(state).run(_request(), lambda: {"result": "ok"})
    restarted = _orchestrator(state).run(_request(run_id="run-2"), lambda: {"result": "duplicate"})
    assert first.status == OrchestrationStatus.SUCCEEDED
    assert first.output == {"result": "ok"}
    assert restarted.status == OrchestrationStatus.DUPLICATE
    assert state.get(first.run_key).state == RunState.SUCCEEDED


def test_failure_is_isolated_and_retry_is_bounded() -> None:
    state = InMemoryOrchestrationState()
    orchestrator = _orchestrator(state, max_attempts=2)

    def fail():
        raise RuntimeError("fixture provider unavailable")

    first = orchestrator.run(_request(), fail)
    second = orchestrator.run(_request(run_id="run-2"), fail)
    third = orchestrator.run(_request(run_id="run-3"), lambda: "not-run")
    assert first.status == OrchestrationStatus.FAILED
    assert second.status == OrchestrationStatus.FAILED
    assert second.attempt_count == 2
    assert third.status == OrchestrationStatus.DUPLICATE
    assert "fixture provider unavailable" in second.error


def test_real_notification_flag_blocks_shadow_execution() -> None:
    flags = PanicRuntimeFlags(feature_enabled=True, notification_enabled=True)
    result = _orchestrator(flags=flags).run(_request(), lambda: "not-run")
    assert result.status == OrchestrationStatus.DISABLED
    assert result.reasons == ("real_notifications_not_permitted",)
    assert result.notification_attempted is False
