from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)


class TestHistoricalMarketPanel:
    def test_create_valid(self) -> None:
        p = HistoricalMarketPanel(
            date=date(2026, 7, 1),
            market_price=15.5,
            market_change_pct=-2.1,
            ma_5=15.0,
            ma_10=14.8,
            ma_20=14.5,
            volume=1_000_000,
            turnover=0.05,
            amplitude=3.2,
        )
        assert p.date == date(2026, 7, 1)
        assert p.market_price == 15.5
        assert p.market_change_pct == -2.1
        assert p.ma_5 == 15.0
        assert p.ma_10 == 14.8
        assert p.ma_20 == 14.5
        assert p.volume == 1_000_000
        assert p.turnover == 0.05
        assert p.amplitude == 3.2

    def test_frozen(self) -> None:
        p = HistoricalMarketPanel(
            date=date(2026, 7, 1),
            market_price=10.0,
            market_change_pct=0.0,
            ma_5=10.0,
            ma_10=10.0,
            ma_20=10.0,
            volume=0,
            turnover=0.0,
            amplitude=0.0,
        )
        with pytest.raises(AttributeError):
            p.market_price = 20.0

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValueError, match="volume must be non-negative"):
            HistoricalMarketPanel(
                date=date(2026, 7, 1),
                market_price=10.0,
                market_change_pct=0.0,
                ma_5=10.0,
                ma_10=10.0,
                ma_20=10.0,
                volume=-1,
                turnover=0.0,
                amplitude=0.0,
            )

    def test_negative_turnover_raises(self) -> None:
        with pytest.raises(ValueError, match="turnover must be non-negative"):
            HistoricalMarketPanel(
                date=date(2026, 7, 1),
                market_price=10.0,
                market_change_pct=0.0,
                ma_5=10.0,
                ma_10=10.0,
                ma_20=10.0,
                volume=0,
                turnover=-0.01,
                amplitude=0.0,
            )

    def test_negative_amplitude_raises(self) -> None:
        with pytest.raises(ValueError, match="amplitude must be non-negative"):
            HistoricalMarketPanel(
                date=date(2026, 7, 1),
                market_price=10.0,
                market_change_pct=0.0,
                ma_5=10.0,
                ma_10=10.0,
                ma_20=10.0,
                volume=0,
                turnover=0.0,
                amplitude=-0.5,
            )

    def test_zero_volume_allowed(self) -> None:
        p = HistoricalMarketPanel(
            date=date(2026, 7, 1),
            market_price=10.0,
            market_change_pct=0.0,
            ma_5=10.0,
            ma_10=10.0,
            ma_20=10.0,
            volume=0,
            turnover=0.0,
            amplitude=0.0,
        )
        assert p.volume == 0
