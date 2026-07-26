from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

from .outcome_loader import (
    DEFAULT_HORIZONS,
    HistoricalEvaluationOutcome,
    OutcomeLoader,
    WindowOutcome,
)
from .trading_calendar import TradingCalendar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceSnapshot:
    close: float
    csi300_close: float


class PriceSeriesOutcomeLoader(OutcomeLoader):
    def __init__(
        self,
        calendar: TradingCalendar | None = None,
        price_fetcher: Callable[[date], PriceSnapshot | None] | None = None,
        entry_price_before: date | None = None,
    ) -> None:
        self.calendar = calendar or TradingCalendar()
        self._price_fetcher = price_fetcher
        self.entry_price_before = entry_price_before

    def load(
        self,
        evaluation_date: date,
        *,
        now: datetime | None = None,
    ) -> HistoricalEvaluationOutcome:
        _now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        if _now.tzinfo is None:
            _now = _now.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        exchange_today = _now.astimezone(ZoneInfo("Asia/Shanghai")).date()

        entry_snapshot = self._fetch_price(evaluation_date)
        if entry_snapshot is None:
            return HistoricalEvaluationOutcome(
                evaluation_date=evaluation_date,
                entry_price=0.0,
                windows=tuple(
                    WindowOutcome(horizon=h, asset_return=None, benchmark_return=None,
                                  excess_return=None, maximum_drawdown=None,
                                  data_gap="entry_price_unavailable")
                    for h in DEFAULT_HORIZONS
                ),
            )

        entry_price = entry_snapshot.close
        entry_benchmark = entry_snapshot.csi300_close

        windows: list[WindowOutcome] = []
        for h in DEFAULT_HORIZONS:
            target_date = self.calendar.nth_trading_day_forward(evaluation_date, h)
            if target_date is None:
                windows.append(WindowOutcome(
                    horizon=h, asset_return=None, benchmark_return=None,
                    excess_return=None, maximum_drawdown=None,
                    data_gap="horizon_out_of_calendar_range",
                ))
                continue

            if target_date >= exchange_today:
                windows.append(WindowOutcome(
                    horizon=h, asset_return=None, benchmark_return=None,
                    excess_return=None, maximum_drawdown=None,
                    data_gap="not_yet_matured",
                ))
                continue

            horizon_snapshot = self._fetch_price(target_date)
            if horizon_snapshot is None:
                windows.append(WindowOutcome(
                    horizon=h, asset_return=None, benchmark_return=None,
                    excess_return=None, maximum_drawdown=None,
                    data_gap="price_data_missing",
                ))
                continue

            asset_return = (horizon_snapshot.close / entry_price) - 1.0 if entry_price != 0 else None
            benchmark_return = (horizon_snapshot.csi300_close / entry_benchmark) - 1.0 if entry_benchmark != 0 else None
            excess_return = (asset_return - benchmark_return) if (asset_return is not None and benchmark_return is not None) else None
            max_dd = self._compute_max_drawdown_for_horizon(evaluation_date, target_date, entry_price)

            windows.append(WindowOutcome(
                horizon=h, asset_return=asset_return,
                benchmark_return=benchmark_return,
                excess_return=excess_return,
                maximum_drawdown=max_dd,
                data_gap=None,
            ))

        return HistoricalEvaluationOutcome(
            evaluation_date=evaluation_date,
            entry_price=entry_price,
            windows=tuple(windows),
        )

    def _fetch_price(self, target_date: date) -> PriceSnapshot | None:
        if self._price_fetcher is not None:
            return self._price_fetcher(target_date)
        return None

    def _compute_max_drawdown_for_horizon(
        self, start_date: date, end_date: date, entry_price: float
    ) -> float | None:
        if self._price_fetcher is None:
            return None
        peak = entry_price
        max_dd = 0.0
        d = start_date
        while d <= end_date:
            snap = self._fetch_price(d)
            if snap is not None:
                price = snap.close
                if price > peak:
                    peak = price
                dd = (price / peak) - 1.0
                if dd < max_dd:
                    max_dd = dd
            next_d = self.calendar.next_trading_day(d)
            if next_d is None or next_d <= d:
                break
            d = next_d
        return max_dd if max_dd < 0 else None


def akshare_price_fetcher(
    symbol: str = "000001",
    index_symbol: str = "000300",
) -> Callable[[date], PriceSnapshot | None]:
    """Return a fetcher that uses AKShare to get historical prices for *symbol* and CSI 300.

    Uses forward-adjusted (前复权) prices. Returns None if the API call fails
    or no data exists for the requested date.
    """
    import pandas as pd

    _cache: dict[date, PriceSnapshot] = {}

    def _fetch(target_date: date) -> PriceSnapshot | None:
        if target_date in _cache:
            return _cache[target_date]

        try:
            import akshare as ak

            stock_df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=target_date.isoformat(),
                end_date=target_date.isoformat(),
                adjust="qfq",
            )
        except Exception:
            logger.warning("akshare stock price fetch failed for %s on %s", symbol, target_date, exc_info=True)
            return None

        if stock_df.empty:
            return None

        try:
            close = float(stock_df["收盘"].iloc[-1])
        except (KeyError, IndexError, ValueError):
            logger.warning("unexpected stock_zh_a_hist columns: %s", list(stock_df.columns))
            return None

        try:
            index_df = ak.stock_zh_index_daily_em(symbol=f"sh{index_symbol}")
            index_df = index_df[index_df["date"] == target_date.isoformat()]
            if index_df.empty:
                logger.warning("CSI 300 data missing for %s", target_date)
                csi300_close = close
            else:
                csi300_close = float(index_df["close"].iloc[-1])
        except Exception:
            logger.warning("akshare CSI 300 fetch failed for %s", target_date, exc_info=True)
            csi300_close = close

        snap = PriceSnapshot(close=close, csi300_close=csi300_close)
        _cache[target_date] = snap
        return snap

    return _fetch
