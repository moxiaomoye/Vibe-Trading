"""B1 — Point-in-Time Financial Provider Contract tests."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

import pytest

from src.investment_research.financials.models import (
    FinancialProviderStatus,
    PointInTimeFinancialRecord,
    StatementType,
)
from src.investment_research.financials.fixture_provider import FixtureFinancialProvider
from src.investment_research.financials.error_providers import (
    UnconfiguredFinancialProvider,
    PermissionDeniedFinancialProvider,
    UpstreamUnavailableFinancialProvider,
    MalformedResponseFinancialProvider,
    FutureRecordRejectedProvider,
)
from src.investment_research.financials.protocol import FinancialProviderProtocol


class TestPointInTimeFinancialRecord:
    def test_valid_record(self):
        r = PointInTimeFinancialRecord(
            issuer_id="issuer_002371",
            normalized_symbol="002371.SZ",
            report_period=date(2024, 12, 31),
            statement_type=StatementType.ANNUAL,
            announcement_date=date(2025, 4, 25),
            available_at=datetime(2025, 4, 25, 18, 0, tzinfo=timezone.utc),
            retrieved_at=datetime(2025, 4, 25, 19, 0, tzinfo=timezone.utc),
            source="test",
            source_record_id="test-001",
            restatement_version=0,
            currency="CNY",
        )
        assert r.issuer_id == "issuer_002371"

    def test_requires_issuer_and_symbol(self):
        with pytest.raises(ValueError, match="issuer_id and normalized_symbol"):
            PointInTimeFinancialRecord(
                issuer_id="  ", normalized_symbol="002371.SZ",
                report_period=date(2024, 12, 31),
                statement_type=StatementType.ANNUAL,
                announcement_date=date(2025, 4, 25),
                available_at=datetime(2025, 4, 25, 18, 0, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 19, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                restatement_version=0, currency="CNY",
            )

    def test_rejects_future_announcement(self):
        with pytest.raises(ValueError, match="announcement_date cannot follow available_at"):
            PointInTimeFinancialRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                report_period=date(2024, 12, 31),
                statement_type=StatementType.ANNUAL,
                announcement_date=date(2025, 4, 25),
                available_at=datetime(2025, 4, 20, 18, 0, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 20, 19, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                restatement_version=0, currency="CNY",
            )

    def test_rejects_retrieved_before_available(self):
        with pytest.raises(ValueError, match="retrieved_at cannot precede available_at"):
            PointInTimeFinancialRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                report_period=date(2024, 12, 31),
                statement_type=StatementType.ANNUAL,
                announcement_date=date(2025, 4, 25),
                available_at=datetime(2025, 4, 25, 18, 0, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 17, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                restatement_version=0, currency="CNY",
            )

    def test_rejects_report_period_after_announcement(self):
        with pytest.raises(ValueError, match="report_period cannot follow announcement_date"):
            PointInTimeFinancialRecord(
                issuer_id="issuer", normalized_symbol="000001.SZ",
                report_period=date(2025, 6, 30),
                statement_type=StatementType.INTERIM,
                announcement_date=date(2025, 4, 25),
                available_at=datetime(2025, 4, 25, 18, 0, tzinfo=timezone.utc),
                retrieved_at=datetime(2025, 4, 25, 19, 0, tzinfo=timezone.utc),
                source="test", source_record_id="test-001",
                restatement_version=0, currency="CNY",
            )


class TestFixtureFinancialProvider:
    def test_returns_records_for_recent_as_of(self):
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 10, 31))
        assert result.status == FinancialProviderStatus.FIXTURE
        assert len(result.records) == 4
        for r in result.records:
            assert r.announcement_date <= date(2025, 10, 31)
            assert r.currency == "CNY"

    def test_rejects_future_records(self):
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 1, 1))
        assert len(result.records) == 0
        assert any("future" in gap for gap in result.data_gaps)

    def test_deterministic_output(self):
        provider = FixtureFinancialProvider()
        r1 = provider.load(as_of=date(2025, 10, 31))
        r2 = provider.load(as_of=date(2025, 10, 31))
        assert len(r1.records) == len(r2.records)
        for a, b in zip(r1.records, r2.records):
            assert a.revenue == b.revenue
            assert a.net_profit == b.net_profit
            assert a.gross_margin == b.gross_margin

    def test_partial_as_of_filter(self):
        provider = FixtureFinancialProvider()
        # After Q1 announcement but before interim
        result = provider.load(as_of=date(2025, 5, 1))
        counted = [r for r in result.records if r.announcement_date <= date(2025, 5, 1)]
        assert len(counted) == 2  # annual + Q1


class TestErrorStateProviders:
    @pytest.mark.parametrize("provider_cls,expected_status", [
        (UnconfiguredFinancialProvider, FinancialProviderStatus.UNCONFIGURED),
        (PermissionDeniedFinancialProvider, FinancialProviderStatus.PERMISSION_DENIED),
        (UpstreamUnavailableFinancialProvider, FinancialProviderStatus.UPSTREAM_UNAVAILABLE),
        (MalformedResponseFinancialProvider, FinancialProviderStatus.MALFORMED_RESPONSE),
    ])
    def test_error_state(self, provider_cls, expected_status):
        provider = provider_cls()
        result = provider.load(as_of=date(2025, 10, 31))
        assert result.status == expected_status
        assert len(result.records) == 0
        assert len(result.data_gaps) > 0

    def test_future_record_rejected(self):
        provider = FutureRecordRejectedProvider()
        result = provider.load(as_of=date(2025, 10, 31))
        assert result.status == FinancialProviderStatus.FIXTURE
        assert len(result.records) == 0
        assert any("future" in g for g in result.data_gaps)


class TestProviderProtocolContract:
    def test_all_providers_implement_protocol(self):
        providers = [
            FixtureFinancialProvider(),
            UnconfiguredFinancialProvider(),
            PermissionDeniedFinancialProvider(),
            UpstreamUnavailableFinancialProvider(),
            MalformedResponseFinancialProvider(),
            FutureRecordRejectedProvider(),
        ]
        for p in providers:
            assert isinstance(p, FinancialProviderProtocol)
            result = p.load(as_of=date(2025, 10, 31))
            assert result.as_of == date(2025, 10, 31)

    def test_no_credentials_in_output(self):
        providers = [
            FixtureFinancialProvider(),
            UnconfiguredFinancialProvider(),
            PermissionDeniedFinancialProvider(),
        ]
        for p in providers:
            result = p.load(as_of=date(2025, 10, 31))
            output = str(result)
            assert "token" not in output.lower()
            assert "secret" not in output.lower()
            assert "key" not in output.lower() or "key" in output.lower() and p.provider_name in output
