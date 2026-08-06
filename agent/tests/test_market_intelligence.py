"""Market State Engine unit tests (Phase 1 Market Intelligence Layer)."""

from __future__ import annotations

from datetime import date

from src.investment_research.models.data_quality import DataQualityStatus
from src.investment_research.models.market_intelligence import (
    MARKET_INTELLIGENCE_VERSION,
    MarketDimension,
    MarketIntelligenceConfig,
    MarketState,
    evaluate_market_intelligence,
)
from src.investment_research.models.research_context import MarketSnapshotModel


def _market(**overrides) -> MarketSnapshotModel:
    values = {
        "as_of": "2024-02-05",
        "indices": [],
        "advancer_ratio": None,
        "above_ma60_ratio": None,
        "limit_down_count": None,
        "turnover_zscore": None,
    }
    values.update(overrides)
    return MarketSnapshotModel(**values)


def _index(close=3000.0, daily_return_pct=-1.0, drawdown_252_pct=-10.0,
           below_ma250=False, below_120d_low=False) -> dict:
    return {
        "symbol": "000300.SH",
        "name": "沪深300",
        "close": close,
        "daily_return_pct": daily_return_pct,
        "drawdown_252_pct": drawdown_252_pct,
        "below_ma250": below_ma250,
        "below_120d_low": below_120d_low,
    }


class TestStateBands:
    def test_normal_market(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index()],
            advancer_ratio=0.6,
            limit_down_count=5,
            turnover_zscore=-0.5,
        ))
        assert intel.state is MarketState.NORMAL
        assert intel.stress_score < 40
        assert intel.coverage["available"] == 4

    def test_stress_market(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index(daily_return_pct=-2.5, drawdown_252_pct=-12.0)],
            advancer_ratio=0.45,
            limit_down_count=30,
            turnover_zscore=1.6,
        ))
        assert intel.state is MarketState.STRESS
        assert 40 <= intel.stress_score < 60

    def test_panic_market(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index(daily_return_pct=-4.0, drawdown_252_pct=-25.0)],
            advancer_ratio=0.15,
            limit_down_count=40,
            turnover_zscore=0.5,
        ))
        assert intel.state is MarketState.PANIC
        assert 60 <= intel.stress_score < 80

    def test_extreme_panic_market(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index(daily_return_pct=-7.0, drawdown_252_pct=-35.0)],
            advancer_ratio=0.05,
            limit_down_count=170,
            turnover_zscore=1.8,
        ))
        assert intel.state is MarketState.EXTREME_PANIC
        assert intel.stress_score >= 80

    def test_unknown_when_no_evidence(self) -> None:
        intel = evaluate_market_intelligence(_market())
        assert intel.state is MarketState.UNKNOWN
        assert intel.stress_score is None
        assert intel.coverage == {"available": 0, "estimated": 0, "total": 6}


class TestAvailability:
    def test_missing_dimensions_are_unavailable_not_silent(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index(daily_return_pct=-7.0)],
            advancer_ratio=0.05,
        ))
        verdicts = {v.dimension: v for v in intel.dimensions}
        assert verdicts[MarketDimension.LIMIT].status is DataQualityStatus.UNAVAILABLE
        assert "Data Gap" in (verdicts[MarketDimension.LIMIT].note or "")
        assert verdicts[MarketDimension.TURNOVER].status is DataQualityStatus.UNAVAILABLE
        assert verdicts[MarketDimension.VOLATILITY].status is DataQualityStatus.UNAVAILABLE
        assert verdicts[MarketDimension.ERP].status is DataQualityStatus.UNAVAILABLE
        assert "预留" in (verdicts[MarketDimension.VOLATILITY].note or "")

    def test_renormalization_does_not_hide_coverage(self) -> None:
        available = evaluate_market_intelligence(_market(
            indices=[_index(daily_return_pct=-7.0, drawdown_252_pct=-30.0,
                            below_ma250=True, below_120d_low=True)],
            advancer_ratio=0.0,
        ))
        assert available.stress_score == 100
        assert available.coverage["available"] == 2
        assert available.state is MarketState.EXTREME_PANIC

    def test_breadth_falls_back_to_ma60_when_advancer_missing(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index()],
            above_ma60_ratio=0.1,
        ))
        breadth = next(
            v for v in intel.dimensions if v.dimension is MarketDimension.BREADTH
        )
        assert breadth.status is DataQualityStatus.AVAILABLE
        assert breadth.triggered is True


class TestEstimatedEvidence:
    def test_estimated_limit_is_visible_not_available(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index()],
            advancer_ratio=0.6,
            limit_down_count=170,
            estimated_fields=["limit_down_count"],
        ))
        limit = next(
            v for v in intel.dimensions if v.dimension is MarketDimension.LIMIT
        )
        assert limit.status is DataQualityStatus.ESTIMATED
        assert "估计" in (limit.note or "")
        assert limit.triggered is True
        assert intel.coverage["available"] == 2
        assert intel.coverage["estimated"] == 1
        assert intel.coverage["total"] == 6
        assert intel.state is not MarketState.UNKNOWN

    def test_estimated_evidence_never_counts_toward_stress_score(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index()],
            advancer_ratio=0.6,
            limit_down_count=170,
            estimated_fields=["limit_down_count"],
        ))
        assert intel.state is MarketState.NORMAL
        assert 0 <= intel.stress_score < 40

    def test_estimated_without_value_stays_unavailable(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index()],
            advancer_ratio=0.6,
            limit_down_count=None,
            estimated_fields=["limit_down_count"],
        ))
        limit = next(
            v for v in intel.dimensions if v.dimension is MarketDimension.LIMIT
        )
        assert limit.status is DataQualityStatus.UNAVAILABLE
        assert "Data Gap" in (limit.note or "")


class TestDeterminismAndPurity:
    def test_deterministic_for_same_snapshot(self) -> None:
        market = _market(
            indices=[_index(daily_return_pct=-4.0)],
            advancer_ratio=0.15,
            limit_down_count=80,
            turnover_zscore=1.6,
        )
        first = evaluate_market_intelligence(market)
        second = evaluate_market_intelligence(market)
        assert first.model_dump() == second.model_dump()
        assert first.version == MARKET_INTELLIGENCE_VERSION
        assert first.thresholds_version == MARKET_INTELLIGENCE_VERSION

    def test_never_emits_trading_directives(self) -> None:
        intel = evaluate_market_intelligence(_market(
            indices=[_index(daily_return_pct=-7.0)],
            advancer_ratio=0.05,
            limit_down_count=170,
            turnover_zscore=2.0,
        ))
        serialized = intel.model_dump()
        for key in ("action", "signal", "recommendation", "order", "buy", "sell"):
            assert key not in serialized

    def test_thresholds_are_frozen_defaults(self) -> None:
        config = MarketIntelligenceConfig()
        assert config.index_daily_return_pct == -2.0
        assert config.advancer_ratio == 0.30
        assert config.min_limit_down_count == 50
        assert config.turnover_zscore == 1.5
        assert sum(config.weights.values()) == 100.0
