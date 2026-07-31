"""Automatic historical price acquisition for read-only outcome evaluation.

This adapter deliberately reuses the existing backtest loaders and their
opt-in local cache.  It only acquires price series; validation and return
calculation remain owned by :class:`PriceSeriesOutcomeLoader`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re
from typing import Any, Callable

import pandas as pd

from backtest.loaders.base import (
    cached_loader_fetch,
    loader_cache_enabled,
    loader_cache_get,
)
from src.config.market_data_providers import get_provider_config


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    component: str
    status: str
    category: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "component": self.component,
            "status": self.status,
            "category": self.category,
            "message": self.message,
        }


@dataclass(frozen=True)
class HistoricalPriceSeries:
    stock_code: str
    benchmark_code: str
    evaluation_date: date
    adjustment: str
    prices: pd.DataFrame
    component_sources: dict[str, str]
    attempts: tuple[ProviderAttempt, ...]
    requested_evaluation_date: date | None = None
    date_resolution: str = "exact_trading_day"

    @property
    def coverage(self) -> dict[str, Any]:
        dates = list(self.prices.index.date)
        return {
            "first_trade_date": dates[0].isoformat(),
            "last_trade_date": dates[-1].isoformat(),
            "row_count": len(dates),
        }


class HistoricalPriceProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        attempts: list[ProviderAttempt],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.attempts = tuple(attempts)


class HistoricalPriceProvider:
    """Fetch a qfq A-share series and CSI 300 closes through existing loaders."""

    benchmark_code = "000300"

    def capability_status(self) -> dict[str, Any]:
        szse = get_provider_config("szse_data")
        tushare = get_provider_config("tushare")
        try:
            import akshare  # noqa: F401

            akshare_available = True
        except ImportError:
            akshare_available = False
        return {
            "automatic_fetch": True,
            "local_cache_enabled": loader_cache_enabled(),
            "providers": [
                {
                    "provider": "szse_data",
                    "configured": szse.configured,
                    "usable": False,
                    "reason": "request protocol is not implemented",
                },
                {
                    "provider": "tushare",
                    "configured": tushare.configured,
                    "usable_for_stock_qfq": False,
                    "usable_for_benchmark": tushare.configured,
                    "reason": "existing stock loader does not expose qfq adjustment",
                },
                {
                    "provider": "tencent",
                    "configured": True,
                    "usable": True,
                    "adjustment": "qfq",
                },
                {
                    "provider": "akshare",
                    "configured": akshare_available,
                    "usable": akshare_available,
                    "adjustment": "qfq",
                },
            ],
        }

    def fetch(
        self,
        stock_code: str,
        evaluation_date: date,
        *,
        horizon: int = 20,
    ) -> HistoricalPriceSeries:
        if horizon != 20:
            raise ValueError("only the T+20 horizon is supported")
        symbol = _qualify_a_share(stock_code)
        fetch_start = evaluation_date - timedelta(days=14)
        end_date = evaluation_date + timedelta(days=60)
        attempts: list[ProviderAttempt] = []

        szse = get_provider_config("szse_data")
        attempts.append(
            ProviderAttempt(
                provider="szse_data",
                component="stock_and_benchmark",
                status="skipped",
                category=(
                    "provider_not_implemented"
                    if szse.configured
                    else "not_configured"
                ),
                message=(
                    "SZSE request protocol is not implemented"
                    if szse.configured
                    else "SZSE provider credentials are not configured"
                ),
            )
        )

        stock, stock_source = self._fetch_stock(
            symbol, fetch_start, end_date, attempts
        )
        benchmark, benchmark_source = self._fetch_benchmark(
            fetch_start, end_date, attempts
        )
        if stock is None or benchmark is None:
            missing = []
            if stock is None:
                missing.append("stock")
            if benchmark is None:
                missing.append("benchmark")
            raise HistoricalPriceProviderError(
                "provider_unavailable",
                f"automatic historical data unavailable for: {', '.join(missing)}",
                attempts,
            )

        joined = pd.concat(
            [
                stock["close"].rename("asset_close"),
                benchmark["close"].rename("benchmark_close"),
            ],
            axis=1,
            join="inner",
        ).dropna()
        joined = joined.loc[
            (joined.index.date >= fetch_start)
            & (joined.index.date <= end_date)
        ]
        eligible_dates = [
            trade_date
            for trade_date in joined.index.date
            if trade_date <= evaluation_date
        ]
        if joined.empty or not eligible_dates:
            raise HistoricalPriceProviderError(
                "date_not_covered",
                "neither price series covers the selected date or an earlier "
                "common trading day",
                attempts,
            )
        effective_evaluation_date = max(eligible_dates)
        evaluation_position = list(joined.index.date).index(
            effective_evaluation_date
        )
        required_end = evaluation_position + horizon
        if required_end >= len(joined):
            raise HistoricalPriceProviderError(
                "date_not_covered",
                "the available price series does not reach T+20 trading days",
                attempts,
            )
        joined = joined.iloc[evaluation_position : required_end + 1]
        return HistoricalPriceSeries(
            stock_code=stock_code,
            benchmark_code=self.benchmark_code,
            evaluation_date=effective_evaluation_date,
            adjustment="qfq",
            prices=joined,
            component_sources={
                "stock": stock_source,
                "benchmark": benchmark_source,
            },
            attempts=tuple(attempts),
            requested_evaluation_date=evaluation_date,
            date_resolution=(
                "exact_trading_day"
                if effective_evaluation_date == evaluation_date
                else "previous_common_trading_day"
            ),
        )

    def _fetch_stock(
        self,
        symbol: str,
        start: date,
        end: date,
        attempts: list[ProviderAttempt],
    ) -> tuple[pd.DataFrame | None, str]:
        tushare = get_provider_config("tushare")
        attempts.append(
            ProviderAttempt(
                provider="tushare",
                component="stock",
                status="skipped",
                category=(
                    "adjustment_not_supported"
                    if tushare.configured
                    else "not_configured"
                ),
                message=(
                    "existing Tushare stock loader does not expose qfq prices"
                    if tushare.configured
                    else "Tushare is not configured"
                ),
            )
        )
        candidates: list[tuple[str, Callable[[], pd.DataFrame | None]]] = [
            (
                "tencent",
                lambda: self._fetch_loader_frame(
                    "tencent", symbol, start, end
                ),
            ),
            (
                "akshare",
                lambda: self._fetch_loader_frame(
                    "akshare", symbol, start, end
                ),
            ),
        ]
        return self._try_candidates("stock", candidates, attempts)

    def _fetch_benchmark(
        self,
        start: date,
        end: date,
        attempts: list[ProviderAttempt],
    ) -> tuple[pd.DataFrame | None, str]:
        candidates: list[tuple[str, Callable[[], pd.DataFrame | None]]] = []
        if get_provider_config("tushare").configured:
            candidates.append(
                (
                    "tushare",
                    lambda: self._fetch_loader_frame(
                        "tushare", "000300.SH", start, end
                    ),
                )
            )
        else:
            attempts.append(
                ProviderAttempt(
                    provider="tushare",
                    component="benchmark",
                    status="skipped",
                    category="not_configured",
                    message="Tushare is not configured",
                )
            )
        candidates.extend(
            [
                (
                    "tencent",
                    lambda: self._fetch_loader_frame(
                        "tencent", "000300.SH", start, end
                    ),
                ),
                (
                    "akshare_index_em",
                    lambda: self._fetch_akshare_benchmark(start, end),
                ),
            ]
        )
        return self._try_candidates("benchmark", candidates, attempts)

    def _try_candidates(
        self,
        component: str,
        candidates: list[tuple[str, Callable[[], pd.DataFrame | None]]],
        attempts: list[ProviderAttempt],
    ) -> tuple[pd.DataFrame | None, str]:
        for provider, fetch in candidates:
            try:
                frame = fetch()
                if frame is None or frame.empty:
                    attempts.append(
                        ProviderAttempt(
                            provider=provider,
                            component=component,
                            status="failed",
                            category="no_data",
                            message="provider returned no rows for the requested range",
                        )
                    )
                    continue
                attempts.append(
                    ProviderAttempt(
                        provider=provider,
                        component=component,
                        status="success",
                    )
                )
                actual_source = str(frame.attrs.get("vibe_data_source", provider))
                return _normalize_close_frame(frame), actual_source
            except Exception as exc:
                attempts.append(
                    ProviderAttempt(
                        provider=provider,
                        component=component,
                        status="failed",
                        category=_classify_provider_error(exc),
                        message=_safe_error_message(exc),
                    )
                )
        return None, "unavailable"

    @staticmethod
    def _fetch_loader_frame(
        source: str,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame | None:
        start_text = start.isoformat()
        end_text = end.isoformat()
        cache_fields: list[str] | None = [] if source == "tushare" else None
        cached = loader_cache_get(
            source=source,
            symbol=symbol,
            timeframe="1D",
            start_date=start_text,
            end_date=end_text,
            fields=cache_fields,
        )
        if cached is not None:
            cached.attrs["vibe_data_source"] = f"local_cache:{source}"
            return cached
        if source == "tencent":
            from backtest.loaders.tencent_loader import DataLoader

            loader = DataLoader()
            fetch = lambda: loader._fetch_one(symbol, start_text, end_text)
        elif source == "akshare":
            from backtest.loaders.akshare_loader import DataLoader

            loader = DataLoader()
            if not loader.is_available():
                raise ImportError("AKShare is not installed")
            fetch = lambda: loader._fetch_one(symbol, start_text, end_text, "1D")
        elif source == "tushare":
            from backtest.loaders.tushare import DataLoader

            loader = DataLoader()
            fetch = lambda: loader._fetch_daily_frame(
                symbol,
                start_text.replace("-", ""),
                end_text.replace("-", ""),
            )
        else:  # pragma: no cover - internal invariant
            raise ValueError(f"unsupported loader source: {source}")
        return cached_loader_fetch(
            source=source,
            symbol=symbol,
            timeframe="1D",
            start_date=start_text,
            end_date=end_text,
            fields=cache_fields,
            fetch=fetch,
        )

    @staticmethod
    def _fetch_akshare_benchmark(start: date, end: date) -> pd.DataFrame | None:
        source = "akshare_index_em"
        symbol = "000300.SH"
        start_text = start.isoformat()
        end_text = end.isoformat()
        cached = loader_cache_get(
            source=source,
            symbol=symbol,
            timeframe="1D",
            start_date=start_text,
            end_date=end_text,
            fields=None,
        )
        if cached is not None:
            cached.attrs["vibe_data_source"] = f"local_cache:{source}"
            return cached

        def fetch() -> pd.DataFrame | None:
            import akshare as ak

            frame = ak.stock_zh_index_daily_em(symbol="sh000300")
            if frame is None or frame.empty:
                return None
            normalized = _normalize_close_frame(frame)
            return normalized.loc[start_text:end_text]

        return cached_loader_fetch(
            source=source,
            symbol=symbol,
            timeframe="1D",
            start_date=start_text,
            end_date=end_text,
            fields=None,
            fetch=fetch,
        )


def _qualify_a_share(stock_code: str) -> str:
    if not re.fullmatch(r"\d{6}", stock_code):
        raise ValueError("stock_code must be a six-digit A-share code")
    if stock_code.startswith(("4", "8")):
        return f"{stock_code}.BJ"
    if stock_code.startswith(("5", "6", "9")):
        return f"{stock_code}.SH"
    return f"{stock_code}.SZ"


def _normalize_close_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if "date" in normalized.columns and not isinstance(
        normalized.index, pd.DatetimeIndex
    ):
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.set_index("date")
    normalized.index = pd.to_datetime(normalized.index, errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    normalized = normalized[~normalized.index.isna()]
    return normalized[["close"]].dropna().sort_index()


def _classify_provider_error(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, ImportError):
        return "dependency_unavailable"
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return "network"
    if any(term in text for term in ("permission", "forbidden", "积分", "权限")):
        return "permission"
    if any(term in text for term in ("rate limit", "too many", "限频")):
        return "rate_limit"
    return "provider_error"


def _safe_error_message(exc: Exception) -> str:
    text = re.sub(r"\s+", " ", str(exc)).strip()
    text = re.sub(
        r"(?i)(token|api[_-]?key|secret|authorization)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(r"\b[A-Za-z0-9_+/=-]{32,}\b", "<redacted>", text)
    return (text or exc.__class__.__name__)[:240]
