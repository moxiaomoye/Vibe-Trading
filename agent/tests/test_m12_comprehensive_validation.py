"""M12 comprehensive validation: end-to-end pipeline test for M1.3."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from src.investment_research.operations.evaluation_metrics import (
    MetricsCalculator,
)
from src.investment_research.operations.historical_shadow_run import (
    HistoricalShadowRunner,
)
from src.investment_research.operations.market_loader import (
    FixtureHistoricalMarketLoader,
)
from src.investment_research.operations.outcome_loader import (
    FixtureOutcomeLoader,
)
from src.investment_research.operations.panic_episode_review import (
    PanicEpisodeReviewWorkflow,
)
from src.investment_research.operations.review_labeling import (
    label_outcome,
)
from src.investment_research.operations.trading_calendar import (
    TradingCalendar,
)


class TestM12ComprehensiveValidation:
    SHANGHAI = ZoneInfo("Asia/Shanghai")

    def test_full_pipeline_happy_path(self) -> None:
        d = date(2026, 7, 15)

        market_fixtures = {
            d: {
                "market_price": 15.5,
                "market_change_pct": -2.1,
                "ma_5": 15.0,
                "ma_10": 14.8,
                "ma_20": 14.5,
                "volume": 1_000_000,
                "turnover": 0.05,
                "amplitude": 3.2,
            }
        }
        outcome_fixtures = {
            d: {
                "_entry_price": 15.5,
                5: {
                    "asset_return": 0.02,
                    "benchmark_return": 0.01,
                    "excess_return": 0.01,
                    "maximum_drawdown": -0.03,
                },
                20: {
                    "asset_return": 0.05,
                    "benchmark_return": 0.03,
                    "excess_return": 0.02,
                    "maximum_drawdown": -0.05,
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

        now = datetime(2026, 7, 15, 19, 0, tzinfo=self.SHANGHAI)

        market_loader = FixtureHistoricalMarketLoader(market_fixtures)
        outcome_loader = FixtureOutcomeLoader(outcome_fixtures)

        runner = HistoricalShadowRunner(market_loader)
        shadow_result = runner.run_for_date(d, now=now)
        assert shadow_result.data_available
        assert shadow_result.panel.market_price == 15.5
        assert shadow_result.panel.market_change_pct == -2.1

        outcome = outcome_loader.load(d)
        assert outcome.entry_price == 15.5
        assert len(outcome.windows) == 3

        cal = MetricsCalculator()
        metrics = cal.evaluate(shadow_result.panel, outcome)
        assert metrics.hit_rate == 2 / 3
        assert metrics.false_positive_rate == 1 / 3

        labels = label_outcome(outcome)
        assert labels[5].value == "correct_call"
        assert labels[20].value == "correct_call"
        assert labels[60].value == "false_positive"

    def test_full_pipeline_missing_data(self) -> None:
        d = date(2026, 7, 15)
        now = datetime(2026, 7, 15, 19, 0, tzinfo=self.SHANGHAI)

        market_loader = FixtureHistoricalMarketLoader({})
        outcome_loader = FixtureOutcomeLoader({})

        runner = HistoricalShadowRunner(market_loader)
        shadow_result = runner.run_for_date(d, now=now)
        assert not shadow_result.data_available

        outcome = outcome_loader.load(d)
        assert outcome.entry_price == 0.0
        for w in outcome.windows:
            assert w.data_gap == "not_yet_tracked"

    def test_trading_calendar_nth_day(self) -> None:
        cal = TradingCalendar()
        d = date(2026, 7, 15)
        t5 = cal.nth_trading_day_forward(d, 5)
        t20 = cal.nth_trading_day_forward(d, 20)
        t60 = cal.nth_trading_day_forward(d, 60)
        assert t5 is not None
        assert t20 is not None
        assert t60 is not None
        assert t5 > d
        assert t20 > t5
        assert t60 > t20

    def test_panic_episode_review_aggregates(self) -> None:
        dates = [
            date(2026, 7, 15),
            date(2026, 7, 16),
            date(2026, 7, 17),
        ]
        fixtures = {}
        for i, d in enumerate(dates):
            fixtures[d] = {
                "_entry_price": 15.0 - i * 0.5,
                5: {
                    "asset_return": 0.02 - i * 0.01,
                    "benchmark_return": 0.01,
                    "excess_return": 0.01 - i * 0.01,
                    "maximum_drawdown": -0.03 - i * 0.01,
                },
            }

        loader = FixtureOutcomeLoader(fixtures)
        workflow = PanicEpisodeReviewWorkflow(loader)
        summary = workflow.review_episode(tuple(dates))
        assert summary.total_dates == 3
        assert summary.available_dates == 3
        assert summary.aggregate_hit_rate is not None
        assert summary.aggregate_avg_excess_return is not None
        assert summary.aggregate_avg_max_drawdown is not None

    def test_historical_market_panel_validation(self) -> None:
        d = date(2026, 7, 15)

        HistoricalMarketPanel(
            date=d, market_price=0.0, market_change_pct=0.0,
            ma_5=0.0, ma_10=0.0, ma_20=0.0,
            volume=0, turnover=0.0, amplitude=0.0,
        )

        HistoricalMarketPanel(
            date=d, market_price=100000.0, market_change_pct=100.0,
            ma_5=100000.0, ma_10=100000.0, ma_20=100000.0,
            volume=10_000_000_000, turnover=100.0, amplitude=100.0,
        )
