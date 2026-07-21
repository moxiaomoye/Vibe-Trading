from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import MarketRegime
from src.investment_research.market.assessment import MarketSnapshot, MarketStateAssessmentEngine


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot("snapshot-1", "evidence-set-1", NOW, -0.28, 0.9, 0.1, 150, -0.055, 2.4)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, MarketRegime.PANIC),
        (
            {
                "broad_index_drawdown": -0.16,
                "index_below_long_trend_ratio": 0.65,
                "advancer_ratio": 0.3,
                "limit_down_count": 35,
                "median_daily_return": -0.025,
                "turnover_stress_zscore": 1.0,
            },
            MarketRegime.SYSTEMIC_STRESS,
        ),
        (
            {
                "broad_index_drawdown": -0.13,
                "index_below_long_trend_ratio": 0.65,
                "advancer_ratio": 0.5,
                "limit_down_count": 5,
                "median_daily_return": -0.005,
                "turnover_stress_zscore": 0.5,
            },
            MarketRegime.CORRECTION,
        ),
        (
            {
                "broad_index_drawdown": -0.05,
                "index_below_long_trend_ratio": 0.2,
                "advancer_ratio": 0.55,
                "limit_down_count": 2,
                "median_daily_return": 0.002,
                "turnover_stress_zscore": 0.2,
            },
            MarketRegime.NORMAL,
        ),
    ],
)
def test_market_state_requires_correlated_stress_signals(changes, expected: MarketRegime) -> None:
    state = MarketStateAssessmentEngine().assess("market-1", replace(_snapshot(), **changes), NOW)
    assert state.regime == expected
    assert state.evidence_set_id == "evidence-set-1"


def test_incomplete_market_data_is_unknown_not_false_calm() -> None:
    snapshot = replace(
        _snapshot(), broad_index_drawdown=None, index_below_long_trend_ratio=None,
        advancer_ratio=None, limit_down_count=None, data_gaps=("breadth",),
    )
    state = MarketStateAssessmentEngine().assess("market-1", snapshot, NOW)
    assert state.regime == MarketRegime.UNKNOWN
    assert "insufficient_market_coverage" in state.data_gaps


def test_market_assessment_rejects_future_and_invalid_observations() -> None:
    with pytest.raises(ValueError, match="future"):
        MarketStateAssessmentEngine().assess("market-1", replace(_snapshot(), as_of=NOW + timedelta(minutes=1)), NOW)
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(_snapshot(), advancer_ratio=1.1)
    with pytest.raises(ValueError, match="negative"):
        replace(_snapshot(), limit_down_count=-1)
