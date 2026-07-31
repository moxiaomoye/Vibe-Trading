from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..models.historical_market_panel import HistoricalMarketPanel
from .trade_date import (
    DateResolution,
    TradeDateResolutionError,
    TradeDateResolver,
)


@dataclass(frozen=True, slots=True)
class LoadedMarketData:
    panel: HistoricalMarketPanel
    raw_panel_data: dict[str, Any]


class HistoricalMarketLoader:
    def __init__(
        self,
        resolver: TradeDateResolver | None = None,
        *,
        use_fallback: bool = True,
    ) -> None:
        self.resolver = resolver or TradeDateResolver()
        self.use_fallback = use_fallback

    def load(
        self,
        requested_date: date,
        *,
        now: datetime | None = None,
    ) -> LoadedMarketData | None:
        tz = ZoneInfo(self.resolver.schedule.timezone_name)
        local_now = now if now is not None else datetime.now(tz)
        try:
            resolved = self.resolver.resolve(
                now=local_now,
                date_mode="selected",
                requested_date=requested_date,
            )
        except TradeDateResolutionError:
            return None

        if resolved.date_resolution is DateResolution.HISTORICAL_DATA_UNAVAILABLE:
            return None

        effective_date = resolved.effective_trade_date
        panel_data = self._fetch_panel_data(effective_date, local_now)
        if panel_data is None:
            if self.use_fallback:
                panel_data = self._fallback_panel(effective_date)
            if panel_data is None:
                return None

        panel = self._build_panel(effective_date, panel_data)
        return LoadedMarketData(panel, panel_data)

    def _fetch_panel_data(
        self, trade_date: date, now: datetime
    ) -> dict[str, Any] | None:
        raise NotImplementedError("subclasses must implement _fetch_panel_data")

    def _fallback_panel(self, trade_date: date) -> dict[str, Any] | None:
        return None

    def _build_panel(
        self, trade_date: date, panel_data: dict[str, Any]
    ) -> HistoricalMarketPanel:
        return HistoricalMarketPanel(
            date=trade_date,
            market_price=panel_data.get("market_price", 0.0),
            market_change_pct=panel_data.get("market_change_pct", 0.0),
            ma_5=panel_data.get("ma_5", 0.0),
            ma_10=panel_data.get("ma_10", 0.0),
            ma_20=panel_data.get("ma_20", 0.0),
            volume=panel_data.get("volume", 0),
            turnover=panel_data.get("turnover", 0.0),
            amplitude=panel_data.get("amplitude", 0.0),
        )


class FixtureHistoricalMarketLoader(HistoricalMarketLoader):
    def __init__(
        self,
        fixture_panels: dict[date, dict[str, Any]],
        resolver: TradeDateResolver | None = None,
    ) -> None:
        super().__init__(resolver)
        self.fixture_panels = fixture_panels

    def _fetch_panel_data(
        self, trade_date: date, now: datetime
    ) -> dict[str, Any] | None:
        return self.fixture_panels.get(trade_date)
