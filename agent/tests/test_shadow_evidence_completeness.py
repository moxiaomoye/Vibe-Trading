"""W6 — Shadow report evidence completeness matrix.

Verifies ResearchProviderAdapter behavior across all provider states:
fixture, unconfigured, permission_denied, upstream_unavailable,
malformed_response, and mixed combinations.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.financials.fixture_provider import FixtureFinancialProvider
from src.investment_research.financials.error_providers import (
    UnconfiguredFinancialProvider,
    PermissionDeniedFinancialProvider,
    UpstreamUnavailableFinancialProvider,
    MalformedResponseFinancialProvider,
)
from src.investment_research.events.fixture_provider import FixtureEventProvider
from src.investment_research.events.error_providers import (
    UnconfiguredEventProvider,
    PermissionDeniedEventProvider,
    UpstreamUnavailableEventProvider,
)
from src.investment_research.identity.fixture_provider import FixtureIdentityProvider
from src.investment_research.identity.error_providers import (
    UnconfiguredIdentityProvider,
    PermissionDeniedIdentityProvider,
)
from src.investment_research.sectors.fixture_provider import FixtureSectorMembershipProvider
from src.investment_research.sectors.error_providers import (
    UnconfiguredSectorProvider,
    UpstreamUnavailableSectorProvider,
    CurrentMembershipBackfillGuardProvider,
)
from src.investment_research.integrations.research_provider_adapter import (
    Provenance,
    ResearchProviderAdapter,
)


AS_OF = date(2025, 11, 1)


class TestAllFixture:
    """All providers return fixture data — full evidence set."""

    def test_financial_observations_present(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert len(ctx.financial_observations) >= 1
        assert ctx.financial_provenance is not None
        assert ctx.financial_provenance.category == Provenance.FIXTURE


class TestFinancialUnconfigured:
    """Financial provider unconfigured — remaining providers fixture."""

    def test_financial_observations_empty(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=UnconfiguredFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert len(ctx.financial_observations) == 0
        assert ctx.financial_provenance is not None
        assert ctx.financial_provenance.category == Provenance.UNAVAILABLE


class TestFinancialPermissionDenied:
    def test_provenance_reflects_denied(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=PermissionDeniedFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert ctx.financial_provenance.category == Provenance.PERMISSION_DENIED


class TestFinancialUpstreamUnavailable:
    def test_provenance_reflects_unavailable(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=UpstreamUnavailableFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert ctx.financial_provenance.category == Provenance.UNAVAILABLE


class TestFinancialMalformed:
    def test_provenance_reflects_insufficient(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=MalformedResponseFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert ctx.financial_provenance.category == Provenance.INSUFFICIENT_DATA


class TestAllUnconfigured:
    """All providers unconfigured — empty evidence, provenance reflects."""

    def test_all_unconfigured(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=UnconfiguredFinancialProvider(),
            event_provider=UnconfiguredEventProvider(),
            identity_provider=UnconfiguredIdentityProvider(),
            sector_provider=UnconfiguredSectorProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert len(ctx.financial_observations) == 0
        for prov in (ctx.financial_provenance, ctx.event_provenance,
                     ctx.identity_provenance, ctx.sector_provenance):
            assert prov is not None
            assert prov.category == Provenance.UNAVAILABLE

    def test_data_gaps_populated(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=UnconfiguredFinancialProvider(),
            event_provider=UnconfiguredEventProvider(),
            identity_provider=UnconfiguredIdentityProvider(),
            sector_provider=UnconfiguredSectorProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert len(ctx.data_gaps) >= 4


class TestSectorCurrentOnly:
    """CurrentMembershipBackfillGuardProvider prevents historical sector data."""

    def test_current_only_sector(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=FixtureEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=CurrentMembershipBackfillGuardProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert len(ctx.financial_observations) >= 1
        assert ctx.sector_provenance is not None


class TestMixedStates:
    """Different providers in different states."""

    def test_permission_denied_and_fixture(self) -> None:
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=PermissionDeniedEventProvider(),
            identity_provider=FixtureIdentityProvider(),
            sector_provider=CurrentMembershipBackfillGuardProvider(),
        )
        ctx = adapter.load_context(as_of=AS_OF)
        assert ctx.financial_provenance.category == Provenance.FIXTURE
        assert ctx.event_provenance.category == Provenance.PERMISSION_DENIED
        assert ctx.identity_provenance.category == Provenance.FIXTURE
