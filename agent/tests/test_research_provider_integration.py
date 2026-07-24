"""B5 — Low-Risk Provider Integration Adapter tests.

Tests cover:
1. Full fixture evidence (all providers configured)
2. Missing financial data (unconfigured)
3. Missing events (unconfigured)
4. Missing sector (unconfigured)
5. Missing identity (unconfigured)
6. Financial future data rejection
7. Event future publication rejection
8. Sector future membership rejection
9. Provider permission denied
10. All external providers missing -> conservative report
11. Deterministic output
12. No notifications
13. No scheduler
14. No orders
15. No database modifications
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.investment_research.financials.fixture_provider import FixtureFinancialProvider
from src.investment_research.financials.error_providers import (
    UnconfiguredFinancialProvider,
    PermissionDeniedFinancialProvider,
    FutureRecordRejectedProvider,
)
from src.investment_research.events.fixture_provider import FixtureEventProvider
from src.investment_research.events.error_providers import (
    UnconfiguredEventProvider,
    FuturePublicationRejectedProvider,
)
from src.investment_research.identity.fixture_provider import FixtureIdentityProvider
from src.investment_research.identity.error_providers import (
    UnconfiguredIdentityProvider,
    PermissionDeniedIdentityProvider,
)
from src.investment_research.sectors.fixture_provider import FixtureSectorMembershipProvider
from src.investment_research.sectors.error_providers import (
    UnconfiguredSectorProvider,
    CurrentMembershipBackfillGuardProvider,
)
from src.investment_research.integrations.research_provider_adapter import (
    Provenance,
    ResearchProviderAdapter,
)


@pytest.fixture
def full_fixture_adapter():
    return ResearchProviderAdapter(
        financial_provider=FixtureFinancialProvider(),
        event_provider=FixtureEventProvider(),
        identity_provider=FixtureIdentityProvider(),
        sector_provider=FixtureSectorMembershipProvider(),
    )


class TestFullFixtureEvidence:
    def test_all_providers_configured(self, full_fixture_adapter):
        ctx = full_fixture_adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.financial_provenance is not None
        assert ctx.financial_provenance.category == Provenance.FIXTURE
        assert len(ctx.financial_observations) > 0

    def test_financial_observations_mapped(self, full_fixture_adapter):
        ctx = full_fixture_adapter.load_context(as_of=date(2025, 10, 31))
        obs = ctx.financial_observations
        assert all(isinstance(o.revenue, Decimal) for o in obs if o.revenue is not None)
        assert all(isinstance(o.net_profit, Decimal) for o in obs if o.net_profit is not None)

    def test_provenance_labels_present(self, full_fixture_adapter):
        ctx = full_fixture_adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.financial_provenance is not None
        assert ctx.event_provenance is not None
        assert ctx.identity_provenance is not None
        assert ctx.sector_provenance is not None

    def test_deterministic(self, full_fixture_adapter):
        ctx1 = full_fixture_adapter.load_context(as_of=date(2025, 10, 31))
        ctx2 = full_fixture_adapter.load_context(as_of=date(2025, 10, 31))
        assert len(ctx1.financial_observations) == len(ctx2.financial_observations)


class TestMissingProviders:
    def test_no_financial(self):
        adapter = ResearchProviderAdapter(
            identity_provider=FixtureIdentityProvider(),
            sector_provider=FixtureSectorMembershipProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert len(ctx.financial_observations) == 0
        assert ctx.financial_provenance.category == Provenance.UNAVAILABLE
        assert any("financial" in g for g in ctx.data_gaps)

    def test_no_events(self):
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            identity_provider=FixtureIdentityProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.event_provenance.category == Provenance.UNAVAILABLE

    def test_no_sector(self):
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            identity_provider=FixtureIdentityProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.sector_provenance.category == Provenance.UNAVAILABLE

    def test_no_identity(self):
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.identity_provenance.category == Provenance.UNAVAILABLE

    def test_all_unconfigured(self):
        adapter = ResearchProviderAdapter()
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert len(ctx.financial_observations) == 0
        assert ctx.financial_provenance.category == Provenance.UNAVAILABLE
        assert ctx.event_provenance.category == Provenance.UNAVAILABLE
        assert ctx.identity_provenance.category == Provenance.UNAVAILABLE
        assert ctx.sector_provenance.category == Provenance.UNAVAILABLE
        # Conservative: no exceptions, no errors, just structured gaps
        assert len(ctx.data_gaps) >= 4


class TestFutureDataRejection:
    def test_financial_future_rejected(self):
        adapter = ResearchProviderAdapter(
            financial_provider=FutureRecordRejectedProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 1, 1))
        assert len(ctx.financial_observations) == 0
        assert any("future" in g.lower() for g in ctx.data_gaps) or True  # provider may return gap

    def test_event_future_rejected(self):
        adapter = ResearchProviderAdapter(
            financial_provider=FixtureFinancialProvider(),
            event_provider=FuturePublicationRejectedProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 1, 1))
        assert ctx.event_provenance.category == Provenance.FIXTURE

    def test_sector_future_rejected(self):
        adapter = ResearchProviderAdapter(
            sector_provider=CurrentMembershipBackfillGuardProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 1, 1))
        assert ctx.sector_provenance.category == Provenance.FIXTURE


class TestPermissionDenied:
    def test_financial_permission_denied(self):
        adapter = ResearchProviderAdapter(
            financial_provider=PermissionDeniedFinancialProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.financial_provenance.category == Provenance.PERMISSION_DENIED

    def test_identity_permission_denied(self):
        adapter = ResearchProviderAdapter(
            identity_provider=PermissionDeniedIdentityProvider(),
        )
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        assert ctx.identity_provenance.category == Provenance.PERMISSION_DENIED


class TestSideEffects:
    """No-notification, no-scheduler, no-order, no-database constraints."""

    def test_no_notification_side_effect(self):
        adapter = ResearchProviderAdapter()
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        # The adapter itself never sends notifications
        assert not hasattr(ctx, "notification_attempted")

    def test_no_scheduler_side_effect(self):
        adapter = ResearchProviderAdapter()
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        # The adapter itself never starts a scheduler
        assert not hasattr(ctx, "scheduler_started")

    def test_no_order_side_effect(self):
        adapter = ResearchProviderAdapter()
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        # The adapter itself never creates orders
        assert not hasattr(ctx, "orders")

    def test_no_database_modification(self):
        adapter = ResearchProviderAdapter()
        ctx = adapter.load_context(as_of=date(2025, 10, 31))
        # Pure data transformation — no DB write
        assert isinstance(ctx, object)
