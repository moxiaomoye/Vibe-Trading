from __future__ import annotations

from enum import StrEnum

from ...investment_research.operations.outcome_loader import (
    HistoricalEvaluationOutcome,
    WindowOutcome,
)


class ReviewLabel(StrEnum):
    CORRECT_CALL = "correct_call"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    UNCLEAR = "unclear"


def label_window(window: WindowOutcome, *, positive_threshold: float = 0.0) -> ReviewLabel:
    if window.data_gap is not None:
        return ReviewLabel.UNCLEAR
    if window.excess_return is None:
        return ReviewLabel.UNCLEAR
    if window.excess_return >= positive_threshold:
        return ReviewLabel.CORRECT_CALL
    return ReviewLabel.FALSE_POSITIVE


def label_outcome(
    outcome: HistoricalEvaluationOutcome,
    *,
    positive_threshold: float = 0.0,
) -> dict[int, ReviewLabel]:
    return {
        window.horizon: label_window(window, positive_threshold=positive_threshold)
        for window in outcome.windows
    }


def label_counts(
    labels: dict[int, ReviewLabel],
) -> dict[ReviewLabel, int]:
    counts: dict[ReviewLabel, int] = {}
    for label in labels.values():
        counts[label] = counts.get(label, 0) + 1
    for label in ReviewLabel:
        counts.setdefault(label, 0)
    return counts
