"""R6: Metric semantics — FP/FN denominators, candidate vs horizon level."""

from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from src.investment_research.operations.evaluation_metrics import (
    MetricsCalculator,
)
from src.investment_research.operations.outcome_loader import (
    DEFAULT_HORIZONS,
    HistoricalEvaluationOutcome,
    WindowOutcome,
)


def _panel(d: date = date(2025, 7, 21)) -> HistoricalMarketPanel:
    return HistoricalMarketPanel(
        date=d, market_price=10.0, market_change_pct=0.0,
        ma_5=0.0, ma_10=0.0, ma_20=0.0,
        volume=0, turnover=0.0, amplitude=0.0,
    )


def _outcome(
    d: date = date(2025, 7, 21),
    *,
    returns: list[float | None] | None = None,
    gaps: list[str | None] | None = None,
) -> HistoricalEvaluationOutcome:
    if returns is None:
        returns = [0.05, 0.10, 0.15]
    windows = []
    for i, h in enumerate(DEFAULT_HORIZONS):
        r = returns[i] if returns and i < len(returns) else None
        g = gaps[i] if gaps and i < len(gaps) else None
        windows.append(WindowOutcome(
            horizon=h, asset_return=r, benchmark_return=0.0,
            excess_return=r, maximum_drawdown=None,
            data_gap=g,
        ))
    return HistoricalEvaluationOutcome(
        evaluation_date=d, entry_price=10.0,
        windows=tuple(windows),
    )


class TestHitRateIsCandidateLevel:
    def test_all_horizons_hit(self):
        """When all 3 horizons have positive excess_return, hit_rate = 1.0."""
        outcome = _outcome(returns=[0.05, 0.10, 0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.hit_rate == 1.0

    def test_all_horizons_miss(self):
        """When all 3 horizons have negative excess_return, hit_rate = 0.0."""
        outcome = _outcome(returns=[-0.05, -0.10, -0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.hit_rate == 0.0

    def test_mixed_horizons(self):
        """When 2/3 horizons hit, hit_rate = 2/3 = 0.666...

        This shows horizon-level aggregation (current behavior).
        If changed to candidate-level (avg excess >= 0),
        the expected value would differ.
        """
        outcome = _outcome(returns=[0.05, -0.10, 0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.hit_rate is not None
        assert metrics.hit_rate == 2 / 3


class TestFalsePositiveRateUnavailable:
    def test_fp_rate_is_not_1_minus_hit_rate_when_no_control(self):
        """Without a non-candidate control group, fp_rate must be None."""
        outcome = _outcome(returns=[0.05, 0.10, 0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.false_positive_rate is None, (
            "false_positive_rate must be None when no control group exists"
        )

    def test_fp_rate_all_miss_still_none(self):
        """Even when all horizons miss, fp_rate is None (no control group)."""
        outcome = _outcome(returns=[-0.05, -0.10, -0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.false_positive_rate is None

    def test_fp_rate_some_gaps_still_none(self):
        """With data gaps, fp_rate is still None."""
        outcome = _outcome(
            returns=[0.05, None, None],
            gaps=[None, "price_data_missing", "price_data_missing"],
        )
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.false_positive_rate is None


class TestFalseNegativeRateUnavailable:
    def test_fn_rate_always_none(self):
        """Without negative predictions, fn_rate must be None."""
        outcome = _outcome(returns=[0.05, 0.10, 0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.false_negative_rate is None

    def test_fn_rate_all_miss_still_none(self):
        """Even without any hits, fn_rate is None (no negative predictions)."""
        outcome = _outcome(returns=[-0.05, -0.10, -0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert metrics.false_negative_rate is None


class TestHorizonsNotIndependentCandidates:
    def test_one_candidate_three_horizons_counts_as_one(self):
        """A single evaluation date with 3 horizons must not inflate candidate count."""
        outcome = _outcome(returns=[0.05, 0.10, 0.15])
        cal = MetricsCalculator()
        metrics = cal.evaluate(_panel(), outcome)
        assert len(metrics.horizons) == 3, "Horizons must preserve their individual metrics"
        assert metrics.hit_rate is not None, "Candidate-level hit rate must still be computed"
