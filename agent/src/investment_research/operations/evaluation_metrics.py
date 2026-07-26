from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ...investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from .outcome_loader import (
    DEFAULT_HORIZONS,
    HistoricalEvaluationOutcome,
    WindowOutcome,
)


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    horizon: int
    asset_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    maximum_drawdown: float | None
    hit: bool | None
    data_gap: str | None


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    evaluation_date: date
    entry_price: float
    horizons: tuple[HorizonMetrics, ...]
    hit_rate: float | None
    false_positive_rate: float | None
    false_negative_rate: float | None
    avg_excess_return: float | None
    avg_max_drawdown: float | None


class MetricsCalculator:
    def evaluate(
        self,
        entry_panel: HistoricalMarketPanel,
        outcome: HistoricalEvaluationOutcome,
        *,
        positive_threshold: float = 0.0,
    ) -> EvaluationMetrics:
        if entry_panel.date != outcome.evaluation_date:
            raise ValueError(
                f"entry date mismatch: panel={entry_panel.date} outcome={outcome.evaluation_date}"
            )

        horizon_metrics_list: list[HorizonMetrics] = []
        hit_count = 0
        total_with_data = 0
        fp_count = 0
        fn_count = 0

        for window in outcome.windows:
            if window.data_gap is not None:
                horizon_metrics_list.append(
                    HorizonMetrics(
                        horizon=window.horizon,
                        asset_return=None,
                        benchmark_return=None,
                        excess_return=None,
                        maximum_drawdown=None,
                        hit=None,
                        data_gap=window.data_gap,
                    )
                )
                continue

            hit = None
            if window.excess_return is not None:
                hit = window.excess_return >= positive_threshold
                total_with_data += 1
                if hit:
                    hit_count += 1
                if not hit:
                    fp_count += 1

            horizon_metrics_list.append(
                HorizonMetrics(
                    horizon=window.horizon,
                    asset_return=window.asset_return,
                    benchmark_return=window.benchmark_return,
                    excess_return=window.excess_return,
                    maximum_drawdown=window.maximum_drawdown,
                    hit=hit,
                    data_gap=None,
                )
            )

        hit_rate = hit_count / total_with_data if total_with_data > 0 else None
        fp_rate = fp_count / total_with_data if total_with_data > 0 else None
        fn_rate = None

        returns_with_data = [
            h.excess_return for h in horizon_metrics_list
            if h.excess_return is not None
        ]
        drawdowns_with_data = [
            h.maximum_drawdown for h in horizon_metrics_list
            if h.maximum_drawdown is not None
        ]
        avg_excess = (
            sum(returns_with_data) / len(returns_with_data)
            if returns_with_data
            else None
        )
        avg_drawdown = (
            sum(drawdowns_with_data) / len(drawdowns_with_data)
            if drawdowns_with_data
            else None
        )

        return EvaluationMetrics(
            evaluation_date=outcome.evaluation_date,
            entry_price=outcome.entry_price,
            horizons=tuple(horizon_metrics_list),
            hit_rate=hit_rate,
            false_positive_rate=fp_rate,
            false_negative_rate=fn_rate,
            avg_excess_return=avg_excess,
            avg_max_drawdown=avg_drawdown,
        )
