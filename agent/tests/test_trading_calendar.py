from __future__ import annotations

from datetime import date, time

import pytest

from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.operations.trading_calendar import (
    TradingCalendar,
)


class TestTradingCalendar:
    def setup_method(self) -> None:
        self.cal = TradingCalendar()

    def test_previous_trading_day_monday_from_saturday(self) -> None:
        sat = date(2026, 7, 18)
        prev = self.cal.previous_trading_day(sat)
        assert prev is not None
        assert prev == date(2026, 7, 17)

    def test_previous_trading_day_monday_from_sunday(self) -> None:
        sun = date(2026, 7, 19)
        prev = self.cal.previous_trading_day(sun)
        assert prev == date(2026, 7, 17)

    def test_next_trading_day_friday_from_thursday(self) -> None:
        thu = date(2026, 7, 16)
        nxt = self.cal.next_trading_day(thu)
        assert nxt == date(2026, 7, 17)

    def test_next_trading_day_monday_from_friday(self) -> None:
        fri = date(2026, 7, 17)
        nxt = self.cal.next_trading_day(fri)
        assert nxt == date(2026, 7, 20)

    def test_nth_trading_day_forward_t5(self) -> None:
        d = date(2026, 7, 15)
        t5 = self.cal.nth_trading_day_forward(d, 5)
        assert t5 is not None
        assert t5 > d

    def test_nth_trading_day_forward_t20(self) -> None:
        d = date(2026, 7, 15)
        t20 = self.cal.nth_trading_day_forward(d, 20)
        assert t20 is not None
        assert t20 > d

    def test_nth_trading_day_forward_negative_n(self) -> None:
        d = date(2026, 7, 15)
        assert self.cal.nth_trading_day_forward(d, -1) is None

    def test_nth_trading_day_backward(self) -> None:
        d = date(2026, 7, 17)
        b1 = self.cal.nth_trading_day_backward(d, 1)
        assert b1 == date(2026, 7, 16)

    def test_trading_days_between(self) -> None:
        start = date(2026, 7, 13)
        end = date(2026, 7, 17)
        days = self.cal.trading_days_between(start, end)
        assert len(days) == 5
        assert days[0] == date(2026, 7, 13)
        assert days[-1] == date(2026, 7, 17)

    def test_trading_days_between_weekend(self) -> None:
        start = date(2026, 7, 17)
        end = date(2026, 7, 20)
        days = self.cal.trading_days_between(start, end)
        assert days == [date(2026, 7, 17), date(2026, 7, 20)]

    def test_is_trading_day(self) -> None:
        assert self.cal.is_trading_day(date(2026, 7, 15))
        assert not self.cal.is_trading_day(date(2026, 7, 18))

    def test_custom_schedule(self) -> None:
        d = date(2026, 7, 18)
        schedule = TradingDaySchedule(included_dates=frozenset([d]))
        cal = TradingCalendar(schedule)
        assert cal.is_trading_day(d)
        assert cal.next_trading_day(date(2026, 7, 17)) == d
