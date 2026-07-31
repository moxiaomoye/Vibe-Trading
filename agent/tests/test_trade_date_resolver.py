from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.operations.trade_date import (
    DateResolution,
    TradeDateResolutionError,
    TradeDateResolver,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.mark.parametrize(
    ("now", "effective", "resolution"),
    [
        (
            datetime(2026, 7, 24, 19, 0, tzinfo=SHANGHAI),
            date(2026, 7, 24),
            DateResolution.CURRENT_COMPLETED_TRADING_DAY,
        ),
        (
            datetime(2026, 7, 24, 14, 0, tzinfo=SHANGHAI),
            date(2026, 7, 23),
            DateResolution.PREVIOUS_COMPLETED_TRADING_DAY,
        ),
        (
            datetime(2026, 7, 25, 10, 0, tzinfo=SHANGHAI),
            date(2026, 7, 24),
            DateResolution.PREVIOUS_COMPLETED_TRADING_DAY,
        ),
        (
            datetime(2026, 7, 26, 10, 0, tzinfo=SHANGHAI),
            date(2026, 7, 24),
            DateResolution.PREVIOUS_COMPLETED_TRADING_DAY,
        ),
    ],
)
def test_auto_resolves_latest_completed_trade_date(now, effective, resolution) -> None:
    result = TradeDateResolver().resolve(now=now)
    assert result.effective_trade_date == effective
    assert result.date_resolution is resolution


def test_exchange_closure_fixture_is_skipped() -> None:
    schedule = TradingDaySchedule(
        run_after=time(18, 30),
        excluded_dates=frozenset({date(2026, 10, 1), date(2026, 10, 2)}),
    )
    result = TradeDateResolver(schedule).resolve(
        now=datetime(2026, 10, 2, 20, 0, tzinfo=SHANGHAI)
    )
    assert result.effective_trade_date == date(2026, 9, 30)


def test_selected_trading_day_is_preserved() -> None:
    result = TradeDateResolver().resolve(
        now=datetime(2026, 7, 25, 10, 0, tzinfo=SHANGHAI),
        date_mode="selected",
        requested_date=date(2026, 7, 23),
    )
    assert result.effective_trade_date == date(2026, 7, 23)
    assert result.date_resolution is DateResolution.SELECTED_TRADING_DAY


def test_selected_weekend_adjusts_to_prior_trade_date() -> None:
    result = TradeDateResolver().resolve(
        now=datetime(2026, 7, 26, 10, 0, tzinfo=SHANGHAI),
        date_mode="selected",
        requested_date=date(2026, 7, 25),
    )
    assert result.effective_trade_date == date(2026, 7, 24)
    assert result.date_resolution is DateResolution.SELECTED_NON_TRADING_DAY_ADJUSTED


def test_future_selected_date_is_rejected() -> None:
    with pytest.raises(TradeDateResolutionError, match="future"):
        TradeDateResolver().resolve(
            now=datetime(2026, 7, 25, 10, 0, tzinfo=SHANGHAI),
            date_mode="selected",
            requested_date=date(2026, 7, 26),
        )


def test_selected_current_session_is_not_ready() -> None:
    with pytest.raises(TradeDateResolutionError) as caught:
        TradeDateResolver().resolve(
            now=datetime(2026, 7, 24, 14, 0, tzinfo=SHANGHAI),
            date_mode="selected",
            requested_date=date(2026, 7, 24),
        )
    assert caught.value.code == DateResolution.DATA_NOT_READY.value


def test_shanghai_date_boundary_uses_exchange_timezone() -> None:
    result = TradeDateResolver().resolve(
        now=datetime.fromisoformat("2026-07-24T16:30:00+00:00")
    )
    assert result.effective_trade_date == date(2026, 7, 24)
    assert result.date_resolution is DateResolution.PREVIOUS_COMPLETED_TRADING_DAY
