from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterator

from .scheduling import TradingDaySchedule


class TradingCalendar:
    """Forward and backward trading day resolution using TradingDaySchedule."""

    def __init__(
        self,
        schedule: TradingDaySchedule | None = None,
        *,
        max_lookback_days: int = 370,
        max_lookforward_days: int = 370,
    ) -> None:
        self.schedule = schedule or TradingDaySchedule()
        self.max_lookback_days = max_lookback_days
        self.max_lookforward_days = max_lookforward_days

    def previous_trading_day(self, start: date) -> date | None:
        candidate = start
        for _ in range(self.max_lookback_days):
            candidate -= timedelta(days=1)
            if self.schedule.is_trading_day(candidate):
                return candidate
        return None

    def next_trading_day(self, start: date) -> date | None:
        candidate = start
        for _ in range(self.max_lookforward_days):
            candidate += timedelta(days=1)
            if self.schedule.is_trading_day(candidate):
                return candidate
        return None

    def nth_trading_day_forward(self, start: date, n: int) -> date | None:
        if n < 0:
            return None
        candidate = start
        count = 0
        for _ in range(self.max_lookforward_days):
            candidate += timedelta(days=1)
            if self.schedule.is_trading_day(candidate):
                count += 1
                if count == n:
                    return candidate
        return None

    def nth_trading_day_backward(self, start: date, n: int) -> date | None:
        if n < 0:
            return None
        candidate = start
        count = 0
        for _ in range(self.max_lookback_days):
            candidate -= timedelta(days=1)
            if self.schedule.is_trading_day(candidate):
                count += 1
                if count == n:
                    return candidate
        return None

    def trading_days_between(self, start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            if self.schedule.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    def is_trading_day(self, day: date) -> bool:
        return self.schedule.is_trading_day(day)
