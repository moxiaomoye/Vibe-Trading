from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from src.investment_research.operations.evaluation_metrics import (
    EvaluationMetrics,
    HorizonMetrics,
    MetricsCalculator,
)
from src.investment_research.operations.outcome_loader import (
    HistoricalEvaluationOutcome,
    WindowOutcome,
)


class TestMetricsCalculator:
    def panel(self, d: date, price: float = 15.0) -> HistoricalMarketPanel:
        return HistoricalMarketPanel(
            date=d, market_price=price, market_change_pct=0.0,
            ma_5=price, ma_10=price, ma_20=price,
            volume=0, turnover=0.0, amplitude=0.0,
        )

    def outcome(
        self, d: date, price: float = 15.0,
        windows: tuple[WindowOutcome, ...] | None = None,
    ) -> HistoricalEvaluationOutcome:
        if windows is None:
            windows = (
                WindowOutcome(5, 0.02, 0.01, 0.01, -0.03),
                WindowOutcome(20, 0.05, 0.03, 0.02, -0.05),
                WindowOutcome(60, -0.02, 0.04, -0.06, -0.12, True),
            )
        return HistoricalEvaluationOutcome(d, price, windows)

    def test_evaluate_all_positive_excess(self) -> None:
        d = date(2026, 7, 15)
        metrics = MetricsCalculator().evaluate(self.panel(d), self.outcome(d))
        assert metrics.hit_rate == 2 / 3
        assert metrics.false_positive_rate is None, "unavailable without control group"
        assert metrics.false_negative_rate is None, "unavailable without control group"
        assert metrics.avg_excess_return is not None
        assert metrics.avg_excess_return == pytest.approx(
            (0.01 + 0.02 + (-0.06)) / 3
        )
        assert metrics.avg_max_drawdown is not None

    def test_hit_rate_all_hits(self) -> None:
        d = date(2026, 7, 15)
        windows = (
            WindowOutcome(5, 0.02, 0.01, 0.01, -0.03),
            WindowOutcome(20, 0.05, 0.03, 0.02, -0.05),
            WindowOutcome(60, 0.04, 0.02, 0.02, -0.06),
        )
        metrics = MetricsCalculator().evaluate(
            self.panel(d), self.outcome(d, windows=windows)
        )
        assert metrics.hit_rate == 1.0
        assert metrics.false_positive_rate is None, "unavailable without control group"

    def test_hit_rate_none_when_all_gapped(self) -> None:
        d = date(2026, 7, 15)
        windows = (
            WindowOutcome(5, None, None, None, None, data_gap="no_data"),
            WindowOutcome(20, None, None, None, None, data_gap="no_data"),
        )
        metrics = MetricsCalculator().evaluate(
            self.panel(d), self.outcome(d, windows=windows)
        )
        assert metrics.hit_rate is None
        assert metrics.false_positive_rate is None

    def test_date_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="entry date mismatch"):
            MetricsCalculator().evaluate(
                self.panel(date(2026, 7, 15)),
                self.outcome(date(2026, 7, 16)),
            )

    def test_horizon_metrics_struct(self) -> None:
        h = HorizonMetrics(
            horizon=5, asset_return=0.01, benchmark_return=0.0,
            excess_return=0.01, maximum_drawdown=-0.02, hit=True,
            data_gap=None,
        )
        assert h.horizon == 5
        assert h.hit is True

    def test_horizon_metrics_frozen(self) -> None:
        h = HorizonMetrics(
            horizon=5, asset_return=0.01, benchmark_return=0.0,
            excess_return=0.01, maximum_drawdown=-0.02, hit=True,
            data_gap=None,
        )
        with pytest.raises(AttributeError):
            h.hit = False
