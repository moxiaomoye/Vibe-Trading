"""Centralized, date-explicit A-share post-close data boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import re
from typing import Any, Callable, Mapping, Protocol

import pandas as pd


@dataclass(frozen=True)
class UpstreamError:
    operation: str
    error_type: str
    message: str
    attempts: int
    retryable: bool


@dataclass(frozen=True)
class ProviderDataGap:
    field: str
    reason: str
    source_date: date | None = None
    availability_date: date | None = None


@dataclass(frozen=True)
class SymbolMetadata:
    symbol: str
    name: str
    source_date: date
    availability_date: date


@dataclass(frozen=True)
class SectorMembership:
    symbol: str
    sector: str
    source_date: date
    availability_date: date
    valid_through: date | None = None


@dataclass(frozen=True)
class PostCloseData:
    source: str
    source_date: date
    availability_date: date
    retrieved_at: datetime
    spot_df: pd.DataFrame
    benchmark_returns: Mapping[str, float] = field(default_factory=dict)
    limit_up_symbols: frozenset[str] = field(default_factory=frozenset)
    limit_down_symbols: frozenset[str] = field(default_factory=frozenset)
    sector_returns: Mapping[str, float] = field(default_factory=dict)
    sector_memberships: tuple[SectorMembership, ...] = ()
    symbol_metadata: tuple[SymbolMetadata, ...] = ()
    errors: tuple[UpstreamError, ...] = ()
    data_gaps: tuple[ProviderDataGap, ...] = ()

    def __post_init__(self) -> None:
        if self.availability_date < self.source_date:
            raise ValueError("availability_date cannot precede source_date")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")

    def to_panel_data(self, benchmark: str = "000300.SH") -> dict[str, Any]:
        return {
            "spot_df": self.spot_df.copy(),
            "limit_up_symbols": set(self.limit_up_symbols),
            "limit_down_symbols": set(self.limit_down_symbols),
            "data_date": self.source_date,
            "availability_date": self.availability_date,
            "now": self.retrieved_at,
            "market_change_pct": self.benchmark_returns.get(benchmark),
            "sector_map": {},
            "sector_memberships": list(self.sector_memberships),
            "sector_returns": dict(self.sector_returns),
            "sector_return_date": self.source_date,
            "sector_return_availability_date": self.availability_date,
            "source": self.source,
            "provider_errors": list(self.errors),
            "data_gaps": list(self.data_gaps),
        }


class PostCloseProvider(Protocol):
    def load(self, *, as_of: date | None = None) -> PostCloseData: ...


class SinaSpotAdapter:
    """Current-day Sina A-share spot adapter with one bounded upstream call."""

    source = "akshare_sina"

    def __init__(
        self,
        *,
        ak_module: Any | None = None,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ak_module = ak_module
        self._today = today
        self._now = now or (lambda: datetime.now(timezone.utc))

    def load(self, *, as_of: date | None = None) -> PostCloseData:
        current_date = self._today()
        target_date = as_of or current_date
        retrieved_at = self._now()
        if target_date != current_date:
            return PostCloseData(
                source=self.source,
                source_date=target_date,
                availability_date=current_date,
                retrieved_at=retrieved_at,
                spot_df=pd.DataFrame(),
                data_gaps=(
                    ProviderDataGap(
                        "all_a_spot",
                        "Sina spot endpoint cannot serve point-in-time historical panels",
                        target_date,
                        current_date,
                    ),
                ),
            )

        try:
            ak = self._ak()
        except Exception as exc:
            return _failed_sina_spot(
                target_date,
                retrieved_at,
                "provider_initialization",
                exc,
                retryable=False,
            )

        try:
            raw = ak.stock_zh_a_spot()
        except Exception as exc:
            return _failed_sina_spot(
                target_date,
                retrieved_at,
                "all_a_spot_sina",
                exc,
                retryable=True,
            )

        spot, normalization_gaps = _normalize_sina_spot(raw, target_date)
        gaps = list(normalization_gaps)
        if spot.empty:
            gaps.append(
                ProviderDataGap(
                    "all_a_spot",
                    "Sina spot response is empty or lacks usable symbols",
                    target_date,
                    target_date,
                )
            )
        metadata = _normalize_symbol_metadata(spot, target_date)
        if not metadata:
            gaps.append(
                ProviderDataGap(
                    "symbol_metadata",
                    "symbol metadata unavailable",
                    target_date,
                    target_date,
                )
            )
        return PostCloseData(
            source=self.source,
            source_date=target_date,
            availability_date=target_date,
            retrieved_at=retrieved_at,
            spot_df=spot,
            symbol_metadata=metadata,
            data_gaps=tuple(gaps),
        )

    def _ak(self) -> Any:
        if self._ak_module is not None:
            return self._ak_module
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare is unavailable") from exc
        return ak


class AksharePostCloseProvider:
    """Best-effort AKShare adapter with bounded retries and explicit gaps.

    AKShare is imported lazily. Its spot endpoint is current-day only, so a
    historical ``as_of`` request is rejected instead of relabeling current data.
    """

    source = "akshare"
    benchmark = "000300.SH"

    def __init__(
        self,
        *,
        ak_module: Any | None = None,
        max_attempts: int = 2,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self._ak_module = ak_module
        self._max_attempts = max_attempts
        self._today = today
        self._now = now or (lambda: datetime.now(timezone.utc))

    def load(self, *, as_of: date | None = None) -> PostCloseData:
        current_date = self._today()
        target_date = as_of or current_date
        retrieved_at = self._now()
        if target_date != current_date:
            return PostCloseData(
                source=self.source,
                source_date=target_date,
                availability_date=current_date,
                retrieved_at=retrieved_at,
                spot_df=pd.DataFrame(),
                data_gaps=(
                    ProviderDataGap(
                        field="all_a_spot",
                        reason="AKShare spot endpoint cannot serve point-in-time historical panels",
                        source_date=target_date,
                        availability_date=current_date,
                    ),
                ),
            )

        errors: list[UpstreamError] = []
        gaps: list[ProviderDataGap] = []
        try:
            ak = self._ak()
        except Exception as exc:
            return PostCloseData(
                source=self.source,
                source_date=target_date,
                availability_date=target_date,
                retrieved_at=retrieved_at,
                spot_df=pd.DataFrame(),
                errors=(
                    UpstreamError(
                        operation="provider_initialization",
                        error_type=type(exc).__name__,
                        message=str(exc)[:200],
                        attempts=1,
                        retryable=False,
                    ),
                ),
                data_gaps=(
                    ProviderDataGap(
                        "all_a_spot",
                        "provider initialization failed",
                        target_date,
                        target_date,
                    ),
                ),
            )

        spot = self._call(ak.stock_zh_a_spot_em, "all_a_spot", errors)
        if spot is None:
            spot = pd.DataFrame()
            gaps.append(ProviderDataGap("all_a_spot", "upstream request failed", target_date, target_date))

        benchmark_returns: dict[str, float] = {}
        index_frame = self._call(
            lambda: ak.stock_zh_index_daily_em(symbol="sh000300"),
            "benchmark_daily",
            errors,
        )
        if index_frame is not None:
            benchmark_return = _last_daily_return(index_frame, target_date)
            if benchmark_return is not None:
                benchmark_returns[self.benchmark] = benchmark_return
            else:
                gaps.append(ProviderDataGap("benchmark_return", "missing or date-misaligned close data", target_date, target_date))
        else:
            gaps.append(ProviderDataGap("benchmark_return", "upstream request failed", target_date, target_date))

        limit_up = self._load_symbol_pool(
            lambda: ak.stock_zt_pool_em(date=target_date.strftime("%Y%m%d")),
            "limit_up_pool",
            errors,
            gaps,
            target_date,
        )
        limit_down = self._load_symbol_pool(
            lambda: ak.stock_zt_pool_dtgc_em(date=target_date.strftime("%Y%m%d")),
            "limit_down_pool",
            errors,
            gaps,
            target_date,
        )

        sector_returns: dict[str, float] = {}
        sector_frame = self._call(ak.stock_board_industry_name_em, "sector_returns", errors)
        if sector_frame is not None:
            sector_returns = _normalize_sector_returns(sector_frame)
        if not sector_returns:
            gaps.append(ProviderDataGap("sector_returns", "sector returns unavailable", target_date, target_date))
        gaps.append(ProviderDataGap("sector_memberships", "symbol-to-sector membership unavailable from bulk endpoint", target_date, target_date))

        metadata = _normalize_symbol_metadata(spot, target_date)
        if not metadata:
            gaps.append(ProviderDataGap("symbol_metadata", "symbol metadata unavailable", target_date, target_date))

        return PostCloseData(
            source=self.source,
            source_date=target_date,
            availability_date=target_date,
            retrieved_at=retrieved_at,
            spot_df=spot,
            benchmark_returns=benchmark_returns,
            limit_up_symbols=frozenset(limit_up),
            limit_down_symbols=frozenset(limit_down),
            sector_returns=sector_returns,
            sector_memberships=(),
            symbol_metadata=metadata,
            errors=tuple(errors),
            data_gaps=tuple(gaps),
        )

    def _ak(self) -> Any:
        if self._ak_module is not None:
            return self._ak_module
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare is unavailable") from exc
        return ak

    def _call(
        self,
        operation: Callable[[], Any],
        name: str,
        errors: list[UpstreamError],
    ) -> Any | None:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return operation()
            except Exception as exc:
                if attempt == self._max_attempts:
                    errors.append(
                        UpstreamError(
                            operation=name,
                            error_type=type(exc).__name__,
                            message=str(exc)[:200],
                            attempts=attempt,
                            retryable=True,
                        )
                    )
        return None

    def _load_symbol_pool(
        self,
        operation: Callable[[], Any],
        name: str,
        errors: list[UpstreamError],
        gaps: list[ProviderDataGap],
        target_date: date,
    ) -> set[str]:
        frame = self._call(operation, name, errors)
        if frame is None:
            gaps.append(ProviderDataGap(name, "upstream request failed", target_date, target_date))
            return set()
        symbols = _extract_symbols(frame)
        if not symbols:
            gaps.append(ProviderDataGap(name, "pool empty or code column missing", target_date, target_date))
        return symbols


def _last_daily_return(frame: Any, target_date: date) -> float | None:
    if frame is None or len(frame) < 2 or "close" not in frame:
        return None
    latest_date = None
    for column in ("date", "日期"):
        if column in frame:
            latest_date = pd.to_datetime(frame[column].iloc[-1]).date()
            break
    if latest_date is not None and latest_date != target_date:
        return None
    closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
    if len(closes) < 2 or float(closes.iloc[-2]) <= 0:
        return None
    return round(float(closes.iloc[-1]) / float(closes.iloc[-2]) - 1.0, 8)


def _extract_symbols(frame: Any) -> set[str]:
    if frame is None:
        return set()
    for column in ("代码", "股票代码", "symbol"):
        if column in frame:
            return {str(value).strip().zfill(6) for value in frame[column] if str(value).strip()}
    return set()


def _normalize_sector_returns(frame: Any) -> dict[str, float]:
    if frame is None or "板块名称" not in frame or "涨跌幅" not in frame:
        return {}
    result: dict[str, float] = {}
    for _, row in frame.iterrows():
        try:
            result[str(row["板块名称"]).strip()] = float(row["涨跌幅"]) / 100.0
        except (TypeError, ValueError):
            continue
    return result


def _normalize_symbol_metadata(frame: Any, source_date: date) -> tuple[SymbolMetadata, ...]:
    if frame is None or "代码" not in frame:
        return ()
    names = frame["名称"] if "名称" in frame else [""] * len(frame)
    return tuple(
        SymbolMetadata(
            symbol=str(symbol).strip().zfill(6),
            name=str(name),
            source_date=source_date,
            availability_date=source_date,
        )
        for symbol, name in zip(frame["代码"], names)
    )


def _failed_sina_spot(
    target_date: date,
    retrieved_at: datetime,
    operation: str,
    exc: Exception,
    *,
    retryable: bool,
) -> PostCloseData:
    return PostCloseData(
        source=SinaSpotAdapter.source,
        source_date=target_date,
        availability_date=target_date,
        retrieved_at=retrieved_at,
        spot_df=pd.DataFrame(),
        errors=(
            UpstreamError(
                operation=operation,
                error_type=type(exc).__name__,
                message=str(exc)[:200],
                attempts=1,
                retryable=retryable,
            ),
        ),
        data_gaps=(
            ProviderDataGap(
                "all_a_spot",
                "Sina spot request failed",
                target_date,
                target_date,
            ),
        ),
    )


def _normalize_sina_spot(
    frame: Any,
    source_date: date,
) -> tuple[pd.DataFrame, tuple[ProviderDataGap, ...]]:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(), ()
    if "代码" not in frame:
        return (
            pd.DataFrame(),
            (
                ProviderDataGap(
                    "all_a_spot",
                    "Sina spot response is missing code column",
                    source_date,
                    source_date,
                ),
            ),
        )

    normalized = frame.copy()
    normalized["代码"] = normalized["代码"].map(_normalize_a_share_code)
    normalized = normalized[normalized["代码"].notna()].copy()
    for column in ("名称", "最新价", "涨跌幅", "昨收"):
        if column not in normalized:
            normalized[column] = pd.NA
    if "成交量" in normalized:
        normalized["成交量"] = pd.to_numeric(
            normalized["成交量"], errors="coerce"
        ) / 100.0
    return normalized.reset_index(drop=True), ()


def _normalize_a_share_code(value: Any) -> str | None:
    text = str(value).strip().lower()
    match = re.fullmatch(r"(?:sh|sz|bj)?(\d{6})(?:\.(?:sh|sz|bj))?", text)
    return match.group(1) if match else None
