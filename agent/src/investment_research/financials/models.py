from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping


class FinancialProviderStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    PERMISSION_DENIED = "permission_denied"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    CONFIGURED = "configured"
    FIXTURE = "fixture"


class StatementType(StrEnum):
    ANNUAL = "annual"
    Q1 = "q1"
    INTERIM = "interim"
    Q3 = "q3"


@dataclass(frozen=True, slots=True)
class PointInTimeFinancialRecord:
    issuer_id: str
    normalized_symbol: str
    report_period: date
    statement_type: StatementType
    announcement_date: date
    available_at: datetime
    retrieved_at: datetime
    source: str
    source_record_id: str
    restatement_version: int
    currency: str
    revenue: Decimal | None = None
    net_profit: Decimal | None = None
    gross_margin: Decimal | None = None
    roe: Decimal | None = None
    operating_cash_flow: Decimal | None = None
    debt_ratio: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.issuer_id.strip() or not self.normalized_symbol.strip():
            raise ValueError("issuer_id and normalized_symbol are required")
        if not self.source.strip() or not self.source_record_id.strip():
            raise ValueError("source and source_record_id are required")
        if not self.currency.strip():
            raise ValueError("currency is required")
        if self.restatement_version < 0:
            raise ValueError("restatement_version must be non-negative")
        _require_aware(self.available_at, "available_at")
        _require_aware(self.retrieved_at, "retrieved_at")
        if self.announcement_date > self.available_at.date():
            raise ValueError("announcement_date cannot follow available_at")
        if self.retrieved_at < self.available_at:
            raise ValueError("retrieved_at cannot precede available_at")
        if self.report_period > self.announcement_date:
            raise ValueError("report_period cannot follow announcement_date")


@dataclass(frozen=True, slots=True)
class FinancialProviderResult:
    status: FinancialProviderStatus
    records: tuple[PointInTimeFinancialRecord, ...]
    as_of: date
    data_gaps: tuple[str, ...]
    errors: tuple[str, ...]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
