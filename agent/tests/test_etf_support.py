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

    def test_tracking_error_threshold_unused(self) -> None:
        """tracking_error_threshold parameter is defined but never used in etf_review_labels."""
        from src.investment_research.operations.outcome_loader import (
            HistoricalEvaluationOutcome,
            WindowOutcome,
        )
        outcome = HistoricalEvaluationOutcome(
            evaluation_date=date(2026, 7, 15),
            entry_price=50.0,
            windows=(
                WindowOutcome(5, 0.01, 0.008, 0.002, -0.02),
            ),
        )
        labels_default = etf_review_labels(outcome)
        labels_custom = etf_review_labels(outcome, tracking_error_threshold=999.0)
        assert labels_default == labels_custom, (
            "tracking_error_threshold has no effect — parameter is dead"
        )

    def test_etf_outcome_loader_is_fixture_copy(self) -> None:
        """ETFOutcomeLoader is structurally identical to FixtureOutcomeLoader.

        Both take fixture_outcomes dict, both return HistoricalEvaluationOutcome
        with same WindowOutcome structure. No ETF-specific logic exists.
        """
        from src.investment_research.operations.outcome_loader import (
            FixtureOutcomeLoader,
        )
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
        etf_loader = ETFOutcomeLoader(fixtures)
        fixture_loader = FixtureOutcomeLoader(fixtures)
        etf_outcome = etf_loader.load(d)
        fixture_outcome = fixture_loader.load(d)
        assert etf_outcome.entry_price == fixture_outcome.entry_price
        assert len(etf_outcome.windows) == len(fixture_outcome.windows)
        for ew, fw in zip(etf_outcome.windows, fixture_outcome.windows):
            assert ew.asset_return == fw.asset_return
            assert ew.benchmark_return == fw.benchmark_return
            assert ew.excess_return == fw.excess_return
            assert ew.maximum_drawdown == fw.maximum_drawdown

    def test_etf_does_not_access_financial_fields(self) -> None:
        """ETFOutcomeLoader source does not reference financial/accounting fields."""
        from pathlib import Path
        source_path = Path(__file__).parent.parent / "src" / "investment_research" / "operations" / "etf_support.py"
        source = source_path.read_text(encoding="utf-8")
        financial_keywords = [
            "pe_ratio", "pb_ratio", "roe", "eps", "revenue",
            "profit", "financial", "财务报表", "净利润", "营业收入",
        ]
        for kw in financial_keywords:
            assert kw not in source.lower(), (
                f"ETFOutcomeLoader source should not contain '{kw}'"
            )

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
