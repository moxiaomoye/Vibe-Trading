from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ...investment_research.contracts import AssetType
from ...investment_research.operations.outcome_loader import (
    HistoricalEvaluationOutcome,
    OutcomeLoader,
    WindowOutcome,
)
from ...investment_research.operations.review_labeling import (
    ReviewLabel,
    label_window,
)


@dataclass(frozen=True, slots=True)
class ETFEvaluation:
    evaluation_date: date
    tracking_error: float | None
    nav_return: float | None
    index_return: float | None
    premium_discount: float | None
    windows: tuple[WindowOutcome, ...] = ()


class ETFOutcomeLoader(OutcomeLoader):
    def __init__(
        self,
        fixture_outcomes: dict[date, dict[int, dict[str, Any]]],
    ) -> None:
        self.fixture_outcomes = fixture_outcomes

    def load(
        self,
        evaluation_date: date,
        *,
        now: Any = None,
    ) -> HistoricalEvaluationOutcome:
        outcomes = self.fixture_outcomes.get(evaluation_date)
        if outcomes is None:
            return HistoricalEvaluationOutcome(
                evaluation_date=evaluation_date,
                entry_price=0.0,
                windows=tuple(
                    WindowOutcome(
                        horizon=h,
                        asset_return=None,
                        benchmark_return=None,
                        excess_return=None,
                        maximum_drawdown=None,
                        data_gap="not_yet_tracked",
                    )
                    for h in (5, 20, 60)
                ),
            )
        entry_price = outcomes.get("_entry_price", 0.0)
        windows = tuple(
            WindowOutcome(
                horizon=h,
                asset_return=outcomes[h].get("asset_return"),
                benchmark_return=outcomes[h].get("benchmark_return"),
                excess_return=outcomes[h].get("excess_return"),
                maximum_drawdown=outcomes[h].get("maximum_drawdown"),
                invalidation_triggered=outcomes[h].get("invalidation_triggered", False),
                data_gap=outcomes[h].get("data_gap"),
            )
            for h in (5, 20, 60)
            if h in outcomes
        )
        return HistoricalEvaluationOutcome(
            evaluation_date=evaluation_date,
            entry_price=entry_price,
            windows=windows,
        )


def compute_tracking_error(
    asset_returns: list[float],
    benchmark_returns: list[float],
) -> float | None:
    if len(asset_returns) != len(benchmark_returns) or not asset_returns:
        return None
    n = len(asset_returns)
    diffs = [a - b for a, b in zip(asset_returns, benchmark_returns)]
    mean_diff = sum(diffs) / n
    variance = sum((d - mean_diff) ** 2 for d in diffs) / n
    return variance ** 0.5


def etf_review_labels(
    outcome: HistoricalEvaluationOutcome,
    *,
    tracking_error_threshold: float = 0.02,
) -> dict[int, ReviewLabel]:
    labels: dict[int, ReviewLabel] = {}
    for window in outcome.windows:
        labels[window.horizon] = label_window(window)
    return labels
