"""B2 — Point-in-Time Announcement/Event Provider Contract tests."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.investment_research.events.models import (
    EventProviderStatus,
    EventType,
    PointInTimeEventRecord,
)
from src.investment_research.events.fixture_provider import FixtureEventProvider
from src.investment_research.events.fixture_restatement_provider import (
    FixtureRestatementEventProvider,
)
from src.investment_research.events.error_providers import (
    UnconfiguredEventProvider,
    PermissionDeniedEventProvider,
    UpstreamUnavailableEventProvider,
    MalformedResponseEventProvider,
    FuturePublicationRejectedProvider,
)
from src.investment_research.events.protocol import EventProviderProtocol


class TestPointInTimeEventRecord:
    def test_valid_record(self):
        r = PointInTimeEventRecord(
            issuer_id="issuer_002371",
            normalized_symbol="002371.SZ",
            event_type=EventType.COMPANY_ANNOUNCEMENT,
            headline="Test announcement",
            occurrence_time=datetime(2025, 4, 25, 12, 0, tzinfo=timezone.utc),
            publication_time=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
            availability_time=datetime(2025, 4, 25, 14, 5, tzinfo=timezone.utc),
            retrieved_at=datetime(2025, 4, 25, 15, 0, tzinfo=timezone.utc),
            source="test",
            source_record_id="test-001",
            source_url="https://example.com/ann",
            body_available=True,
            parser_version="1.0.0",
            confidence=Decimal("0.95"),
        )
        assert r.event_type == EventType.COMPANY_ANNOUNCEMENT

    def test_rejects_occurrence_after_publication(self):
        with pytest.raises(ValueError, match="occurrence cannot follow publication"):
            PointInTimeEventRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                event_type=EventType.NEWS_ARTICLE,
                headline="test",
                occurrence_time=datetime(2025, 4, 25, 15, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
                availability_time=datetime(2025, 4, 25, 14, 5, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 15, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                source_url="https://example.com",
                body_available=True, parser_version="1.0.0",
                confidence=Decimal("0.95"),
            )

    def test_rejects_publication_after_availability(self):
        with pytest.raises(ValueError, match="publication cannot follow availability"):
            PointInTimeEventRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                event_type=EventType.NEWS_ARTICLE,
                headline="test",
                occurrence_time=datetime(2025, 4, 25, 12, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 4, 25, 14, 5, tzinfo=timezone.utc),
                availability_time=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 15, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                source_url="https://example.com",
                body_available=True, parser_version="1.0.0",
                confidence=Decimal("0.95"),
            )

    def test_rejects_retrieved_before_availability(self):
        with pytest.raises(ValueError, match="retrieved_at cannot precede availability_time"):
            PointInTimeEventRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                event_type=EventType.NEWS_ARTICLE,
                headline="test",
                occurrence_time=datetime(2025, 4, 25, 12, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
                availability_time=datetime(2025, 4, 25, 14, 5, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                source_url="https://example.com",
                body_available=True, parser_version="1.0.0",
                confidence=Decimal("0.95"),
            )

    def test_rejects_credentials_in_url(self):
        with pytest.raises(ValueError, match="source_url must not contain credentials"):
            PointInTimeEventRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                event_type=EventType.NEWS_ARTICLE,
                headline="test",
                occurrence_time=datetime(2025, 4, 25, 12, 0, tzinfo=timezone.utc),
                publication_time=datetime(2025, 4, 25, 14, 0, tzinfo=timezone.utc),
                availability_time=datetime(2025, 4, 25, 14, 5, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 15, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                source_url="https://user:pass@api.example.com/ann",
                body_available=True, parser_version="1.0.0",
                confidence=Decimal("0.95"),
            )

    def test_missing_body_marked(self):
        r = PointInTimeEventRecord(
            issuer_id="issuer_300750", normalized_symbol="300750.SZ",
            event_type=EventType.INDUSTRY_EVENT,
            headline="Industry event",
            occurrence_time=datetime(2025, 7, 1, 8, 0, tzinfo=timezone.utc),
            publication_time=datetime(2025, 7, 1, 9, 0, tzinfo=timezone.utc),
            availability_time=datetime(2025, 7, 1, 9, 5, tzinfo=timezone.utc),
            retrieved_at=datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc),
            source="test", source_record_id="test-002",
            source_url="https://example.com/ind",
            body_available=False, parser_version="1.0.0",
            confidence=Decimal("0.70"),
        )
        assert not r.body_available


class TestFixtureEventProvider:
    def test_returns_events_for_recent_as_of(self):
        provider = FixtureEventProvider()
        result = provider.load(as_of=date(2025, 10, 31))
        assert result.status == EventProviderStatus.FIXTURE
        assert len(result.records) >= 3

    def test_rejects_future_publications(self):
        provider = FixtureEventProvider()
        result = provider.load(as_of=date(2025, 1, 1))
        assert any("future" in gap for gap in result.data_gaps)

    def test_deterministic_output(self):
        provider = FixtureEventProvider()
        r1 = provider.load(as_of=date(2025, 10, 31))
        r2 = provider.load(as_of=date(2025, 10, 31))
        assert len(r1.records) == len(r2.records)


class TestRestatementProvider:
    def test_original_available_before_correction(self):
        provider = FixtureRestatementEventProvider()
        # After original, before correction
        result = provider.load(as_of=date(2025, 3, 31))
        records = [r for r in result.records if r.source_record_id.startswith("fixture-ann-restate")]
        assert any("v0" in r.source_record_id for r in records)
        assert not any("v1" in r.source_record_id for r in records)

    def test_correction_available_after_publication(self):
        provider = FixtureRestatementEventProvider()
        result = provider.load(as_of=date(2025, 5, 1))
        records = [r for r in result.records if r.source_record_id.startswith("fixture-ann-restate")]
        assert len(records) == 2


class TestErrorStateProviders:
    @pytest.mark.parametrize("provider_cls,expected_status", [
        (UnconfiguredEventProvider, EventProviderStatus.UNCONFIGURED),
        (PermissionDeniedEventProvider, EventProviderStatus.PERMISSION_DENIED),
        (UpstreamUnavailableEventProvider, EventProviderStatus.UPSTREAM_UNAVAILABLE),
        (MalformedResponseEventProvider, EventProviderStatus.MALFORMED_RESPONSE),
    ])
    def test_error_state(self, provider_cls, expected_status):
        provider = provider_cls()
        result = provider.load(as_of=date(2025, 10, 31))
        assert result.status == expected_status
        assert len(result.records) == 0

    def test_future_publication_rejected(self):
        provider = FuturePublicationRejectedProvider()
        result = provider.load(as_of=date(2025, 10, 31))
        assert any("future" in g for g in result.data_gaps)


class TestProviderProtocolContract:
    def test_all_providers_implement_protocol(self):
        providers = [
            FixtureEventProvider(),
            FixtureRestatementEventProvider(),
            UnconfiguredEventProvider(),
            PermissionDeniedEventProvider(),
            UpstreamUnavailableEventProvider(),
            MalformedResponseEventProvider(),
            FuturePublicationRejectedProvider(),
        ]
        for p in providers:
            assert isinstance(p, EventProviderProtocol)
            result = p.load(as_of=date(2025, 10, 31))
            assert result.as_of == date(2025, 10, 31)

    def test_no_credentials_in_output(self):
        providers = [
            FixtureEventProvider(),
            UnconfiguredEventProvider(),
        ]
        for p in providers:
            result = p.load(as_of=date(2025, 10, 31))
            for r in result.records:
                assert "@" not in r.source_url or "://" not in r.source_url
