from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from .models import (
    FinancialProviderResult,
    FinancialProviderStatus,
    PointInTimeFinancialRecord,
    StatementType,
)
from .protocol import FinancialProviderProtocol


class FixtureFinancialProvider(FinancialProviderProtocol):
    """Fixture financial provider returning canned data for 002371.SZ.

    All records have point-in-time metadata.  Reports are available only
    after their announcement date.  Every field is set to a deterministic
    value so that tests are repeatable.

    Not intended for production use — no real network calls are made.
    """

    provider_name = "fixture_financial"
    status = FinancialProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> FinancialProviderResult:
        gaps: list[str] = []
        errors: list[str] = []
        records: list[PointInTimeFinancialRecord] = []

        base = as_of
        for i, (period_end, ann_date, stmt_type) in enumerate(
            [
                (date(2024, 12, 31), date(2025, 4, 25), StatementType.ANNUAL),
                (date(2025, 3, 31), date(2025, 4, 29), StatementType.Q1),
                (date(2025, 6, 30), date(2025, 8, 28), StatementType.INTERIM),
                (date(2025, 9, 30), date(2025, 10, 28), StatementType.Q3),
            ]
        ):
            if ann_date > as_of:
                gaps.append(f"future_record: {stmt_type.value}_{period_end.isoformat()}")
                continue
            if period_end > as_of:
                gaps.append(f"future_period: {stmt_type.value}_{period_end.isoformat()}")
                continue
            available = datetime(ann_date.year, ann_date.month, ann_date.day, 18, 0, tzinfo=timezone.utc)
            if available > datetime(as_of.year, as_of.month, as_of.day, 23, 59, tzinfo=timezone.utc):
                continue
            records.append(
                PointInTimeFinancialRecord(
                    issuer_id="issuer_002371",
                    normalized_symbol="002371.SZ",
                    report_period=period_end,
                    statement_type=stmt_type,
                    announcement_date=ann_date,
                    available_at=available,
                    retrieved_at=available + timedelta(hours=1),
                    source="fixture_financial",
                    source_record_id=f"fixture-002371-{stmt_type.value}-{period_end.isoformat()}",
                    restatement_version=0,
                    currency="CNY",
                    revenue=Decimal("10000000000") * (1 + i * Decimal("0.05")),
                    net_profit=Decimal("1500000000") * (1 + i * Decimal("0.08")),
                    gross_margin=Decimal("0.42"),
                    roe=Decimal("0.15"),
                    operating_cash_flow=Decimal("1800000000") * (1 + i * Decimal("0.03")),
                    debt_ratio=Decimal("0.35"),
                )
            )

        return FinancialProviderResult(
            status=FinancialProviderStatus.FIXTURE,
            records=tuple(records),
            as_of=as_of,
            data_gaps=tuple(gaps),
            errors=tuple(errors),
        )
