"""Deterministic point-in-time quality and scenario valuation engines."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext
from typing import Sequence

from .models import (
    AssumptionStatus,
    EvaluationStatus,
    FinancialObservation,
    QualityAssessment,
    QualityMetrics,
    ScenarioValuation,
    ScenarioValuationResult,
    ValuationAssumptions,
)


class CompanyQualityEngine:
    def assess(
        self,
        *,
        asset_id: str,
        observations: Sequence[FinancialObservation],
        information_cutoff: datetime,
    ) -> QualityAssessment:
        _require_aware(information_cutoff)
        eligible = sorted(
            (
                item
                for item in observations
                if item.asset_id == asset_id
                and item.period_end <= information_cutoff.date()
                and item.available_at <= information_cutoff
            ),
            key=lambda item: (item.period_end, item.available_at, item.source),
        )
        gaps: list[str] = []
        if any(
            item.asset_id == asset_id
            and (item.period_end > information_cutoff.date() or item.available_at > information_cutoff)
            for item in observations
        ):
            gaps.append("future_financial_observations_excluded")
        if not eligible:
            return QualityAssessment(
                asset_id=asset_id,
                information_cutoff=information_cutoff,
                status=EvaluationStatus.UNCONFIGURED,
                observation_count=0,
                metrics=QualityMetrics(None, None, None, None, None, None, None, None),
                period_ends=(),
                data_gaps=tuple((*gaps, "point_in_time_financial_history")),
            )

        first, latest = eligible[0], eligible[-1]
        metrics = QualityMetrics(
            revenue_growth=_growth(first.revenue, latest.revenue),
            profit_growth=_growth(first.net_profit, latest.net_profit),
            gross_margin=latest.gross_margin,
            gross_margin_change=_difference(first.gross_margin, latest.gross_margin),
            roe=latest.roe,
            operating_cashflow_to_profit=_ratio(latest.operating_cash_flow, latest.net_profit),
            debt_ratio=latest.debt_ratio,
            earnings_stability=_earnings_stability(eligible),
        )
        for field_name in QualityMetrics.__dataclass_fields__:
            value = getattr(metrics, field_name)
            if value is None:
                gaps.append(field_name)
        status = EvaluationStatus.CONFIGURED if not gaps else EvaluationStatus.PARTIAL
        return QualityAssessment(
            asset_id=asset_id,
            information_cutoff=information_cutoff,
            status=status,
            observation_count=len(eligible),
            metrics=metrics,
            period_ends=tuple(item.period_end for item in eligible),
            data_gaps=tuple(dict.fromkeys(gaps)),
        )


class ScenarioValuationEngine:
    def evaluate(
        self,
        *,
        asset_id: str,
        information_cutoff: datetime,
        assumptions: ValuationAssumptions | None,
    ) -> ScenarioValuationResult:
        _require_aware(information_cutoff)
        if assumptions is None:
            return _unconfigured(asset_id, information_cutoff, "valuation_assumptions")
        if assumptions.asset_id != asset_id:
            raise ValueError("valuation assumptions reference a different asset")
        if (
            assumptions.assumption_date > information_cutoff.date()
            or assumptions.available_at > information_cutoff
        ):
            return _unconfigured(asset_id, information_cutoff, "future_valuation_assumptions_excluded")

        valuations: list[ScenarioValuation] = []
        with localcontext() as context:
            context.prec = 28
            for scenario in assumptions.scenarios:
                future_eps = assumptions.current_eps * (
                    Decimal("1") + scenario.annual_earnings_growth
                ) ** assumptions.horizon_years
                indicated = future_eps * scenario.terminal_multiple
                upside = indicated / assumptions.current_price - Decimal("1")
                valuations.append(
                    ScenarioValuation(
                        name=scenario.name,
                        future_eps=_quantize(future_eps),
                        indicated_value=_quantize(indicated),
                        upside=_quantize(upside),
                    )
                )
        if not (
            valuations[0].indicated_value
            <= valuations[1].indicated_value
            <= valuations[2].indicated_value
        ):
            raise ValueError("bear/base/bull indicated values must be monotonic")
        status = (
            EvaluationStatus.CONFIGURED
            if assumptions.status == AssumptionStatus.APPROVED
            else EvaluationStatus.PROVISIONAL
        )
        return ScenarioValuationResult(
            asset_id=asset_id,
            information_cutoff=information_cutoff,
            status=status,
            method=assumptions.method,
            assumption_version=assumptions.assumption_version,
            assumption_date=assumptions.assumption_date,
            scenarios=tuple(valuations),
            invalidation_conditions=assumptions.invalidation_conditions,
            data_gaps=(),
        )


def _growth(first: Decimal | None, latest: Decimal | None) -> Decimal | None:
    if first is None or latest is None or first <= 0:
        return None
    return _quantize(latest / first - Decimal("1"))


def _difference(first: Decimal | None, latest: Decimal | None) -> Decimal | None:
    if first is None or latest is None:
        return None
    return _quantize(latest - first)


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _quantize(numerator / denominator)


def _earnings_stability(observations: Sequence[FinancialObservation]) -> Decimal | None:
    values = [item.net_profit for item in observations if item.net_profit is not None]
    if not values:
        return None
    positive = sum(value > 0 for value in values)
    return _quantize(Decimal(positive) / Decimal(len(values)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"))


def _unconfigured(
    asset_id: str,
    information_cutoff: datetime,
    gap: str,
) -> ScenarioValuationResult:
    return ScenarioValuationResult(
        asset_id=asset_id,
        information_cutoff=information_cutoff,
        status=EvaluationStatus.UNCONFIGURED,
        method=None,
        assumption_version=None,
        assumption_date=None,
        scenarios=(),
        invalidation_conditions=(),
        data_gaps=(gap,),
    )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("information_cutoff must be timezone-aware")
