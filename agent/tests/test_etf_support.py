from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.operations.etf_support import (
    ETFOutcomeLoader,
    compute_tracking_error,
    etf_review_labels,
)
from src.investment_research.operations.review_labeling import ReviewLabel


class TestETFSupport:
    def test_compute_tracking_error(self) -> None:
        asset = [0.01, 0.02, -0.01, 0.005, 0.015]
        bench = [0.005, 0.015, -0.005, 0.01, 0.01]
        te = compute_tracking_error(asset, bench)
        assert te is not None
        assert te >= 0

    def test_tracking_error_empty_returns_none(self) -> None:
        assert compute_tracking_error([], []) is None

    def test_tracking_error_mismatched_lengths(self) -> None:
        assert compute_tracking_error([0.01, 0.02], [0.01]) is None

    def test_tracking_error_perfect_tracking(self) -> None:
        returns = [0.01, 0.02, -0.01, 0.0]
        te = compute_tracking_error(returns, returns)
        assert te == 0.0

    def test_etf_outcome_loader_missing_date(self) -> None:
        loader = ETFOutcomeLoader({})
        outcome = loader.load(date(2026, 7, 15))
        assert outcome.entry_price == 0.0
        for w in outcome.windows:
            assert w.data_gap == "not_yet_tracked"

    def test_etf_outcome_loader_with_data(self) -> None:
        d = date(2026, 7, 15)
        fixtures = {
            d: {
                "_entry_price": 50.0,
                5: {
                    "asset_return": 0.01,
                    "benchmark_return": 0.008,
                    "excess_return": 0.002,
                    "maximum_drawdown": -0.02,
                },
            }
        }
        loader = ETFOutcomeLoader(fixtures)
        outcome = loader.load(d)
        assert outcome.entry_price == 50.0
        assert len(outcome.windows) == 1

    def test_etf_review_labels(self) -> None:
        from src.investment_research.operations.outcome_loader import (
            HistoricalEvaluationOutcome,
            WindowOutcome,
        )
        outcome = HistoricalEvaluationOutcome(
            evaluation_date=date(2026, 7, 15),
            entry_price=50.0,
            windows=(
                WindowOutcome(5, 0.01, 0.008, 0.002, -0.02),
                WindowOutcome(20, -0.01, 0.005, -0.015, -0.03),
            ),
        )
        labels = etf_review_labels(outcome)
        assert labels[5] == ReviewLabel.CORRECT_CALL
        assert labels[20] == ReviewLabel.FALSE_POSITIVE
