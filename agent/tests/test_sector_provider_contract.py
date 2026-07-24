"""B4 — Historical Sector Membership Contract tests."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.investment_research.sectors.models import (
    ClassificationStandard,
    SectorMembershipRecord,
    SectorProviderStatus,
)
from src.investment_research.sectors.fixture_provider import FixtureSectorMembershipProvider
from src.investment_research.sectors.error_providers import (
    UnconfiguredSectorProvider,
    UpstreamUnavailableSectorProvider,
    CurrentMembershipBackfillGuardProvider,
)
from src.investment_research.sectors.protocol import SectorMembershipProviderProtocol


class TestSectorMembershipRecord:
    def test_valid(self):
        m = SectorMembershipRecord(
            normalized_symbol="600519.SH", issuer_id="issuer_600519",
            sector_id="sector_baijiu", sector_name="白酒",
            classification_standard=ClassificationStandard.SW,
            effective_from=date(2001, 8, 27), effective_to=None,
            availability_time=datetime(2001, 8, 27, 15, 0, tzinfo=timezone.utc),
            source="test", membership_version="1.0",
        )
        assert m.sector_name == "白酒"

    def test_rejects_effective_from_after_to(self):
        with pytest.raises(ValueError):
            SectorMembershipRecord(
                normalized_symbol="600519.SH", issuer_id="issuer_600519",
                sector_id="sector_test", sector_name="Test",
                classification_standard=ClassificationStandard.CUSTOM,
                effective_from=date(2025, 6, 1), effective_to=date(2025, 1, 1),
                availability_time=datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="test", membership_version="1.0",
            )


class TestFixtureSectorMembershipProvider:
    def test_valid_members(self):
        p = FixtureSectorMembershipProvider()
        r = p.load(as_of=date(2025, 10, 31))
        assert r.status == SectorProviderStatus.FIXTURE
        assert len(r.memberships) >= 3

    def test_expired_membership(self):
        p = FixtureSectorMembershipProvider()
        # 300750.SZ was in battery sector until 2022-06-30
        r = p.load(as_of=date(2023, 1, 1))
        battery = [m for m in r.memberships if m.sector_id == "sector_battery"]
        assert len(battery) == 0

    def test_sector_change(self):
        p = FixtureSectorMembershipProvider()
        # After sector change, 300750 should be EV
        r = p.load(as_of=date(2023, 1, 1))
        ev = [m for m in r.memberships if m.sector_id == "sector_ev"]
        assert len(ev) == 1
        assert ev[0].normalized_symbol == "300750.SZ"

    def test_future_membership_rejected(self):
        p = FixtureSectorMembershipProvider()
        r = p.load(as_of=date(2000, 1, 1))
        assert len(r.memberships) == 0
        assert any("future" in g for g in r.data_gaps)

    def test_overlapping_memberships(self):
        p = FixtureSectorMembershipProvider()
        # Multiple classification standards overlap
        r = p.load(as_of=date(2023, 1, 1))
        symbols = {m.normalized_symbol for m in r.memberships}
        assert "002371.SZ" in symbols
        # Both SW and CITICS should be active
        standards = {m.classification_standard for m in r.memberships if m.normalized_symbol == "002371.SZ"}
        assert ClassificationStandard.SW in standards
        assert ClassificationStandard.CITICS in standards

    def test_classification_standard_change(self):
        p = FixtureSectorMembershipProvider()
        r = p.load(as_of=date(2025, 10, 31))
        standards = {m.classification_standard for m in r.memberships}
        assert len(standards) >= 2

    def test_no_current_backfill_for_history(self):
        p = FixtureSectorMembershipProvider()
        # Historical date before 300750 was listed
        r = p.load(as_of=date(2017, 1, 1))
        assert not any(m.normalized_symbol == "300750.SZ" for m in r.memberships)

    def test_deterministic(self):
        p = FixtureSectorMembershipProvider()
        r1 = p.load(as_of=date(2025, 10, 31))
        r2 = p.load(as_of=date(2025, 10, 31))
        assert len(r1.memberships) == len(r2.memberships)


class TestErrorStateProviders:
    @pytest.mark.parametrize("provider_cls,status", [
        (UnconfiguredSectorProvider, SectorProviderStatus.UNCONFIGURED),
        (UpstreamUnavailableSectorProvider, SectorProviderStatus.UPSTREAM_UNAVAILABLE),
        (CurrentMembershipBackfillGuardProvider, SectorProviderStatus.FIXTURE),
    ])
    def test_error_state(self, provider_cls, status):
        p = provider_cls()
        r = p.load(as_of=date(2025, 10, 31))
        assert r.status == status
        assert len(r.memberships) == 0

    def test_current_backfill_guard(self):
        p = CurrentMembershipBackfillGuardProvider()
        r = p.load(as_of=date(2025, 10, 31))
        assert any("backfill" in g for g in r.data_gaps)


class TestProtocolContract:
    def test_all_implement_protocol(self):
        providers = [
            FixtureSectorMembershipProvider(),
            UnconfiguredSectorProvider(),
            UpstreamUnavailableSectorProvider(),
            CurrentMembershipBackfillGuardProvider(),
        ]
        for p in providers:
            assert isinstance(p, SectorMembershipProviderProtocol)
            r = p.load(as_of=date(2025, 10, 31))
            assert r.as_of == date(2025, 10, 31)
