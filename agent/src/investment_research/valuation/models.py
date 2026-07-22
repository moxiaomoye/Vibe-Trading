"""Point-in-time company quality and explicit scenario-valuation models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class EvaluationStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    PARTIAL = "partial"
    PROVISIONAL = "provisional"
    CONFIGURED = "configured"


class AssumptionStatus(StrEnum):
    PROVISIONAL = "provisional"
    APPROVED = "approved"


class ValuationMethod(StrEnum):
    FORWARD_PE = "forward_pe"


@dataclass(frozen=True, slots=True)
class FinancialObservation:
    asset_id: str
    period_end: date
    available_at: datetime
    source: str
    revenue: Decimal | None = None
    net_profit: Decimal | None = None
    gross_margin: Decimal | None = None
    roe: Decimal | None = None
    operating_cash_flow: Decimal | None = None
    debt_ratio: Decimal | None = None

    def __post_init__(self) -> None:
        _require_aware(self.available_at, "available_at")
        if not self.asset_id.strip() or not self.source.strip():
            raise ValueError("financial observation identity and source are required")
        if self.period_end > self.available_at.date():
            raise ValueError("financial period cannot end after information availability")
        for field_name in ("gross_margin", "roe", "debt_ratio"):
            value = getattr(self, field_name)
            if value is not None and not Decimal("-1") <= value <= Decimal("1"):
                raise ValueError(f"{field_name} must be expressed as a decimal ratio")


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    revenue_growth: Decimal | None
    profit_growth: Decimal | None
    gross_margin: Decimal | None
    gross_margin_change: Decimal | None
    roe: Decimal | None
    operating_cashflow_to_profit: Decimal | None
    debt_ratio: Decimal | None
    earnings_stability: Decimal | None


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    asset_id: str
    information_cutoff: datetime
    status: EvaluationStatus
    observation_count: int
    metrics: QualityMetrics
    period_ends: tuple[date, ...]
    data_gaps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenarioAssumption:
    name: str
    annual_earnings_growth: Decimal
    terminal_multiple: Decimal

    def __post_init__(self) -> None:
        if self.name not in {"bear", "base", "bull"}:
            raise ValueError("scenario name must be bear, base, or bull")
        if self.annual_earnings_growth <= Decimal("-1"):
            raise ValueError("annual earnings growth must be greater than -100%")
        if self.terminal_multiple <= 0:
            raise ValueError("terminal multiple must be positive")


@dataclass(frozen=True, slots=True)
class ValuationAssumptions:
    asset_id: str
    current_price: Decimal
    current_eps: Decimal
    horizon_years: int
    method: ValuationMethod
    scenarios: tuple[ScenarioAssumption, ...]
    assumption_date: date
    available_at: datetime
    assumption_version: str
    invalidation_conditions: tuple[str, ...]
    status: AssumptionStatus = AssumptionStatus.PROVISIONAL
    approval_reference: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.available_at, "available_at")
        if not self.asset_id.strip() or not self.assumption_version.strip():
            raise ValueError("valuation asset and assumption version are required")
        if self.current_price <= 0 or self.current_eps <= 0:
            raise ValueError("current price and EPS must be positive")
        if self.horizon_years < 1:
            raise ValueError("valuation horizon must be positive")
        if self.assumption_date > self.available_at.date():
            raise ValueError("assumption date cannot follow availability")
        if tuple(item.name for item in self.scenarios) != ("bear", "base", "bull"):
            raise ValueError("scenarios must be ordered bear, base, bull")
        if not self.invalidation_conditions:
            raise ValueError("valuation assumptions require invalidation conditions")
        if self.status == AssumptionStatus.APPROVED and not (self.approval_reference or "").strip():
            raise ValueError("approved assumptions require an approval reference")


@dataclass(frozen=True, slots=True)
class ScenarioValuation:
    name: str
    future_eps: Decimal
    indicated_value: Decimal
    upside: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioValuationResult:
    asset_id: str
    information_cutoff: datetime
    status: EvaluationStatus
    method: ValuationMethod | None
    assumption_version: str | None
    assumption_date: date | None
    scenarios: tuple[ScenarioValuation, ...]
    invalidation_conditions: tuple[str, ...]
    data_gaps: tuple[str, ...]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
