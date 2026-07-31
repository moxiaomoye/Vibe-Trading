from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone

from src.investment_research.operations.daily_automation import (
    DailyOpportunityAutomation,
)
from src.investment_research.operations.scheduling import TradingDaySchedule


def test_daily_automation_is_disabled_by_default(tmp_path):
    calls = 0

    async def callback(_now):
        nonlocal calls
        calls += 1
        return {"ok": True}

    automation = DailyOpportunityAutomation(
        callback,
        tmp_path / "state.json",
        schedule=TradingDaySchedule(run_after=time(18, 30)),
        enabled=False,
    )
    result = asyncio.run(
        automation.tick(datetime(2026, 7, 29, 11, 0, tzinfo=timezone.utc))
    )
    assert result["tick"] == "disabled"
    assert calls == 0


def test_daily_automation_runs_once_and_persists_idempotency(tmp_path):
    calls = 0

    async def callback(_now):
        nonlocal calls
        calls += 1
        return {"report_date": "2026-07-29", "trading_executed": False}

    automation = DailyOpportunityAutomation(
        callback,
        tmp_path / "state.json",
        schedule=TradingDaySchedule(run_after=time(18, 30)),
        enabled=True,
    )
    now = datetime(2026, 7, 29, 11, 0, tzinfo=timezone.utc)
    first = asyncio.run(automation.tick(now))
    second = asyncio.run(automation.tick(now))

    assert first["tick"] == "completed"
    assert second["tick"] == "already_completed"
    assert calls == 1
    assert automation.status()["last_completed_trade_date"] == "2026-07-29"


def test_daily_automation_records_failure_without_raising(tmp_path):
    async def callback(_now):
        raise ConnectionError("fixture upstream unavailable")

    automation = DailyOpportunityAutomation(
        callback,
        tmp_path / "state.json",
        schedule=TradingDaySchedule(run_after=time(18, 30)),
        enabled=True,
    )
    result = asyncio.run(
        automation.tick(datetime(2026, 7, 29, 11, 0, tzinfo=timezone.utc))
    )
    assert result["tick"] == "failed"
    assert result["last_error"] == "ConnectionError"
