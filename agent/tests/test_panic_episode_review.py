from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.operations.outcome_loader import (
    FixtureOutcomeLoader,
)
from src.investment_research.operations.panic_episode_review import (
    PanicEpisodeReviewWorkflow,
)


class TestPanicEpisodeReviewWorkflow:
    def test_review_empty_episode(self) -> None:
        loader = FixtureOutcomeLoader({})
        workflow = PanicEpisodeReviewWorkflow(loader)
        summary = workflow.review_episode(())
        assert summary.total_dates == 0
        assert summary.available_dates == 0
        assert summary.aggregate_hit_rate is None

    def test_review_single_date_with_data(self) -> None:
        d = date(2026, 7, 15)
        fixtures = {
            d: {
                "_entry_price": 15.0,
                5: {
                    "asset_return": 0.02,
                    "benchmark_return": 0.01,
                    "excess_return": 0.01,
                    "maximum_drawdown": -0.03,
                },
            }
        }
        loader = FixtureOutcomeLoader(fixtures)
        workflow = PanicEpisodeReviewWorkflow(loader)
        summary = workflow.review_episode((d,))
        assert summary.total_dates == 1
        assert summary.episode_start == d
        assert summary.episode_end == d
        assert len(summary.dates) == 1
        assert summary.dates[0].trade_date == d

    def test_review_multi_date(self) -> None:
        d1 = date(2026, 7, 15)
        d2 = date(2026, 7, 16)
        fixtures = {
            d1: {
                "_entry_price": 15.0,
                5: {
                    "asset_return": 0.02,
                    "benchmark_return": 0.01,
                    "excess_return": 0.01,
                    "maximum_drawdown": -0.03,
                },
            },
            d2: {
                "_entry_price": 14.5,
                5: {
                    "asset_return": -0.01,
                    "benchmark_return": 0.0,
                    "excess_return": -0.01,
                    "maximum_drawdown": -0.02,
                },
            },
        }
        loader = FixtureOutcomeLoader(fixtures)
        workflow = PanicEpisodeReviewWorkflow(loader)
        summary = workflow.review_episode((d1, d2))
        assert summary.total_dates == 2
        assert summary.aggregate_hit_rate == 0.5
        assert summary.aggregate_avg_excess_return is not None
        assert summary.aggregate_avg_max_drawdown is not None
        assert sum(summary.label_distribution.values()) > 0

    def test_label_distribution_in_summary(self) -> None:
        d = date(2026, 7, 15)
        fixtures = {
            d: {
                "_entry_price": 15.0,
                5: {
                    "asset_return": 0.02,
                    "benchmark_return": 0.01,
                    "excess_return": 0.01,
                    "maximum_drawdown": -0.03,
                },
                20: {
                    "asset_return": -0.01,
                    "benchmark_return": 0.01,
                    "excess_return": -0.02,
                    "maximum_drawdown": -0.05,
                },
            }
        }
        loader = FixtureOutcomeLoader(fixtures)
        workflow = PanicEpisodeReviewWorkflow(loader)
        summary = workflow.review_episode((d,))
        dist = summary.label_distribution
        assert dist.get("correct_call", 0) >= 1
        assert dist.get("false_positive", 0) >= 1
