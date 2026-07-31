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


class FixtureRestatementEventProvider(EventProviderProtocol):
    """Fixture provider that emits a correction announcement.

    Used to test that corrected announcements do not retroactively
    change historical evaluations.
    """

    provider_name = "fixture_restatement_event"
    status = EventProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> EventProviderResult:
        gaps: list[str] = []
        records: list[PointInTimeEventRecord] = []

        # Original announcement
        original = PointInTimeEventRecord(
            issuer_id="issuer_002371",
            normalized_symbol="002371.SZ",
            event_type=EventType.COMPANY_ANNOUNCEMENT,
            headline="002371.SZ 2024年净利润初步数据",
            occurrence_time=datetime(2025, 3, 15, 12, 0, tzinfo=timezone.utc),
            publication_time=datetime(2025, 3, 15, 14, 0, tzinfo=timezone.utc),
            availability_time=datetime(2025, 3, 15, 14, 5, tzinfo=timezone.utc),
            retrieved_at=datetime(2025, 3, 15, 15, 0, tzinfo=timezone.utc),
            source="fixture_announcement",
            source_record_id="fixture-ann-restate-v0",
            source_url="https://fixture.example.com/ann/restate/v0",
            body_available=True,
            parser_version="1.0.0",
            confidence=Decimal("0.90"),
            normalized_facts=("net_profit_preliminary_1.4b",),
        )

        # Corrected announcement (issued later)
        corrected = PointInTimeEventRecord(
            issuer_id="issuer_002371",
            normalized_symbol="002371.SZ",
            event_type=EventType.COMPANY_ANNOUNCEMENT,
            headline="002371.SZ 2024年净利润修正数据",
            occurrence_time=datetime(2025, 4, 10, 12, 0, tzinfo=timezone.utc),
            publication_time=datetime(2025, 4, 10, 14, 0, tzinfo=timezone.utc),
            availability_time=datetime(2025, 4, 10, 14, 5, tzinfo=timezone.utc),
            retrieved_at=datetime(2025, 4, 10, 15, 0, tzinfo=timezone.utc),
            source="fixture_announcement",
            source_record_id="fixture-ann-restate-v1",
            source_url="https://fixture.example.com/ann/restate/v1",
            body_available=True,
            parser_version="1.0.0",
            confidence=Decimal("0.95"),
            normalized_facts=("net_profit_corrected_1.5b",),
        )

        for record in [original, corrected]:
            if record.availability_time.date() > as_of:
                gaps.append(f"future_event: {record.source_record_id}")
                continue
            records.append(record)

        return EventProviderResult(
            status=EventProviderStatus.FIXTURE,
            records=tuple(records),
            as_of=as_of,
            data_gaps=tuple(gaps),
            errors=(),
        )
