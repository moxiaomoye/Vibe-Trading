from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from src.investment_research.operations.historical_shadow_run import (
    HistoricalShadowResult,
    HistoricalShadowRunner,
    HistoricalShadowSummary,
)
from src.investment_research.operations.market_loader import (
    FixtureHistoricalMarketLoader,
)


class TestHistoricalShadowRunner:
    SHANGHAI = ZoneInfo("Asia/Shanghai")

    def make_now(self, day: int = 15, hour: int = 19) -> datetime:
        return datetime(2026, 7, day, hour, 0, tzinfo=self.SHANGHAI)

    def test_run_for_date_returns_panel(self) -> None:
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
        runner = HistoricalShadowRunner(loader)
        result = runner.run_for_date(d, now=self.make_now(15, 19))
        assert result.data_available
        assert result.trade_date == d
        assert result.panel.market_price == 15.5

    def test_run_for_date_unavailable_returns_no_data(self) -> None:
        loader = FixtureHistoricalMarketLoader({})
        runner = HistoricalShadowRunner(loader)
        result = runner.run_for_date(date(2026, 7, 15), now=self.make_now(15, 19))
        assert not result.data_available
        assert "historical_data_unavailable" in result.data_gaps

    def test_run_for_dates_summary(self) -> None:
        d1 = date(2026, 7, 15)
        d2 = date(2026, 7, 16)
        d3 = date(2026, 7, 17)
        fixtures = {
            d1: {
                "market_price": 15.0,
                "market_change_pct": 0.0,
                "ma_5": 15.0,
                "ma_10": 15.0,
                "ma_20": 15.0,
                "volume": 0,
                "turnover": 0.0,
                "amplitude": 0.0,
            },
            d3: {
                "market_price": 16.0,
                "market_change_pct": 1.0,
                "ma_5": 15.5,
                "ma_10": 15.0,
                "ma_20": 14.5,
                "volume": 500_000,
                "turnover": 0.02,
                "amplitude": 2.0,
            },
        }
        loader = FixtureHistoricalMarketLoader(fixtures)
        runner = HistoricalShadowRunner(loader)
        summary = runner.run_for_dates((d1, d2, d3), now=self.make_now(17, 19))
        assert summary.total_count == 3
        assert summary.available_count == 2
        assert summary.unavailable_count == 1
        assert len(summary.results) == 3
        assert summary.results[0].data_available
        assert not summary.results[1].data_available
        assert summary.results[2].data_available

    def test_empty_date_list(self) -> None:
        loader = FixtureHistoricalMarketLoader({})
        runner = HistoricalShadowRunner(loader)
        summary = runner.run_for_dates((), now=self.make_now(15, 19))
        assert summary.total_count == 0
        assert summary.available_count == 0
        assert summary.unavailable_count == 0
        assert len(summary.results) == 0

    def test_result_struct(self) -> None:
        d = date(2026, 7, 15)
        panel = HistoricalMarketPanel(
            date=d, market_price=10.0, market_change_pct=0.0,
            ma_5=10.0, ma_10=10.0, ma_20=10.0,
            volume=0, turnover=0.0, amplitude=0.0,
        )
        result = HistoricalShadowResult(
            trade_date=d,
            panel=panel,
            raw_panel_data={"source": "test"},
            data_available=True,
        )
        assert result.data_available
        assert result.raw_panel_data["source"] == "test"
