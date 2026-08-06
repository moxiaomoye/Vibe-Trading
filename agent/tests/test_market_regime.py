"""Regime Detection (Phase 2) contract tests - pure macro state engine."""

from __future__ import annotations

from src.investment_research.models.data_quality import DataQualityStatus
from src.investment_research.models.market_regime import (
    MARKET_REGIME_VERSION,
    MacroDimension,
    MacroSnapshotModel,
    MarketRegimeConfig,
    Regime,
    evaluate_market_regime,
)


def _macro(**overrides) -> MacroSnapshotModel:
    values: dict = {
        "as_of": "2024-02-05",
        "rate_change_bp": None,
        "liquidity_gap_bp": None,
        "equity_risk_premium_pct": None,
        "earnings_revision_pct": None,
        "credit_spread_bp": None,
    }
    values.update(overrides)
    return MacroSnapshotModel(**values)


def _all_available(**overrides) -> MacroSnapshotModel:
    values = {
        "rate_change_bp": 10.0,
        "liquidity_gap_bp": 20.0,
        "equity_risk_premium_pct": 3.5,
        "earnings_revision_pct": 0.0,
        "credit_spread_bp": 50.0,
    }
    values.update(overrides)
    return _macro(**values)


class TestRegimeClassification:
    def test_stable_when_nothing_triggered(self) -> None:
        result = evaluate_market_regime(_all_available())
        assert result.regime is Regime.STABLE
        assert result.coverage["available"] == 5
        assert result.coverage["estimated"] == 0

    def test_liquidity_panic_when_funding_spread_spikes(self) -> None:
        result = evaluate_market_regime(_all_available(liquidity_gap_bp=250.0))
        assert result.regime is Regime.LIQUIDITY_PANIC
        verdict = next(v for v in result.dimensions if v.dimension is MacroDimension.LIQUIDITY)
        assert verdict.triggered is True
        assert any("Liquidity" in line or "资金面" in line for line in result.summary)

    def test_liquidity_priority_over_earnings_downgrade(self) -> None:
        result = evaluate_market_regime(_all_available(
            liquidity_gap_bp=300.0,
            earnings_revision_pct=-8.0,
            credit_spread_bp=400.0,
        ))
        assert result.regime is Regime.LIQUIDITY_PANIC

    def test_earnings_downgrade_regime(self) -> None:
        result = evaluate_market_regime(_all_available(earnings_revision_pct=-5.0))
        assert result.regime is Regime.EARNINGS_DOWNGRADE

    def test_structural_repricing_regime(self) -> None:
        result = evaluate_market_regime(_all_available(equity_risk_premium_pct=6.2))
        assert result.regime is Regime.STRUCTURAL_REPRICING

    def test_structural_repricing_credit_spread(self) -> None:
        result = evaluate_market_regime(_all_available(credit_spread_bp=350.0))
        assert result.regime is Regime.STRUCTURAL_REPRICING

    def test_structural_repricing_rate_hike_shock(self) -> None:
        result = evaluate_market_regime(_all_available(rate_change_bp=80.0))
        assert result.regime is Regime.STRUCTURAL_REPRICING

    def test_earnings_threshold_is_downgrade_side(self) -> None:
        config = MarketRegimeConfig()
        assert config.earnings_revision_pct < 0


class TestAvailabilityAndGaps:
    def test_unknown_when_no_evidence(self) -> None:
        result = evaluate_market_regime(_macro())
        assert result.regime is Regime.UNKNOWN
        assert result.coverage == {"available": 0, "estimated": 0, "total": 5}
        assert any("缺口" in line for line in result.summary)

    def test_missing_dimensions_are_unavailable_not_silent(self) -> None:
        result = evaluate_market_regime(_macro(liquidity_gap_bp=10.0))
        verdicts = {v.dimension: v for v in result.dimensions}
        assert verdicts[MacroDimension.RATE].status is DataQualityStatus.UNAVAILABLE
        assert "Data Gap" in (verdicts[MacroDimension.RATE].note or "")
        assert verdicts[MacroDimension.LIQUIDITY].status is DataQualityStatus.AVAILABLE
        assert verdicts[MacroDimension.CREDIT].status is DataQualityStatus.UNAVAILABLE

    def test_estimated_inputs_are_labeled_and_excluded(self) -> None:
        result = evaluate_market_regime(_all_available(
            liquidity_gap_bp=250.0,
            estimated_fields=["liquidity_gap_bp"],
        ))
        liquidity = next(
            v for v in result.dimensions if v.dimension is MacroDimension.LIQUIDITY
        )
        assert liquidity.status is DataQualityStatus.ESTIMATED
        assert "估计" in (liquidity.note or "")
        assert result.coverage["available"] == 4
        assert result.coverage["estimated"] == 1
        assert result.regime is not Regime.LIQUIDITY_PANIC

    def test_estimated_liquidity_cannot_drive_panic(self) -> None:
        result = evaluate_market_regime(_all_available(
            liquidity_gap_bp=250.0,
            estimated_fields=["liquidity_gap_bp"],
        ))
        assert result.regime is Regime.STABLE


class TestContractShape:
    def test_deterministic_for_same_snapshot(self) -> None:
        macro = _all_available(liquidity_gap_bp=250.0)
        assert evaluate_market_regime(macro).model_dump() == evaluate_market_regime(macro).model_dump()

    def test_version_is_frozen(self) -> None:
        assert MarketRegimeConfig().version == MARKET_REGIME_VERSION
        assert evaluate_market_regime(_macro()).version == MARKET_REGIME_VERSION

    def test_thresholds_are_frozen_defaults(self) -> None:
        config = MarketRegimeConfig()
        assert config.rate_hike_bp == 50.0
        assert config.liquidity_gap_bp == 100.0
        assert config.erp_pct == 5.0
        assert config.earnings_revision_pct == -3.0
        assert config.credit_spread_bp == 200.0
        assert sum(config.weights.values()) == 100.0

    def test_never_emits_trading_directives(self) -> None:
        serialized = evaluate_market_regime(_all_available(liquidity_gap_bp=250.0)).model_dump()
        for key in ("action", "signal", "recommendation", "order", "buy", "sell"):
            assert key not in serialized

    def test_triggered_dimensions_are_documented(self) -> None:
        result = evaluate_market_regime(_all_available(
            rate_change_bp=80.0,
            earnings_revision_pct=-4.0,
        ))
        assert result.regime is Regime.EARNINGS_DOWNGRADE
        triggered = {v.dimension for v in result.dimensions if v.triggered}
        assert MacroDimension.RATE in triggered
        assert MacroDimension.EARNINGS in triggered
