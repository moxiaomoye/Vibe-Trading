"""Default-off, dry-run orchestration for the panic research pipeline."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Callable, Generic, Protocol, TypeVar

from ..operations.scheduling import TradingDaySchedule


T = TypeVar("T")


class TriggerSource(StrEnum):
    MANUAL = "manual"
    SCHEDULER = "scheduler"


class OrchestrationStatus(StrEnum):
    DISABLED = "disabled"
    NOT_DUE = "not_due"
    STALE_DATA = "stale_data"
    DUPLICATE = "duplicate"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PanicRuntimeFlags:
    feature_enabled: bool = False
    routes_enabled: bool = False
    scheduler_enabled: bool = False
    notification_enabled: bool = False


@dataclass(frozen=True, slots=True)
class OrchestrationRequest:
    run_id: str
    now: datetime
    data_date: date
    data_available_at: datetime
    trigger: TriggerSource = TriggerSource.MANUAL
    mode: str = "shadow"

    def __post_init__(self) -> None:
        _aware(self.now, "now")
        _aware(self.data_available_at, "data_available_at")
        if not self.run_id or self.mode != "shadow":
            raise ValueError("a run identity and shadow mode are required")


@dataclass(frozen=True, slots=True)
class StoredRun:
    key: str
    run_id: str
    state: RunState
    attempt_count: int
    updated_at: datetime
    error: str | None = None

    def __post_init__(self) -> None:
        _aware(self.updated_at, "updated_at")
        if not self.key or not self.run_id or self.attempt_count < 1:
            raise ValueError("stored run identity and attempts are required")
        if self.state == RunState.FAILED and not (self.error or "").strip():
            raise ValueError("failed runs require an error")


class OrchestrationStateStore(Protocol):
    def acquire(self, key: str, run_id: str, now: datetime, max_attempts: int) -> StoredRun | None: ...
    def finish(self, key: str, run_id: str, state: RunState, now: datetime, error: str | None = None) -> None: ...
    def get(self, key: str) -> StoredRun | None: ...


class InMemoryOrchestrationState:
    """Shared adapter proves restart idempotency without changing the database."""

    def __init__(self) -> None:
        self._runs: dict[str, StoredRun] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, run_id: str, now: datetime, max_attempts: int) -> StoredRun | None:
        with self._lock:
            previous = self._runs.get(key)
            if previous is None:
                current = StoredRun(key, run_id, RunState.RUNNING, 1, now)
            elif previous.state != RunState.FAILED or previous.attempt_count >= max_attempts:
                return None
            else:
                current = StoredRun(key, run_id, RunState.RUNNING, previous.attempt_count + 1, now)
            self._runs[key] = current
            return current

    def finish(self, key: str, run_id: str, state: RunState, now: datetime, error: str | None = None) -> None:
        if state not in {RunState.SUCCEEDED, RunState.FAILED}:
            raise ValueError("finished orchestration must succeed or fail")
        with self._lock:
            current = self._runs.get(key)
            if current is None or current.run_id != run_id or current.state != RunState.RUNNING:
                raise ValueError("orchestration run is missing or no longer running")
            self._runs[key] = replace(current, state=state, updated_at=now, error=error)

    def get(self, key: str) -> StoredRun | None:
        with self._lock:
            return self._runs.get(key)


@dataclass(frozen=True, slots=True)
class OrchestrationResult(Generic[T]):
    status: OrchestrationStatus
    run_key: str
    trade_date: date
    attempt_count: int
    reasons: tuple[str, ...]
    output: T | None = None
    error: str | None = None
    shadow_run: bool = True
    notification_attempted: bool = False

    def __post_init__(self) -> None:
        if not self.run_key or not self.reasons or not self.shadow_run:
            raise ValueError("orchestration result identity, reasons and shadow mode are required")
        if self.notification_attempted:
            raise ValueError("shadow orchestration cannot attempt notification")


class PanicResearchOrchestrator:
    job_name = "panic-research-shadow"

    def __init__(
        self,
        state: OrchestrationStateStore,
        *,
        schedule: TradingDaySchedule | None = None,
        flags: PanicRuntimeFlags | None = None,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("maximum attempts must be positive")
        self.state = state
        self.schedule = schedule or TradingDaySchedule()
        self.flags = flags or PanicRuntimeFlags()
        self.max_attempts = max_attempts

    def run(self, request: OrchestrationRequest, execute: Callable[[], T]) -> OrchestrationResult[T]:
        trade_date = self.schedule.local_now(request.now).date()
        key = f"{self.job_name}:{request.mode}:{trade_date.isoformat()}"
        gate = self._gate(request, trade_date)
        if gate is not None:
            status, reason = gate
            return OrchestrationResult(status, key, trade_date, 0, (reason,))

        acquired = self.state.acquire(key, request.run_id, request.now, self.max_attempts)
        if acquired is None:
            prior = self.state.get(key)
            attempts = prior.attempt_count if prior else 0
            return OrchestrationResult(
                OrchestrationStatus.DUPLICATE, key, trade_date, attempts,
                ("once_per_trading_day_or_retry_limit",),
            )
        try:
            output = execute()
        except Exception as exc:  # isolation boundary: caller receives state, core remains alive
            error = f"{type(exc).__name__}: {exc}"
            self.state.finish(key, request.run_id, RunState.FAILED, request.now, error)
            return OrchestrationResult(
                OrchestrationStatus.FAILED, key, trade_date, acquired.attempt_count,
                ("shadow_pipeline_failure_isolated",), error=error,
            )
        self.state.finish(key, request.run_id, RunState.SUCCEEDED, request.now)
        return OrchestrationResult(
            OrchestrationStatus.SUCCEEDED, key, trade_date, acquired.attempt_count,
            ("shadow_pipeline_completed",), output=output,
        )

    def _gate(self, request: OrchestrationRequest, trade_date: date):
        if not self.flags.feature_enabled:
            return OrchestrationStatus.DISABLED, "feature_disabled"
        if request.trigger == TriggerSource.SCHEDULER and not self.flags.scheduler_enabled:
            return OrchestrationStatus.DISABLED, "scheduler_disabled"
        if self.flags.notification_enabled:
            return OrchestrationStatus.DISABLED, "real_notifications_not_permitted"
        if not self.schedule.is_due(request.now):
            return OrchestrationStatus.NOT_DUE, "market_not_closed_or_not_trading_day"
        if request.data_date != trade_date:
            return OrchestrationStatus.STALE_DATA, "data_date_does_not_match_trade_date"
        if request.data_available_at > request.now:
            return OrchestrationStatus.STALE_DATA, "data_not_available_at_run_time"
        return None


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
