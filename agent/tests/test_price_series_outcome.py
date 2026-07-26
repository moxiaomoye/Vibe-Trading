"""R4: Tests for PriceSeriesOutcomeLoader with hand-calculable price series."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.investment_research.operations.outcome_loader import DEFAULT_HORIZONS
from src.investment_research.operations.price_series_outcome_loader import (
    PriceSeriesOutcomeLoader,
    PriceSnapshot,
)

TRADING_DAYS: list[date] = [
    date(2025, 7, 21),  # T  (Monday)
    date(2025, 7, 22),  # T+1
    date(2025, 7, 23),  # T+2
    date(2025, 7, 24),  # T+3
    date(2025, 7, 25),  # T+4
    date(2025, 7, 28),  # T+5 (Monday, weekend skipped)
    date(2025, 7, 29),  # T+6
    date(2025, 7, 30),  # T+7
    date(2025, 7, 31),  # T+8
    date(2025, 8, 1),   # T+9
    date(2025, 8, 4),   # T+10
    date(2025, 8, 5),   # T+11
    date(2025, 8, 6),   # T+12
    date(2025, 8, 7),   # T+13
    date(2025, 8, 8),   # T+14
    date(2025, 8, 11),  # T+15
    date(2025, 8, 12),  # T+16
    date(2025, 8, 13),  # T+17
    date(2025, 8, 14),  # T+18
    date(2025, 8, 15),  # T+19
    date(2025, 8, 18),  # T+20 (Monday)
    date(2025, 8, 19),  # T+21
    date(2025, 8, 20),  # T+22
    date(2025, 8, 21),  # T+23
    date(2025, 8, 22),  # T+24
    date(2025, 8, 25),  # T+25
    date(2025, 8, 26),  # T+26
    date(2025, 8, 27),  # T+27
    date(2025, 8, 28),  # T+28
    date(2025, 8, 29),  # T+29
    date(2025, 9, 1),   # T+30
    date(2025, 9, 2),   # T+31
    date(2025, 9, 3),   # T+32
    date(2025, 9, 4),   # T+33
    date(2025, 9, 5),   # T+34
    date(2025, 9, 8),   # T+35
    date(2025, 9, 9),   # T+36
    date(2025, 9, 10),  # T+37
    date(2025, 9, 11),  # T+38
    date(2025, 9, 12),  # T+39
    date(2025, 9, 15),  # T+40
    date(2025, 9, 16),  # T+41
    date(2025, 9, 17),  # T+42
    date(2025, 9, 18),  # T+43
    date(2025, 9, 19),  # T+44
    date(2025, 9, 22),  # T+45
    date(2025, 9, 23),  # T+46
    date(2025, 9, 24),  # T+47
    date(2025, 9, 25),  # T+48
    date(2025, 9, 26),  # T+49
    date(2025, 9, 29),  # T+50
    date(2025, 9, 30),  # T+51
    date(2025, 10, 8),  # T+52 (after National Day holiday)
    date(2025, 10, 9),  # T+53
    date(2025, 10, 10), # T+54
    date(2025, 10, 13), # T+55
    date(2025, 10, 14), # T+56
    date(2025, 10, 15), # T+57
    date(2025, 10, 16), # T+58
    date(2025, 10, 17), # T+59
    date(2025, 10, 20), # T+60 (Monday)
]

PRICES: dict[date, PriceSnapshot] = {
    # Stock: steadily rising from 10 to 16, then dropping
    # CSI 300: mildly rising from 4000 to 4400, then dropping
    date(2025, 7, 21): PriceSnapshot(close=10.00, csi300_close=4000.0),
    date(2025, 7, 22): PriceSnapshot(close=10.50, csi300_close=4020.0),
    date(2025, 7, 23): PriceSnapshot(close=10.80, csi300_close=4050.0),
    date(2025, 7, 24): PriceSnapshot(close=11.00, csi300_close=4030.0),
    date(2025, 7, 25): PriceSnapshot(close=11.20, csi300_close=4060.0),
    date(2025, 7, 28): PriceSnapshot(close=11.50, csi300_close=4080.0),
    date(2025, 7, 29): PriceSnapshot(close=12.00, csi300_close=4100.0),
    date(2025, 7, 30): PriceSnapshot(close=13.00, csi300_close=4150.0),
    date(2025, 7, 31): PriceSnapshot(close=14.00, csi300_close=4200.0),
    date(2025, 8, 1):  PriceSnapshot(close=15.00, csi300_close=4250.0),
    date(2025, 8, 4):  PriceSnapshot(close=16.00, csi300_close=4300.0),
    date(2025, 8, 5):  PriceSnapshot(close=15.50, csi300_close=4280.0),
    date(2025, 8, 6):  PriceSnapshot(close=15.00, csi300_close=4250.0),
    date(2025, 8, 7):  PriceSnapshot(close=14.50, csi300_close=4220.0),
    date(2025, 8, 8):  PriceSnapshot(close=14.00, csi300_close=4200.0),
    date(2025, 8, 11): PriceSnapshot(close=13.50, csi300_close=4180.0),
    date(2025, 8, 12): PriceSnapshot(close=13.00, csi300_close=4150.0),
    date(2025, 8, 13): PriceSnapshot(close=12.50, csi300_close=4120.0),
    date(2025, 8, 14): PriceSnapshot(close=12.00, csi300_close=4100.0),
    date(2025, 8, 15): PriceSnapshot(close=11.50, csi300_close=4080.0),
    date(2025, 8, 18): PriceSnapshot(close=11.00, csi300_close=4050.0),
    date(2025, 8, 19): PriceSnapshot(close=10.50, csi300_close=4020.0),
    date(2025, 8, 20): PriceSnapshot(close=10.00, csi300_close=4000.0),
    date(2025, 8, 21): PriceSnapshot(close=9.50,  csi300_close=3980.0),
    date(2025, 8, 22): PriceSnapshot(close=9.00,  csi300_close=3950.0),
    date(2025, 8, 25): PriceSnapshot(close=8.50,  csi300_close=3920.0),
    date(2025, 8, 26): PriceSnapshot(close=8.00,  csi300_close=3900.0),
    date(2025, 8, 27): PriceSnapshot(close=8.50,  csi300_close=3910.0),
    date(2025, 8, 28): PriceSnapshot(close=9.00,  csi300_close=3930.0),
    date(2025, 8, 29): PriceSnapshot(close=9.50,  csi300_close=3950.0),
    date(2025, 9, 1):  PriceSnapshot(close=10.00, csi300_close=3980.0),
    date(2025, 9, 2):  PriceSnapshot(close=10.50, csi300_close=4000.0),
    date(2025, 9, 3):  PriceSnapshot(close=11.00, csi300_close=4020.0),
    date(2025, 9, 4):  PriceSnapshot(close=11.50, csi300_close=4050.0),
    date(2025, 9, 5):  PriceSnapshot(close=12.00, csi300_close=4080.0),
    date(2025, 9, 8):  PriceSnapshot(close=12.50, csi300_close=4100.0),
    date(2025, 9, 9):  PriceSnapshot(close=13.00, csi300_close=4120.0),
    date(2025, 9, 10): PriceSnapshot(close=13.50, csi300_close=4150.0),
    date(2025, 9, 11): PriceSnapshot(close=14.00, csi300_close=4180.0),
    date(2025, 9, 12): PriceSnapshot(close=14.50, csi300_close=4200.0),
    date(2025, 9, 15): PriceSnapshot(close=15.00, csi300_close=4220.0),
    date(2025, 9, 16): PriceSnapshot(close=14.00, csi300_close=4200.0),
    date(2025, 9, 17): PriceSnapshot(close=13.00, csi300_close=4180.0),
    date(2025, 9, 18): PriceSnapshot(close=12.00, csi300_close=4150.0),
    date(2025, 9, 19): PriceSnapshot(close=11.00, csi300_close=4120.0),
    date(2025, 9, 22): PriceSnapshot(close=10.00, csi300_close=4100.0),
    date(2025, 9, 23): PriceSnapshot(close=9.00,  csi300_close=4080.0),
    date(2025, 9, 24): PriceSnapshot(close=8.00,  csi300_close=4050.0),
    date(2025, 9, 25): PriceSnapshot(close=9.00,  csi300_close=4080.0),
    date(2025, 9, 26): PriceSnapshot(close=10.00, csi300_close=4100.0),
    date(2025, 9, 29): PriceSnapshot(close=11.00, csi300_close=4120.0),
    date(2025, 9, 30): PriceSnapshot(close=12.00, csi300_close=4150.0),
    date(2025, 10, 8): PriceSnapshot(close=13.00, csi300_close=4180.0),
    date(2025, 10, 9): PriceSnapshot(close=14.00, csi300_close=4200.0),
    date(2025, 10, 10): PriceSnapshot(close=15.00, csi300_close=4220.0),
    date(2025, 10, 13): PriceSnapshot(close=14.00, csi300_close=4200.0),
    date(2025, 10, 14): PriceSnapshot(close=13.00, csi300_close=4180.0),
    date(2025, 10, 15): PriceSnapshot(close=12.00, csi300_close=4150.0),
    date(2025, 10, 16): PriceSnapshot(close=11.00, csi300_close=4120.0),
    date(2025, 10, 17): PriceSnapshot(close=10.00, csi300_close=4100.0),
    date(2025, 10, 20): PriceSnapshot(close=9.00,  csi300_close=4080.0),
}


@pytest.fixture
def known_prices() -> dict[date, PriceSnapshot]:
    return PRICES


@pytest.fixture
def loader(known_prices) -> PriceSeriesOutcomeLoader:
    from src.investment_research.operations.trading_calendar import TradingCalendar
    cal = TradingCalendar()
    return PriceSeriesOutcomeLoader(
        calendar=cal,
        price_fetcher=known_prices.get,
    )


def _find_horizon_date(trading_days: list[date], n: int) -> date:
    """Return the n-th trading day after T (index 0)."""
    idx = TRADING_DAYS.index(trading_days[0])
    return trading_days[idx + n]


class TestPriceSeriesHandCalculable:
    def test_entry_price(self, loader):
        """Entry price must equal the close on evaluation_date."""
        outcome = loader.load(date(2025, 7, 21))
        assert outcome.entry_price == 10.00

    def test_t5_asset_return(self, loader):
        """T+5: asset_return = (11.50/10.00) - 1 = 0.15."""
        outcome = loader.load(date(2025, 7, 21))
        w5 = [w for w in outcome.windows if w.horizon == 5][0]
        assert w5.data_gap is None
        assert w5.asset_return is not None
        assert abs(w5.asset_return - 0.15) < 1e-10, f"Expected 0.15, got {w5.asset_return}"

    def test_t5_benchmark_return(self, loader):
        """T+5: benchmark_return = (4080/4000) - 1 = 0.02."""
        outcome = loader.load(date(2025, 7, 21))
        w5 = [w for w in outcome.windows if w.horizon == 5][0]
        assert w5.benchmark_return is not None
        assert abs(w5.benchmark_return - 0.02) < 1e-10, f"Expected 0.02, got {w5.benchmark_return}"

    def test_t5_excess_return(self, loader):
        """T+5: excess_return = 0.15 - 0.02 = 0.13."""
        outcome = loader.load(date(2025, 7, 21))
        w5 = [w for w in outcome.windows if w.horizon == 5][0]
        assert w5.excess_return is not None
        assert abs(w5.excess_return - 0.13) < 1e-10, f"Expected 0.13, got {w5.excess_return}"

    def test_t5_max_drawdown_none(self, loader):
        """T to T+5: prices rise monotonically (10→11.5), no drawdown → None."""
        outcome = loader.load(date(2025, 7, 21))
        w5 = [w for w in outcome.windows if w.horizon == 5][0]
        assert w5.maximum_drawdown is None, "Monotonically rising prices should have no drawdown"

    def test_t20_values(self, loader):
        """T+20: close=11.00, csi300=4050.
        asset_return = (11.00/10.00)-1 = 0.10
        benchmark_return = (4050/4000)-1 = 0.0125
        excess_return = 0.10 - 0.0125 = 0.0875
        """
        outcome = loader.load(date(2025, 7, 21))
        w20 = [w for w in outcome.windows if w.horizon == 20][0]
        assert w20.data_gap is None
        assert w20.asset_return is not None
        assert w20.benchmark_return is not None
        assert w20.excess_return is not None
        assert abs(w20.asset_return - 0.10) < 1e-10, f"asset_return: {w20.asset_return}"
        assert abs(w20.benchmark_return - 0.0125) < 1e-10, f"benchmark_return: {w20.benchmark_return}"
        assert abs(w20.excess_return - 0.0875) < 1e-10, f"excess_return: {w20.excess_return}"

    def test_t60_values(self, loader):
        """T+60 (2025-10-13 with weekend-only calendar): close=14.00, csi300=4200.
        asset_return = (14.00/10.00)-1 = 0.40
        benchmark_return = (4200/4000)-1 = 0.05
        excess_return = 0.40 - 0.05 = 0.35
        max_drawdown: peak 16.0 (Aug 4), trough 8.0 (Sep 24) = (8/16)-1 = -0.50
        """
        outcome = loader.load(date(2025, 7, 21))
        w60 = [w for w in outcome.windows if w.horizon == 60][0]
        assert w60.data_gap is None
        assert w60.asset_return is not None
        assert w60.benchmark_return is not None
        assert w60.excess_return is not None
        assert abs(w60.asset_return - 0.40) < 1e-10, f"asset_return: {w60.asset_return}"
        assert abs(w60.benchmark_return - 0.05) < 1e-10, f"benchmark_return: {w60.benchmark_return}"
        assert abs(w60.excess_return - 0.35) < 1e-10, f"excess_return: {w60.excess_return}"
        assert w60.maximum_drawdown is not None
        assert abs(w60.maximum_drawdown - (-0.50)) < 1e-6, f"maximum_drawdown: {w60.maximum_drawdown}"

    def test_all_horizons_present(self, loader):
        """Must have windows for all DEFAULT_HORIZONS."""
        outcome = loader.load(date(2025, 7, 21))
        horizons = {w.horizon for w in outcome.windows}
        assert horizons == set(DEFAULT_HORIZONS), f"Expected {DEFAULT_HORIZONS}, got {horizons}"

    def test_missing_price_returns_data_gap(self):
        """If price data is missing for a horizon, data_gap must be set, returns None."""
        cal = _noop_calendar()
        limited_prices = {date(2025, 7, 21): PriceSnapshot(close=10.0, csi300_close=4000.0)}
        loader = PriceSeriesOutcomeLoader(
            calendar=cal,
            price_fetcher=limited_prices.get,
        )
        outcome = loader.load(date(2025, 7, 21))
        for w in outcome.windows:
            assert w.data_gap is not None, f"Horizon {w.horizon} should have data_gap"
            assert w.asset_return is None
            assert w.excess_return is None

    def test_entry_price_unavailable(self):
        """If entry price is missing, all windows must report data_gap."""
        loader = PriceSeriesOutcomeLoader(
            price_fetcher=lambda d: None,
        )
        outcome = loader.load(date(2025, 7, 21))
        assert outcome.entry_price == 0.0
        for w in outcome.windows:
            assert w.data_gap == "entry_price_unavailable"


class TestNoLookahead:
    def test_future_horizon_marked_not_yet_matured(self):
        """If a horizon target date is >= today (exchange date), mark not_yet_matured."""
        cal = _noop_calendar()
        prices = {
            date(2025, 7, 21): PriceSnapshot(close=10.0, csi300_close=4000.0),
        }
        loader = PriceSeriesOutcomeLoader(
            calendar=cal,
            price_fetcher=prices.get,
        )
        now = datetime(2025, 7, 21, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        outcome = loader.load(date(2025, 7, 21), now=now)
        for w in outcome.windows:
            assert w.data_gap == "not_yet_matured", (
                f"Horizon {w.horizon} should be not_yet_matured when target >= today"
            )
            assert w.asset_return is None
            assert w.excess_return is None


def _noop_calendar():
    """Minimal stub that advances one day at a time (no holiday skipping)."""
    from src.investment_research.operations.trading_calendar import TradingCalendar
    return TradingCalendar()
