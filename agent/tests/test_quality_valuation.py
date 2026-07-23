from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.investment_research.valuation import (
    AssumptionStatus,
    CompanyQualityEngine,
    EvaluationStatus,
    FinancialObservation,
    ScenarioAssumption,
    ScenarioValuationEngine,
    ValuationAssumptions,
    ValuationMethod,
)


ASSET = "asset-fixture"
CUTOFF = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)


def _observation(year, revenue, profit, *, available=None, **overrides):
    return FinancialObservation(
        asset_id=ASSET,
        period_end=date(year, 12, 31),
        available_at=available or datetime(year + 1, 3, 31, tzinfo=timezone.utc),
        source="fixture-filing",
        revenue=Decimal(revenue),
        net_profit=Decimal(profit),
        gross_margin=Decimal(overrides.get("gross_margin", "0.40")),
        roe=Decimal(overrides.get("roe", "0.15")),
        operating_cash_flow=Decimal(overrides.get("cashflow", profit)),
        debt_ratio=Decimal(overrides.get("debt_ratio", "0.25")),
    )


def _assumptions(*, available_at=CUTOFF, status=AssumptionStatus.PROVISIONAL, approval=None):
    return ValuationAssumptions(
        asset_id=ASSET,
        current_price=Decimal("100"),
        current_eps=Decimal("5"),
        horizon_years=2,
        method=ValuationMethod.FORWARD_PE,
        scenarios=(
            ScenarioAssumption("bear", Decimal("-0.10"), Decimal("12")),
            ScenarioAssumption("base", Decimal("0.10"), Decimal("18")),
            ScenarioAssumption("bull", Decimal("0.20"), Decimal("24")),
        ),
        assumption_date=available_at.date(),
        available_at=available_at,
        assumption_version="fixture-v1",
        invalidation_conditions=("earnings assumptions no longer supported",),
        status=status,
        approval_reference=approval,
    )


def test_quality_metrics_are_deterministic_and_point_in_time():
    observations = [_observation(2023, "100", "10"), _observation(2024, "120", "12")]
    result = CompanyQualityEngine().assess(
        asset_id=ASSET,
        observations=observations,
        information_cutoff=CUTOFF,
    )
    assert result.status == EvaluationStatus.CONFIGURED
    assert result.metrics.revenue_growth == Decimal("0.20000000")
    assert result.metrics.profit_growth == Decimal("0.20000000")
    assert result.metrics.operating_cashflow_to_profit == Decimal("1.00000000")
    assert result.metrics.earnings_stability == Decimal("1.00000000")


def test_future_financial_data_does_not_change_current_metrics():
    current = [_observation(2023, "100", "10"), _observation(2024, "120", "12")]
    future = _observation(
        2025,
        "9999",
        "9999",
        available=CUTOFF + timedelta(days=1),
    )
    engine = CompanyQualityEngine()
    baseline = engine.assess(asset_id=ASSET, observations=current, information_cutoff=CUTOFF)
    contaminated = engine.assess(asset_id=ASSET, observations=[*current, future], information_cutoff=CUTOFF)
    assert contaminated.metrics == baseline.metrics
    assert contaminated.period_ends == baseline.period_ends
    assert "future_financial_observations_excluded" in contaminated.data_gaps


def test_missing_history_is_unconfigured():
    result = CompanyQualityEngine().assess(
        asset_id=ASSET,
        observations=[],
        information_cutoff=CUTOFF,
    )
    assert result.status == EvaluationStatus.UNCONFIGURED
    assert "point_in_time_financial_history" in result.data_gaps


def test_explicit_scenarios_are_reproducible_and_provisional():
    engine = ScenarioValuationEngine()
    first = engine.evaluate(asset_id=ASSET, information_cutoff=CUTOFF, assumptions=_assumptions())
    second = engine.evaluate(asset_id=ASSET, information_cutoff=CUTOFF, assumptions=_assumptions())
    assert first == second
    assert first.status == EvaluationStatus.PROVISIONAL
    values = {item.name: item.indicated_value for item in first.scenarios}
    assert values == {
        "bear": Decimal("48.60000000"),
        "base": Decimal("108.90000000"),
        "bull": Decimal("172.80000000"),
    }
    assert first.assumption_version == "fixture-v1"


def test_absent_or_future_assumptions_are_unconfigured():
    engine = ScenarioValuationEngine()
    absent = engine.evaluate(asset_id=ASSET, information_cutoff=CUTOFF, assumptions=None)
    future = engine.evaluate(
        asset_id=ASSET,
        information_cutoff=CUTOFF,
        assumptions=_assumptions(available_at=CUTOFF + timedelta(days=1)),
    )
    assert absent.status == EvaluationStatus.UNCONFIGURED
    assert future.status == EvaluationStatus.UNCONFIGURED
    assert future.scenarios == ()
    assert "future_valuation_assumptions_excluded" in future.data_gaps


def test_approved_assumptions_require_reference():
    with pytest.raises(ValueError, match="approval"):
        _assumptions(status=AssumptionStatus.APPROVED)
    approved = _assumptions(status=AssumptionStatus.APPROVED, approval="fixture-review-1")
    result = ScenarioValuationEngine().evaluate(
        asset_id=ASSET,
        information_cutoff=CUTOFF,
        assumptions=approved,
    )
    assert result.status == EvaluationStatus.CONFIGURED
