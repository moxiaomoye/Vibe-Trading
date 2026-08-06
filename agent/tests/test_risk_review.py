"""Phase 4 Stock Risk Analyzer tests - value-trap Risk Review contract."""

from __future__ import annotations

from src.investment_research.models.risk_review import (
    RISK_REVIEW_VERSION,
    RiskDimension,
    RiskReviewConfig,
    RiskSeverity,
    evaluate_risk_review,
)


def _observation(**overrides) -> dict:
    values = {
        "security_type": "stock",
        "risk_flags": [],
        "risk_evidence": [],
        "roe_5y_median_pct": 10.0,
        "operating_cashflow_to_profit": 1.2,
        "profit_growth_pct": 15.0,
    }
    values.update(overrides)
    return values


class TestDimensionTriggers:
    def test_clean_stock_is_low_with_leverage_gap(self) -> None:
        review = evaluate_risk_review(_observation())
        assert review.risk_level is RiskSeverity.LOW
        assert "leverage_data" in review.data_gaps
        leverage = next(
            f for f in review.dimensions if f.dimension is RiskDimension.LEVERAGE
        )
        assert leverage.gap is True
        assert "Data Gap" in (leverage.note or "")

    def test_financial_anomaly_flag_is_critical(self) -> None:
        review = evaluate_risk_review(_observation(risk_flags=["fraud"]))
        assert review.risk_level is RiskSeverity.CRITICAL
        anomaly = next(
            f for f in review.dimensions if f.dimension is RiskDimension.FINANCIAL_ANOMALY
        )
        assert anomaly.triggered is True
        assert anomaly.severity is RiskSeverity.CRITICAL
        assert anomaly.evidence == ["fraud"]

    def test_any_critical_flag_escalates(self) -> None:
        for flag in ("investigation", "qualified_audit", "delisting", "negative_equity"):
            assert evaluate_risk_review(
                _observation(risk_flags=[flag])
            ).risk_level is RiskSeverity.CRITICAL

    def test_inquiry_is_medium(self) -> None:
        review = evaluate_risk_review(_observation(risk_flags=["inquiry"]))
        assert review.risk_level is RiskSeverity.MEDIUM

    def test_shareholder_reduction_is_medium(self) -> None:
        review = evaluate_risk_review(_observation(risk_flags=["shareholder_reduction"]))
        assert review.risk_level is RiskSeverity.MEDIUM
        shareholder = next(
            f for f in review.dimensions if f.dimension is RiskDimension.SHAREHOLDER
        )
        assert shareholder.triggered is True

    def test_cashflow_bands(self) -> None:
        assert evaluate_risk_review(
            _observation(operating_cashflow_to_profit=0.4)
        ).risk_level is RiskSeverity.HIGH
        assert evaluate_risk_review(
            _observation(operating_cashflow_to_profit=0.7)
        ).risk_level is RiskSeverity.MEDIUM
        assert evaluate_risk_review(
            _observation(operating_cashflow_to_profit=1.1)
        ).risk_level is RiskSeverity.LOW

    def test_profit_deterioration_bands(self) -> None:
        assert evaluate_risk_review(
            _observation(profit_growth_pct=-30.0)
        ).risk_level is RiskSeverity.HIGH
        assert evaluate_risk_review(
            _observation(profit_growth_pct=-10.0)
        ).risk_level is RiskSeverity.MEDIUM
        assert evaluate_risk_review(
            _observation(profit_growth_pct=-3.0)
        ).risk_level is RiskSeverity.LOW

    def test_negative_roe_is_high(self) -> None:
        review = evaluate_risk_review(_observation(roe_5y_median_pct=-2.0))
        assert review.risk_level is RiskSeverity.HIGH
        profitability = next(
            f for f in review.dimensions if f.dimension is RiskDimension.PROFITABILITY
        )
        assert profitability.triggered is True

    def test_profit_decline_announcement_flag_is_high(self) -> None:
        review = evaluate_risk_review(_observation(risk_flags=["profit_decline"]))
        assert review.risk_level is RiskSeverity.HIGH


class TestGaps:
    def test_missing_financials_are_explicit_gaps_not_silent(self) -> None:
        review = evaluate_risk_review({
            "security_type": "stock",
            "risk_flags": [],
            "risk_evidence": [],
            "roe_5y_median_pct": None,
            "operating_cashflow_to_profit": None,
            "profit_growth_pct": None,
        })
        assert "operating_cashflow_to_profit" in review.data_gaps
        assert "profit_growth_pct" in review.data_gaps
        assert "roe_5y_median_pct" in review.data_gaps
        cashflow = next(
            f for f in review.dimensions if f.dimension is RiskDimension.CASHFLOW
        )
        assert cashflow.gap is True
        assert any("缺口" in line for line in review.summary)

    def test_etf_without_issuer_financials_is_low_with_gaps(self) -> None:
        review = evaluate_risk_review({
            "security_type": "etf",
            "risk_flags": [],
            "risk_evidence": [],
            "roe_5y_median_pct": None,
            "operating_cashflow_to_profit": None,
            "profit_growth_pct": None,
        })
        assert review.risk_level is RiskSeverity.LOW
        assert review.data_gaps


class TestContractShape:
    def test_never_emits_trading_or_rating_directives(self) -> None:
        review = evaluate_risk_review(_observation(risk_flags=["fraud"]))
        serialized = review.model_dump()
        for key in ("action", "signal", "recommendation", "order", "buy", "sell", "rating", "score"):
            assert key not in serialized
        assert "非买入评级" in review.summary[-1]

    def test_deterministic_for_same_observation(self) -> None:
        observation = _observation(risk_flags=["fraud"], profit_growth_pct=-8.0)
        assert evaluate_risk_review(observation).model_dump() == evaluate_risk_review(observation).model_dump()

    def test_version_and_thresholds_are_frozen(self) -> None:
        config = RiskReviewConfig()
        assert config.version == RISK_REVIEW_VERSION
        assert config.cashflow_medium_ratio == 0.8
        assert config.cashflow_high_ratio == 0.5
        assert config.profit_decline_medium_pct == -5.0
        assert config.profit_decline_high_pct == -20.0

    def test_coverage_tracks_evaluated_and_triggered(self) -> None:
        review = evaluate_risk_review(_observation(risk_flags=["fraud"]))
        assert review.coverage["total"] == 5
        assert review.coverage["evaluated"] == 4
        assert review.coverage["triggered"] == 1

    def test_overall_level_is_max_finding_severity(self) -> None:
        review = evaluate_risk_review(_observation(
            risk_flags=["shareholder_reduction"],
            operating_cashflow_to_profit=0.4,
            profit_growth_pct=-30.0,
        ))
        assert review.risk_level is RiskSeverity.HIGH
