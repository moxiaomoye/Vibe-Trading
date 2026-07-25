from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from src.investment_research.operations.market_loader import (
    FixtureHistoricalMarketLoader,
    HistoricalMarketLoader,
    LoadedMarketData,
)
from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.operations.trade_date import TradeDateResolver


class TestHistoricalMarketLoader:
    SHANGHAI = ZoneInfo("Asia/Shanghai")

    def make_now(self, day: int = 15, hour: int = 19) -> datetime:
        return datetime(2026, 7, day, hour, 0, tzinfo=self.SHANGHAI)

    def test_loader_must_be_subclassed(self) -> None:
        loader = HistoricalMarketLoader()
        now = self.make_now(15, 19)
        with pytest.raises(NotImplementedError):
            loader.load(date(2026, 7, 15), now=now)

    def test_fixture_loader_returns_panel(self) -> None:
        d = date(2026, 7, 15)
        fixtures = {
            d: {
                "market_price": 15.5,
                "market_change_pct": -2.1,
                "ma_5": 15.0,
                "ma_10": 14.8,
                "ma_20": 14.5,
                "volume": 1_000_000,
                "turnover": 0.05,
                "amplitude": 3.2,
            }
        }
        loader = FixtureHistoricalMarketLoader(fixtures)
        now = self.make_now(15, 19)
        result = loader.load(d, now=now)
        assert result is not None
        assert isinstance(result, LoadedMarketData)
        assert isinstance(result.panel, HistoricalMarketPanel)
        assert result.panel.date == d
        assert result.panel.market_price == 15.5

    def test_fixture_loader_missing_date_returns_none(self) -> None:
        loader = FixtureHistoricalMarketLoader({})
        now = self.make_now(15, 19)
        result = loader.load(date(2026, 7, 15), now=now)
        assert result is None

    def test_fixture_loader_non_trading_day_adjusts(self) -> None:
        saturday = date(2026, 7, 18)
        friday = date(2026, 7, 17)
        fixtures = {
            friday: {
                "market_price": 14.0,
                "market_change_pct": 0.5,
                "ma_5": 13.5,
                "ma_10": 13.0,
                "ma_20": 12.5,
                "volume": 500_000,
                "turnover": 0.03,
                "amplitude": 1.5,
            }
        }
        loader = FixtureHistoricalMarketLoader(fixtures)
        now = self.make_now(20, 19)
        result = loader.load(saturday, now=now)
        assert result is not None
        assert result.panel.date == friday

    def test_future_date_returns_none(self) -> None:
        loader = FixtureHistoricalMarketLoader({})
        future = date(2030, 1, 1)
        now = self.make_now(15, 19)
        result = loader.load(future, now=now)
        assert result is None

    def test_loader_uses_custom_schedule(self) -> None:
        d = date(2026, 7, 15)
        included = frozenset([d])
        schedule = TradingDaySchedule(
            included_dates=included, run_after=time(15, 0)
        )
        resolver = TradeDateResolver(schedule)
        fixtures = {
            d: {
                "market_price": 10.0,
                "market_change_pct": 0.0,
                "ma_5": 10.0,
                "ma_10": 10.0,
                "ma_20": 10.0,
                "volume": 0,
                "turnover": 0.0,
                "amplitude": 0.0,
            }
        }
        loader = FixtureHistoricalMarketLoader(fixtures, resolver=resolver)
        now = self.make_now(15, 16)
        result = loader.load(d, now=now)
        assert result is not None
        assert result.panel.date == d
