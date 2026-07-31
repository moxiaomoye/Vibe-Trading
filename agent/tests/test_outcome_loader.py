from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.operations.outcome_loader import (
    DEFAULT_HORIZONS,
    FixtureOutcomeLoader,
    HistoricalEvaluationOutcome,
    OutcomeLoader,
    WindowOutcome,
)


class TestFixtureOutcomeLoader:
    def test_load_complete_outcomes(self) -> None:
        d = date(2026, 7, 15)
        fixtures = {
            d: {
                "_entry_price": 15.5,
                5: {
                    "asset_return": 0.02,
                    "benchmark_return": 0.01,
                    "excess_return": 0.01,
                    "maximum_drawdown": -0.03,
                    "invalidation_triggered": False,
                },
                20: {
                    "asset_return": 0.05,
                    "benchmark_return": 0.03,
                    "excess_return": 0.02,
                    "maximum_drawdown": -0.05,
                    "invalidation_triggered": False,
                },
                60: {
                    "asset_return": -0.02,
                    "benchmark_return": 0.04,
                    "excess_return": -0.06,
                    "maximum_drawdown": -0.12,
                    "invalidation_triggered": True,
                },
            }
        }
        loader = FixtureOutcomeLoader(fixtures)
        outcome = loader.load(d)
        assert outcome.entry_price == 15.5
        assert len(outcome.windows) == 3

        window_5 = outcome.windows[0]
        assert window_5.horizon == 5
        assert window_5.asset_return == 0.02
        assert window_5.benchmark_return == 0.01
        assert window_5.excess_return == 0.01
        assert window_5.maximum_drawdown == -0.03
        assert not window_5.invalidation_triggered
        assert window_5.data_gap is None

        window_60 = outcome.windows[2]
        assert window_60.horizon == 60
        assert window_60.invalidation_triggered

    def test_load_missing_date_returns_none_outcomes(self) -> None:
        loader = FixtureOutcomeLoader({})
        outcome = loader.load(date(2026, 7, 15))
        assert outcome.entry_price == 0.0
        assert len(outcome.windows) == 3
        for w in outcome.windows:
            assert w.asset_return is None
            assert w.data_gap == "not_yet_tracked"

    def test_load_partial_windows(self) -> None:
        d = date(2026, 7, 20)
        fixtures = {
            d: {
                "_entry_price": 14.0,
                5: {
                    "asset_return": -0.01,
                    "benchmark_return": 0.0,
                    "excess_return": -0.01,
                    "maximum_drawdown": -0.02,
                },
            }
        }
        loader = FixtureOutcomeLoader(fixtures)
        outcome = loader.load(d)
        assert len(outcome.windows) == 1
        assert outcome.windows[0].horizon == 5

    def test_default_horizons(self) -> None:
        assert DEFAULT_HORIZONS == (5, 20, 60)

    def test_outcome_loader_must_be_subclassed(self) -> None:
        loader = OutcomeLoader()
        with pytest.raises(NotImplementedError):
            loader.load(date(2026, 7, 15))

    def test_window_outcome_frozen(self) -> None:
        w = WindowOutcome(
            horizon=5, asset_return=0.01, benchmark_return=0.0,
            excess_return=0.01, maximum_drawdown=-0.02,
        )
        with pytest.raises(AttributeError):
            w.asset_return = 0.05
