"""Authenticated, read-only HTTP adapter for historical outcome evaluation."""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from src.investment_research.models.historical_market_panel import HistoricalMarketPanel
from src.investment_research.operations.evaluation_metrics import (
    EvaluationMetrics,
    MetricsCalculator,
)
from src.investment_research.operations.historical_price_provider import (
    HistoricalPriceProvider,
    HistoricalPriceProviderError,
)
from src.investment_research.operations.outcome_loader import OutcomeLoader
from src.investment_research.operations.price_series_outcome_loader import (
    PriceSeriesOutcomeLoader,
    PriceSnapshot,
)
from src.investment_research.operations.review_labeling import ReviewLabel, label_outcome


AuthDep = Callable[..., Awaitable[Any] | Any]
SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_PRICE_ROWS = 2_000
MIN_T20_CALENDAR_DAYS = 20
_provider_factory: Callable[[], HistoricalPriceProvider] = HistoricalPriceProvider


class HistoricalAutomaticEvaluationRequest(BaseModel):
    stock_code: str = Field(pattern=r"^\d{6}$")
    evaluation_date: date
    horizon: Literal[20] = 20

    @field_validator("evaluation_date")
    @classmethod
    def reject_future_date(cls, value: date) -> date:
        if value > datetime.now(SHANGHAI).date():
            raise ValueError("evaluation_date must not be in the future")
        return value


class HistoricalPriceRow(BaseModel):
    trade_date: date
    asset_close: float = Field(gt=0)
    benchmark_close: float = Field(gt=0)


class HistoricalManualEvaluationRequest(BaseModel):
    schema_version: Literal["1.0"]
    input_mode: Literal["manual", "sample"] = "manual"
    data_source: str = Field(min_length=1, max_length=128)
    availability_time: datetime
    evaluation_date: date
    stock_code: str = Field(pattern=r"^\d{6}$")
    benchmark_code: str = Field(default="000300", pattern=r"^\d{6}$")
    adjustment: Literal["qfq"] = "qfq"
    prices: list[HistoricalPriceRow] = Field(min_length=1, max_length=MAX_PRICE_ROWS)

    @field_validator("availability_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("availability_time must include a timezone offset")
        return value

    @field_validator("data_source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("data_source must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_point_in_time_contract(self) -> "HistoricalManualEvaluationRequest":
        now = datetime.now(SHANGHAI)
        today = now.date()
        if self.availability_time > now:
            raise ValueError("availability_time must not be in the future")
        if self.evaluation_date > today:
            raise ValueError("evaluation_date must not be in the future")

        dates = [row.trade_date for row in self.prices]
        if len(dates) != len(set(dates)):
            raise ValueError("price rows must have unique trade_date values")
        if dates != sorted(dates):
            raise ValueError("price rows must be sorted by trade_date")
        if any(day > today for day in dates):
            raise ValueError("price rows must not contain future dates")
        if self.evaluation_date not in set(dates):
            raise ValueError("evaluation_date must be present in price rows")
        if self.availability_time.astimezone(SHANGHAI).date() < dates[-1]:
            raise ValueError(
                "availability_time must not precede the latest imported price"
            )
        return self


class ImportedTradingCalendar:
    """Calendar constrained to the validated dates supplied by the caller."""

    def __init__(self, trading_dates: list[date]) -> None:
        self._dates = tuple(sorted(set(trading_dates)))
        self._positions = {day: index for index, day in enumerate(self._dates)}

    def next_trading_day(self, start: date) -> date | None:
        index = bisect_right(self._dates, start)
        return self._dates[index] if index < len(self._dates) else None

    def nth_trading_day_forward(self, start: date, n: int) -> date | None:
        position = self._positions.get(start)
        if position is None or n < 0:
            return None
        target = position + n
        return self._dates[target] if target < len(self._dates) else None


def register_historical_evaluation_routes(app: FastAPI, require_auth: AuthDep) -> None:
    dependencies = [Depends(require_auth)]

    @app.get(
        "/investment-research/historical-evaluation/status",
        dependencies=dependencies,
    )
    def historical_evaluation_status() -> dict[str, Any]:
        capability = _provider_factory().capability_status()
        return {
            "enabled": True,
            "read_only": True,
            "supported_horizons": [20],
            "provider_supported": True,
            "manual_import_supported": True,
            "manual_schema_version": "1.0",
            "adjustment": "qfq",
            "automatic_fetch": capability,
        }

    @app.post(
        "/investment-research/historical-evaluation/evaluate-auto",
        dependencies=dependencies,
    )
    def evaluate_automatic_prices(payload: HistoricalAutomaticEvaluationRequest):
        latest_possible_date = (
            datetime.now(SHANGHAI).date()
            - timedelta(days=MIN_T20_CALENDAR_DAYS)
        )
        if payload.evaluation_date > latest_possible_date:
            return _error(
                422,
                "date_not_matured",
                "evaluation_date has not reached T+20 yet",
                reasons=[
                    "T+20 requires at least 20 calendar days after the "
                    "evaluation date; weekends and market holidays can require "
                    "a still earlier date"
                ],
            )
        try:
            series = _provider_factory().fetch(
                payload.stock_code,
                payload.evaluation_date,
                horizon=payload.horizon,
            )
            price_rows = [
                HistoricalPriceRow(
                    trade_date=index.date(),
                    asset_close=float(row.asset_close),
                    benchmark_close=float(row.benchmark_close),
                )
                for index, row in series.prices.iterrows()
            ]
            outcome, calendar, snapshots, coverage = _evaluate_price_rows(
                series.evaluation_date,
                price_rows,
            )
            result = _build_response(
                series.evaluation_date,
                outcome,
                stock_code=payload.stock_code,
                benchmark_code=series.benchmark_code,
                data_source="component_providers",
                input_mode="provider",
                adjustment=series.adjustment,
                calendar=calendar,
                snapshots=snapshots,
                coverage=coverage,
                component_sources=series.component_sources,
                provider_attempts=[
                    attempt.to_dict() for attempt in series.attempts
                ],
            )
            result.update(
                {
                    "requested_evaluation_date": (
                        series.requested_evaluation_date
                        or payload.evaluation_date
                    ).isoformat(),
                    "effective_evaluation_date": (
                        series.evaluation_date.isoformat()
                    ),
                    "date_resolution": series.date_resolution,
                }
            )
            if series.date_resolution != "exact_trading_day":
                result["warnings"].append(
                    "the requested date was not a common trading day; "
                    "the previous common trading day was used"
                )
            result["horizons"] = [
                row
                for row in result["horizons"]
                if row["horizon"] == payload.horizon
            ]
            return result
        except HistoricalPriceProviderError as exc:
            return _error(
                503,
                exc.code,
                str(exc),
                reasons=[
                    _attempt_reason(attempt.to_dict())
                    for attempt in exc.attempts
                    if attempt.status != "success"
                ],
                provider_attempts=[
                    attempt.to_dict() for attempt in exc.attempts
                ],
            )
        except ValueError as exc:
            return _error(422, "invalid_request", str(exc))
        except Exception:
            return _error(
                503,
                "provider_unavailable",
                "automatic historical price acquisition failed",
            )

    @app.post(
        "/investment-research/historical-evaluation/evaluate-manual",
        dependencies=dependencies,
    )
    def evaluate_manual_prices(payload: HistoricalManualEvaluationRequest):
        outcome, calendar, snapshots, coverage = _evaluate_price_rows(
            payload.evaluation_date,
            payload.prices,
        )
        return _build_response(
            payload.evaluation_date,
            outcome,
            stock_code=payload.stock_code,
            benchmark_code=payload.benchmark_code,
            data_source=payload.data_source,
            input_mode=payload.input_mode,
            adjustment=payload.adjustment,
            calendar=calendar,
            snapshots=snapshots,
            coverage=coverage,
        )


def _evaluate_price_rows(
    evaluation_date: date,
    rows: list[HistoricalPriceRow],
) -> tuple[
    Any,
    ImportedTradingCalendar,
    dict[date, PriceSnapshot],
    dict[str, Any],
]:
    dates = [row.trade_date for row in rows]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("price rows must be sorted and have unique trade dates")
    if evaluation_date not in set(dates):
        raise ValueError("evaluation_date must be present in price rows")
    snapshots = {
        row.trade_date: PriceSnapshot(
            close=row.asset_close,
            csi300_close=row.benchmark_close,
        )
        for row in rows
    }
    calendar = ImportedTradingCalendar(dates)
    loader: OutcomeLoader = PriceSeriesOutcomeLoader(
        calendar=calendar,  # type: ignore[arg-type]
        price_fetcher=snapshots.get,
    )
    outcome = loader.load(evaluation_date)
    coverage = {
        "first_trade_date": dates[0].isoformat(),
        "last_trade_date": dates[-1].isoformat(),
        "row_count": len(rows),
    }
    return outcome, calendar, snapshots, coverage


def _build_response(
    evaluation_date: date,
    outcome: Any,
    *,
    stock_code: str,
    benchmark_code: str,
    data_source: str,
    input_mode: str,
    adjustment: str,
    calendar: ImportedTradingCalendar | None = None,
    snapshots: dict[date, PriceSnapshot] | None = None,
    coverage: dict[str, Any] | None = None,
    component_sources: dict[str, str] | None = None,
    provider_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metrics = MetricsCalculator().evaluate(_empty_panel(evaluation_date), outcome)
    labels = label_outcome(outcome)
    result = _serialize_evaluation(evaluation_date, metrics, labels)
    result.update(
        {
            "stock_code": stock_code,
            "benchmark_code": benchmark_code,
            "data_source": data_source,
            "input_mode": input_mode,
            "adjustment": adjustment,
            "capability": (
                "sample_contract"
                if input_mode == "sample"
                else "validated_manual_price_series"
                if input_mode == "manual"
                else "provider"
            ),
            "coverage": coverage,
            "component_sources": component_sources or {},
            "provider_attempts": provider_attempts or [],
            "verification_status": (
                "provider_acquired_unverified"
                if input_mode == "provider"
                else "caller_supplied"
            ),
            "warnings": (
                ["sample data is synthetic and does not validate investment performance"]
                if input_mode == "sample"
                else []
            ),
        }
    )
    if calendar is not None and snapshots is not None:
        for horizon in result["horizons"]:
            target_date = calendar.nth_trading_day_forward(
                evaluation_date, horizon["horizon"]
            )
            target = snapshots.get(target_date) if target_date else None
            horizon.update(
                {
                    "entry_date": evaluation_date.isoformat(),
                    "target_trading_date": (
                        target_date.isoformat() if target_date else None
                    ),
                    "target_price": target.close if target else None,
                    "benchmark_entry_price": snapshots[evaluation_date].csi300_close,
                    "benchmark_target_price": target.csi300_close if target else None,
                    "calculation_status": (
                        "complete" if horizon["data_gap"] is None else "data_gap"
                    ),
                }
            )
    return result


def _empty_panel(evaluation_date: date) -> HistoricalMarketPanel:
    return HistoricalMarketPanel(
        date=evaluation_date,
        market_price=0.0,
        market_change_pct=0.0,
        ma_5=0.0,
        ma_10=0.0,
        ma_20=0.0,
        volume=0,
        turnover=0.0,
        amplitude=0.0,
    )


def _serialize_evaluation(
    evaluation_date: date,
    metrics: EvaluationMetrics,
    labels: dict[int, ReviewLabel],
) -> dict[str, Any]:
    return {
        "evaluation_date": evaluation_date.isoformat(),
        "entry_price": metrics.entry_price,
        "metrics": {
            "hit_rate": metrics.hit_rate,
            "false_positive_rate": metrics.false_positive_rate,
            "false_negative_rate": metrics.false_negative_rate,
            "avg_excess_return": metrics.avg_excess_return,
            "avg_max_drawdown": metrics.avg_max_drawdown,
        },
        "horizons": [
            {
                "horizon": horizon.horizon,
                "asset_return": horizon.asset_return,
                "benchmark_return": horizon.benchmark_return,
                "excess_return": horizon.excess_return,
                "maximum_drawdown": horizon.maximum_drawdown,
                "hit": horizon.hit,
                "review_label": labels.get(horizon.horizon, "unclear"),
                "data_gap": horizon.data_gap,
            }
            for horizon in metrics.horizons
        ],
    }


def _attempt_reason(attempt: dict[str, Any]) -> str:
    provider = attempt.get("provider", "provider")
    component = attempt.get("component", "data")
    category = attempt.get("category") or "unavailable"
    message = attempt.get("message")
    suffix = f": {message}" if message else ""
    return f"{provider} ({component}) [{category}]{suffix}"


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    reasons: list[str] | None = None,
    provider_attempts: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "reasons": reasons or [],
                "provider_attempts": provider_attempts or [],
            }
        },
    )
