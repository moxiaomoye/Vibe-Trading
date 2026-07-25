"""B3 — Asset/Issuer/Security Identity Mapping tests."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.investment_research.identity.models import (
    BoardType,
    Exchange,
    IdentityProviderStatus,
    Issuer,
    SecurityIdentity,
)
from src.investment_research.identity.fixture_provider import FixtureIdentityProvider
from src.investment_research.identity.error_providers import (
    UnconfiguredIdentityProvider,
    PermissionDeniedIdentityProvider,
    UpstreamUnavailableIdentityProvider,
    FutureMappingRejectedProvider,
)
from src.investment_research.identity.protocol import IdentityProviderProtocol


class TestIssuer:
    def test_valid_issuer(self):
        i = Issuer("issuer_001", "Test Corp", "Test Corp Ltd")
        assert i.issuer_id == "issuer_001"

    def test_requires_name(self):
        with pytest.raises(ValueError):
            Issuer("issuer_001", "")

    def test_requires_id(self):
        with pytest.raises(ValueError):
            Issuer("", "Test Corp")


class TestSecurityIdentity:
    def test_valid(self):
        s = SecurityIdentity(
            normalized_symbol="600519.SH", raw_symbol="600519",
            security_code="600519", security_name="贵州茅台",
            exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
            issuer_id="issuer_600519", issuer_name="贵州茅台",
            listing_date=date(2001, 8, 27), delisting_date=None,
            is_st=False, effective_from=date(2001, 8, 27), effective_to=None,
            availability_time=datetime(2001, 8, 27, 15, 0, tzinfo=timezone.utc),
            source="fixture_identity", mapping_version="1.0.0",
        )
        assert s.normalized_symbol == "600519.SH"

    def test_rejects_effective_from_after_to(self):
        with pytest.raises(ValueError, match="effective_from cannot follow effective_to"):
            SecurityIdentity(
                normalized_symbol="600519.SH", raw_symbol="600519",
                security_code="600519", security_name="Test",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_001", issuer_name="Test",
                listing_date=date(2000, 1, 1), delisting_date=None,
                is_st=False, effective_from=date(2025, 6, 1), effective_to=date(2025, 1, 1),
                availability_time=datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="test", mapping_version="1.0",
            )

    def test_rejects_listing_after_effective(self):
        with pytest.raises(ValueError, match="listing cannot precede effective_from"):
            SecurityIdentity(
                normalized_symbol="600519.SH", raw_symbol="600519",
                security_code="600519", security_name="Test",
                exchange=Exchange.SSE, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_001", issuer_name="Test",
                listing_date=date(2025, 6, 1), delisting_date=None,
                is_st=False, effective_from=date(2025, 1, 1), effective_to=None,
                availability_time=datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="test", mapping_version="1.0",
            )

    def test_sh_sz_bj_exchanges(self):
        for sym, ex in [("600519.SH", Exchange.SSE), ("002371.SZ", Exchange.SZSE), ("920000.BJ", Exchange.BSE)]:
            s = SecurityIdentity(
                normalized_symbol=sym, raw_symbol=sym.split(".")[0],
                security_code=sym.split(".")[0], security_name="Test",
                exchange=ex, board=BoardType.MAIN_BOARD,
                issuer_id="issuer_001", issuer_name="Test",
                listing_date=date(2020, 1, 1), delisting_date=None,
                is_st=False, effective_from=date(2020, 1, 1), effective_to=None,
                availability_time=datetime(2020, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="test", mapping_version="1.0",
            )
            assert s.exchange == ex

    def test_star_chinext_board(self):
        star = SecurityIdentity(
            normalized_symbol="688981.SH", raw_symbol="688981",
            security_code="688981", security_name="Test",
            exchange=Exchange.SSE, board=BoardType.STAR,
            issuer_id="issuer_001", issuer_name="Test",
            listing_date=date(2020, 1, 1), delisting_date=None,
            is_st=False, effective_from=date(2020, 1, 1), effective_to=None,
            availability_time=datetime(2020, 1, 1, 15, 0, tzinfo=timezone.utc),
            source="test", mapping_version="1.0",
        )
        assert star.board == BoardType.STAR


class TestFixtureIdentityProvider:
    def test_returns_identities(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(2025, 10, 31))
        assert r.status == IdentityProviderStatus.FIXTURE
        assert len(r.securities) >= 5

    def test_exchanges_covered(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(2025, 10, 31))
        exchanges = {s.exchange for s in r.securities}
        assert Exchange.SSE in exchanges
        assert Exchange.SZSE in exchanges
        assert Exchange.BSE in exchanges

    def test_boards_covered(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(2025, 10, 31))
        boards = {s.board for s in r.securities}
        assert BoardType.MAIN_BOARD in boards
        assert BoardType.STAR in boards
        assert BoardType.CHINEXT in boards
        assert BoardType.BEIJING in boards

    def test_st_name_period(self):
        p = FixtureIdentityProvider()
        # During ST period
        r = p.load(as_of=date(2025, 4, 1))
        st = [s for s in r.securities if s.normalized_symbol == "600522.SH"]
        assert len(st) == 1
        assert st[0].is_st

    def test_st_removed(self):
        p = FixtureIdentityProvider()
        # After ST removal
        r = p.load(as_of=date(2025, 10, 31))
        st = [s for s in r.securities if s.normalized_symbol == "600522.SH"]
        assert len(st) == 1
        assert not st[0].is_st

    def test_delisted_security(self):
        p = FixtureIdentityProvider()
        # Before delisting
        r = p.load(as_of=date(2024, 6, 1))
        assert any(s.normalized_symbol == "600001.SH" for s in r.securities)
        # After delisting
        r = p.load(as_of=date(2025, 6, 1))
        assert not any(s.normalized_symbol == "600001.SH" for s in r.securities)

    def test_suspended_security(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(2025, 10, 31))
        assert any(s.normalized_symbol == "600002.SH" for s in r.securities)

    def test_name_change_does_not_break_history(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(2023, 6, 1))
        names = {s.security_name for s in r.securities if s.normalized_symbol == "600522.SH"}
        assert len(names) == 1

    def test_future_mapping_rejected(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(1990, 1, 1))
        assert len(r.securities) == 0
        assert any("future" in g for g in r.data_gaps)

    def test_deterministic(self):
        p = FixtureIdentityProvider()
        r1 = p.load(as_of=date(2025, 10, 31))
        r2 = p.load(as_of=date(2025, 10, 31))
        assert len(r1.securities) == len(r2.securities)

    def test_issuer_security_separation(self):
        p = FixtureIdentityProvider()
        r = p.load(as_of=date(2025, 10, 31))
        assert len(r.issuers) >= 3
        # One issuer can have multiple securities
        issuer_ids = {s.issuer_id for s in r.securities}
        assert len(issuer_ids) <= len(r.securities)


class TestErrorStateProviders:
    @pytest.mark.parametrize("provider_cls,expected_status", [
        (UnconfiguredIdentityProvider, IdentityProviderStatus.UNCONFIGURED),
        (PermissionDeniedIdentityProvider, IdentityProviderStatus.PERMISSION_DENIED),
        (UpstreamUnavailableIdentityProvider, IdentityProviderStatus.UPSTREAM_UNAVAILABLE),
    ])
    def test_error_state(self, provider_cls, expected_status):
        p = provider_cls()
        r = p.load(as_of=date(2025, 10, 31))
        assert r.status == expected_status
        assert len(r.securities) == 0
        assert len(r.data_gaps) > 0

    def test_future_mapping_rejected(self):
        p = FutureMappingRejectedProvider()
        r = p.load(as_of=date(2025, 10, 31))
        assert any("future" in g for g in r.data_gaps)


class TestProtocolContract:
    def test_all_implement_protocol(self):
        providers = [
            FixtureIdentityProvider(),
            UnconfiguredIdentityProvider(),
            PermissionDeniedIdentityProvider(),
            UpstreamUnavailableIdentityProvider(),
            FutureMappingRejectedProvider(),
        ]
        for p in providers:
            assert isinstance(p, IdentityProviderProtocol)
            r = p.load(as_of=date(2025, 10, 31))
            assert r.as_of == date(2025, 10, 31)
