from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.operations.outcome_loader import (
    HistoricalEvaluationOutcome,
    WindowOutcome,
)
from src.investment_research.operations.review_labeling import (
    ReviewLabel,
    label_counts,
    label_outcome,
    label_window,
)


class TestReviewLabeling:
    def test_correct_call_positive_excess(self) -> None:
        w = WindowOutcome(5, 0.02, 0.01, 0.01, -0.03)
        assert label_window(w) == ReviewLabel.CORRECT_CALL

    def test_correct_call_zero_excess(self) -> None:
        w = WindowOutcome(5, 0.0, 0.0, 0.0, 0.0)
        assert label_window(w) == ReviewLabel.CORRECT_CALL

    def test_false_positive_negative_excess(self) -> None:
        w = WindowOutcome(5, -0.02, 0.01, -0.03, -0.05)
        assert label_window(w) == ReviewLabel.FALSE_POSITIVE

    def test_unclear_data_gap(self) -> None:
        w = WindowOutcome(5, None, None, None, None, data_gap="no_data")
        assert label_window(w) == ReviewLabel.UNCLEAR

    def test_unclear_no_excess_return(self) -> None:
        w = WindowOutcome(5, 0.01, 0.0, None, -0.02)
        assert label_window(w) == ReviewLabel.UNCLEAR

    def test_custom_threshold(self) -> None:
        w = WindowOutcome(5, 0.02, 0.0, 0.02, -0.01)
        assert label_window(w, positive_threshold=0.03) == ReviewLabel.FALSE_POSITIVE

    def test_label_outcome_all_horizons(self) -> None:
        outcome = HistoricalEvaluationOutcome(
            evaluation_date=date(2026, 7, 15),
            entry_price=15.0,
            windows=(
                WindowOutcome(5, 0.02, 0.01, 0.01, -0.03),
                WindowOutcome(20, -0.01, 0.01, -0.02, -0.05),
                WindowOutcome(60, None, None, None, None, data_gap="not_yet"),
            ),
        )
        labels = label_outcome(outcome)
        assert labels[5] == ReviewLabel.CORRECT_CALL
        assert labels[20] == ReviewLabel.FALSE_POSITIVE
        assert labels[60] == ReviewLabel.UNCLEAR

    def test_label_counts(self) -> None:
        labels = {
            5: ReviewLabel.CORRECT_CALL,
            20: ReviewLabel.FALSE_POSITIVE,
            60: ReviewLabel.UNCLEAR,
        }
        counts = label_counts(labels)
        assert counts[ReviewLabel.CORRECT_CALL] == 1
        assert counts[ReviewLabel.FALSE_POSITIVE] == 1
        assert counts[ReviewLabel.UNCLEAR] == 1
        assert counts[ReviewLabel.FALSE_NEGATIVE] == 0

    def test_label_counts_empty(self) -> None:
        counts = label_counts({})
        for label in ReviewLabel:
            assert counts[label] == 0
