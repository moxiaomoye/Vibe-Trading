"""Exchange-local daily schedule policy with explicit calendar overrides."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class TradingDaySchedule:
    timezone_name: str = "Asia/Shanghai"
    run_after: time = time(18, 30)
    excluded_dates: frozenset[date] = frozenset()
    included_dates: frozenset[date] = frozenset()

    def local_now(self, now: datetime) -> datetime:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return now.astimezone(ZoneInfo(self.timezone_name))

    def is_trading_day(self, day: date) -> bool:
        if day in self.included_dates:
            return True
        return day.weekday() < 5 and day not in self.excluded_dates

    def is_due(self, now: datetime) -> bool:
        local = self.local_now(now)
        return self.is_trading_day(local.date()) and local.time().replace(tzinfo=None) >= self.run_after
