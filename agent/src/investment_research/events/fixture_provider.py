from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from .models import (
    EventProviderResult,
    EventProviderStatus,
    EventType,
    PointInTimeEventRecord,
)
from .protocol import EventProviderProtocol


class FixtureEventProvider(EventProviderProtocol):
    """Fixture event provider with diverse event scenarios.

    Includes: company announcement, adverse event, industry event,
    market systemic event, and mixed scenarios.
    """

    provider_name = "fixture_event"
    status = EventProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> EventProviderResult:
        gaps: list[str] = []
        errors: list[str] = []
        records: list[PointInTimeEventRecord] = []

        scenarios = [
            # company announcement
            PointInTimeEventRecord(
                issuer_id="issuer_002371",
                normalized_symbol="002371.SZ",
                event_type=EventType.COMPANY_ANNOUNCEMENT,
                headline="002371.SZ 发布2024年度报告",
                occurrence_time=datetime(2025, 4, 25, 12, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
                availability_time=datetime(2025, 4, 25, 14, 5, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 15, 0, tzinfo=timezone.utc),
                source="fixture_announcement",
                source_record_id="fixture-ann-001",
                source_url="https://fixture.example.com/ann/001",
                body_available=True,
                parser_version="1.0.0",
                confidence=Decimal("0.95"),
                normalized_facts=("revenue_10b", "net_profit_1.5b"),
            ),
            # adverse event
            PointInTimeEventRecord(
                issuer_id="issuer_600522",
                normalized_symbol="600522.SH",
                event_type=EventType.ADVERSE_EVENT,
                headline="600522.SH 收到证监会调查通知书",
                occurrence_time=datetime(2025, 6, 15, 9, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc),
                availability_time=datetime(2025, 6, 15, 10, 35, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc),
                source="fixture_announcement",
                source_record_id="fixture-ann-002",
                source_url="https://fixture.example.com/ann/002",
                body_available=True,
                parser_version="1.0.0",
                confidence=Decimal("0.90"),
                normalized_facts=("regulatory_investigation",),
            ),
            # industry event
            PointInTimeEventRecord(
                issuer_id="issuer_300750",
                normalized_symbol="300750.SZ",
                event_type=EventType.INDUSTRY_EVENT,
                headline="动力电池行业新国标发布",
                occurrence_time=datetime(2025, 7, 1, 8, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 7, 1, 9, 0, tzinfo=timezone.utc),
                availability_time=datetime(2025, 7, 1, 9, 5, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc),
                source="fixture_news",
                source_record_id="fixture-ind-001",
                source_url="https://fixture.example.com/industry/001",
                body_available=False,
                parser_version="1.0.0",
                confidence=Decimal("0.70"),
                normalized_facts=("new_standard_published",),
            ),
            # market systemic event
            PointInTimeEventRecord(
                issuer_id="",
                normalized_symbol="",
                event_type=EventType.MARKET_SYSTEMIC,
                headline="全球市场大幅波动 主要指数下跌超过5%",
                occurrence_time=datetime(2025, 8, 5, 2, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 8, 5, 2, 15, tzinfo=timezone.utc),
                availability_time=datetime(2025, 8, 5, 2, 20, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 8, 5, 3, 0, tzinfo=timezone.utc),
                source="fixture_macro",
                source_record_id="fixture-macro-001",
                source_url="https://fixture.example.com/macro/001",
                body_available=True,
                parser_version="1.0.0",
                confidence=Decimal("0.85"),
                normalized_facts=("market_correction", "panic_selling"),
            ),
        ]

        for record in scenarios:
            if record.availability_time.date() > as_of:
                gaps.append(f"future_event: {record.source_record_id}")
                continue
            records.append(record)

        return EventProviderResult(
            status=EventProviderStatus.FIXTURE,
            records=tuple(records),
            as_of=as_of,
            data_gaps=tuple(gaps),
            errors=tuple(errors),
        )
