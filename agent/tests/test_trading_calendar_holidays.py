"""R5: A-share trading calendar with holiday support — not just weekends."""

from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.operations.trading_calendar import TradingCalendar


def test_weekend_is_not_trading_day():
    """Weekends (Sat/Sun) must not be trading days."""
    cal = TradingCalendar()
    saturday = date(2025, 7, 26)
    sunday = date(2025, 7, 27)
    assert not cal.is_trading_day(saturday)
    assert not cal.is_trading_day(sunday)


def test_weekday_is_trading_day():
    """Weekdays without holiday exclusion must be trading days."""
    cal = TradingCalendar()
    monday = date(2025, 7, 28)
    assert cal.is_trading_day(monday)


def test_excluded_date_is_not_trading_day():
    """An excluded date (e.g. Spring Festival) must not be a trading day."""
    schedule = TradingDaySchedule(
        excluded_dates=frozenset({date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31)})
    )
    cal = TradingCalendar(schedule=schedule)
    assert not cal.is_trading_day(date(2025, 1, 29))
    assert not cal.is_trading_day(date(2025, 1, 30))


def test_nth_trading_day_skips_holidays():
    """nth_trading_day_forward must skip excluded holiday dates."""
    schedule = TradingDaySchedule(
        excluded_dates=frozenset({
            date(2025, 4, 28),  # Monday holiday
            date(2025, 4, 29),  # Tuesday holiday
        })
    )
    cal = TradingCalendar(schedule=schedule)

    start = date(2025, 4, 25)  # Friday
    next_td = cal.next_trading_day(start)
    # Apr 26 Sat, Apr 27 Sun, Apr 28 Mon (excluded), Apr 29 Tue (excluded), Apr 30 Wed
    assert next_td == date(2025, 4, 30), f"Expected Apr 30, got {next_td}"


def test_nth_trading_day_with_spring_festival():
    """T+20 spanning Spring Festival must skip all holiday days."""
    schedule = TradingDaySchedule(
        excluded_dates=frozenset({
            date(2026, 2, 16),  # Mon — CNY Eve
            date(2026, 2, 17),  # Tue — CNY
            date(2026, 2, 18),  # Wed
            date(2026, 2, 19),  # Thu
            date(2026, 2, 20),  # Fri
            date(2026, 2, 23),  # Mon — makeup holiday
            date(2026, 2, 24),  # Tue
            date(2026, 2, 25),  # Wed
        })
    )
    cal = TradingCalendar(schedule=schedule)

    start = date(2026, 2, 13)  # Friday before CNY
    t5 = cal.nth_trading_day_forward(start, 5)
    assert t5 is not None
    # Feb 13 Fri start. Trading days forward skipping holidays:
    # +1 = Feb 26 Thu (skip Feb 14 Sat, 15 Sun, 16-20 holiday, 21 Sat, 22 Sun, 23-25 holiday)
    assert t5 > date(2026, 2, 25), f"T+5 should be after holiday period, got {t5}"
    assert cal.is_trading_day(t5)


def test_holiday_calendar_marked_contract_only():
    """Warning: Chinese holiday data is manually maintained, not from a live source.

    The excluded_dates must be populated externally. The infrastructure
    (excluded_dates frozenset, is_trading_day check) works correctly but
    the holiday data is contract-only until a reliable source is connected.
    """
    schedule = TradingDaySchedule(excluded_dates=frozenset())
    cal = TradingCalendar(schedule=schedule)
    national_day = date(2025, 10, 1)  # Wednesday — should be holiday but isn't excluded
    assert cal.is_trading_day(national_day), (
        "Without excluded_dates, National Day is considered a trading day. "
        "This proves holiday data must be provided externally."
    )


def test_included_date_overrides_excluded():
    """included_dates can make a normally excluded day a trading day."""
    schedule = TradingDaySchedule(
        excluded_dates=frozenset({date(2026, 7, 27)}),
        included_dates=frozenset({date(2026, 7, 27)}),
    )
    cal = TradingCalendar(schedule=schedule)
    assert cal.is_trading_day(date(2026, 7, 27)), "included_dates must override excluded_dates"


KNOWN_HOLIDAYS_2025: set[date] = {
    # New Year
    date(2025, 1, 1),
    # Spring Festival (Jan 28 - Feb 3)
    date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30),
    date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 2), date(2025, 2, 3),
    # Qingming
    date(2025, 4, 4), date(2025, 4, 5), date(2025, 4, 6),
    # Labor Day
    date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 3),
    # Dragon Boat
    date(2025, 5, 31), date(2025, 6, 1), date(2025, 6, 2),
    # National Day + Mid-Autumn
    date(2025, 10, 1), date(2025, 10, 2), date(2025, 10, 3),
    date(2025, 10, 4), date(2025, 10, 5), date(2025, 10, 6), date(2025, 10, 7),
}

KNOWN_HOLIDAYS_2026: set[date] = {
    # New Year
    date(2026, 1, 1),
    # Spring Festival (Feb 16-25 — approximate)
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 2, 19), date(2026, 2, 20),
    date(2026, 2, 23), date(2026, 2, 24), date(2026, 2, 25),
    # Qingming
    date(2026, 4, 4), date(2026, 4, 5), date(2026, 4, 6),
    # Labor Day
    date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3),
    # Dragon Boat
    date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
    # National Day + Mid-Autumn
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3),
    date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
}


@pytest.mark.parametrize("holiday", sorted(KNOWN_HOLIDAYS_2025))
def test_known_2025_holidays_are_excluded(holiday: date):
    """All known 2025 Chinese holidays must be excluded from trading."""
    schedule = TradingDaySchedule(excluded_dates=frozenset(KNOWN_HOLIDAYS_2025))
    cal = TradingCalendar(schedule=schedule)
    if holiday.weekday() < 5:
        assert not cal.is_trading_day(holiday), f"{holiday} should not be a trading day"


@pytest.mark.parametrize("holiday", sorted(KNOWN_HOLIDAYS_2026))
def test_known_2026_holidays_are_excluded(holiday: date):
    """All known 2026 Chinese holidays must be excluded from trading."""
    schedule = TradingDaySchedule(excluded_dates=frozenset(KNOWN_HOLIDAYS_2026))
    cal = TradingCalendar(schedule=schedule)
    if holiday.weekday() < 5:
        assert not cal.is_trading_day(holiday), f"{holiday} should not be a trading day"
