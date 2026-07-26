from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..models.historical_market_panel import HistoricalMarketPanel

DEFAULT_HORIZONS: tuple[int, ...] = (5, 20, 60)


@dataclass(frozen=True, slots=True)
class WindowOutcome:
    horizon: int
    asset_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    maximum_drawdown: float | None
    invalidation_triggered: bool = False
    data_gap: str | None = None


@dataclass(frozen=True, slots=True)
class HistoricalEvaluationOutcome:
    evaluation_date: date
    entry_price: float
    windows: tuple[WindowOutcome, ...] = ()


class OutcomeLoader:
    def load(
        self,
        evaluation_date: date,
        *,
        now: datetime | None = None,
    ) -> HistoricalEvaluationOutcome:
        raise NotImplementedError("subclasses must implement load")


class FixtureOutcomeLoader(OutcomeLoader):
    def __init__(
        self,
        fixture_outcomes: dict[date, dict[int, dict[str, Any]]],
    ) -> None:
        self.fixture_outcomes = fixture_outcomes

    def load(
        self,
        evaluation_date: date,
        *,
        now: datetime | None = None,
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
                    for h in DEFAULT_HORIZONS
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
            for h in DEFAULT_HORIZONS
            if h in outcomes
        )
        return HistoricalEvaluationOutcome(
            evaluation_date=evaluation_date,
            entry_price=entry_price,
            windows=windows,
        )
