from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..models.historical_market_panel import HistoricalMarketPanel
from .market_loader import HistoricalMarketLoader, LoadedMarketData


@dataclass(frozen=True, slots=True)
class HistoricalShadowResult:
    trade_date: date
    panel: HistoricalMarketPanel
    raw_panel_data: dict[str, Any]
    data_available: bool
    data_gaps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalShadowSummary:
    evaluated_dates: tuple[date, ...]
    results: tuple[HistoricalShadowResult, ...]
    available_count: int
    unavailable_count: int
    total_count: int
    last_evaluated: datetime


class HistoricalShadowRunner:
    def __init__(
        self,
        loader: HistoricalMarketLoader,
    ) -> None:
        self.loader = loader

    def run_for_date(
        self,
        trade_date: date,
        *,
        now: datetime | None = None,
    ) -> HistoricalShadowResult:
        loaded = self.loader.load(trade_date, now=now)
        if loaded is None:
            return HistoricalShadowResult(
                trade_date=trade_date,
                panel=HistoricalMarketPanel(
                    date=trade_date,
                    market_price=0.0,
                    market_change_pct=0.0,
                    ma_5=0.0,
                    ma_10=0.0,
                    ma_20=0.0,
                    volume=0,
                    turnover=0.0,
                    amplitude=0.0,
                ),
                raw_panel_data={},
                data_available=False,
                data_gaps=("historical_data_unavailable",),
            )
        return HistoricalShadowResult(
            trade_date=trade_date,
            panel=loaded.panel,
            raw_panel_data=loaded.raw_panel_data,
            data_available=True,
        )

    def run_for_dates(
        self,
        trade_dates: tuple[date, ...],
        *,
        now: datetime | None = None,
    ) -> HistoricalShadowSummary:
        results: list[HistoricalShadowResult] = []
        for d in trade_dates:
            results.append(self.run_for_date(d, now=now))
        available = sum(1 for r in results if r.data_available)
        unavailable = len(results) - available
        return HistoricalShadowSummary(
            evaluated_dates=trade_dates,
            results=tuple(results),
            available_count=available,
            unavailable_count=unavailable,
            total_count=len(trade_dates),
            last_evaluated=datetime.now(),
        )
