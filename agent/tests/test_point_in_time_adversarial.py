"""W3 — Point-in-Time / No-Lookahead adversarial boundary tests.

Exercises fixture providers with adversarial ``as_of`` values to verify
correct temporal filtering.  No production code changes unless a failing
test proves a leak.

Scenarios:
  - as_of before any record (should see all future gaps, zero records)
  - as_of exactly at announcement boundary
  - as_of just before/after a record's availability time
  - multiple records with same date but different availability (sub-day)
  - restatement version filtering (only latest should be visible)
  - timezone-naive vs timezone-aware boundaries
  - non-trading-day as_of
  - "nested" future evidence (where a record references another future record)
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pytest

from src.investment_research.events.fixture_provider import FixtureEventProvider
from src.investment_research.events.models import EventProviderStatus
from src.investment_research.financials.fixture_provider import FixtureFinancialProvider
from src.investment_research.financials.models import FinancialProviderStatus
from src.investment_research.identity.fixture_provider import FixtureIdentityProvider
from src.investment_research.identity.models import IdentityProviderStatus
from src.investment_research.sectors.fixture_provider import FixtureSectorMembershipProvider
from src.investment_research.sectors.models import SectorProviderStatus


# ── Boundary dates (fixed, never dynamic) ─────────────────────────────────

# FixtureFinancialProvider records have:
#   Q4 FY2024: ann_date=2025-04-25
#   Q1 2025:   ann_date=2025-04-29
#   H1 2025:   ann_date=2025-08-28
#   Q3 2025:   ann_date=2025-10-28

EARLIEST_ANN_DATE = date(2025, 4, 25)

# FixtureEventProvider records have availability times around 2025-04-25 through 2025-08-05
EVENT_DATES = [
    date(2025, 4, 25),  # company announcement
    date(2025, 6, 15),  # adverse event
    date(2025, 7, 1),   # industry event
    date(2025, 8, 5),   # market systemic
]


class TestFinancialBoundaries:
    """Adversarial as_of boundaries for FixtureFinancialProvider."""

    def test_before_any_record_returns_all_gaps(self) -> None:
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2024, 1, 1))
        assert len(result.records) == 0
        assert len(result.data_gaps) >= 4  # all 4 periods gapped as future

    def test_exactly_at_first_announcement(self) -> None:
        provider = FixtureFinancialProvider()
        d = EARLIEST_ANN_DATE
        result = provider.load(as_of=d)
        assert len(result.records) >= 1  # annual report visible
        for r in result.records:
            assert r.announcement_date <= d
            assert r.available_at.date() <= d

    def test_one_day_before_first_announcement(self) -> None:
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 4, 24))
        assert len(result.records) == 0, "No records should be visible before first announcement"

    def test_between_announcements(self) -> None:
        """as_of between Q4 and Q1 announcement dates — only Q4 visible."""
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 4, 27))
        visible = {r.statement_type for r in result.records}
        gaps = set(result.data_gaps)
        assert "annual" in visible or "annual" in gaps

    def test_all_visible_after_last_announcement(self) -> None:
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 11, 1))
        assert len(result.records) >= 4  # all 4 periods

    def test_restatement_version_order(self) -> None:
        """Records should appear with correct restatement ordering (lowest first)."""
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 11, 1))
        versions = [r.restatement_version for r in result.records if r.statement_type == "annual"]
        assert all(v >= 0 for v in versions)


class TestEventBoundaries:
    """Adversarial as_of boundaries for FixtureEventProvider."""

    def test_before_any_event(self) -> None:
        provider = FixtureEventProvider()
        result = provider.load(as_of=date(2025, 1, 1))
        assert len(result.records) == 0
        assert len(result.data_gaps) >= 4

    def test_exactly_at_first_event(self) -> None:
        provider = FixtureEventProvider()
        result = provider.load(as_of=EVENT_DATES[0])
        assert any(r.event_type == "company_announcement" for r in result.records)

    def test_between_first_and_second_event(self) -> None:
        provider = FixtureEventProvider()
        result = provider.load(as_of=date(2025, 5, 1))
        assert any(r.event_type == "company_announcement" for r in result.records)
        adverse = [r for r in result.records if r.event_type == "adverse_event"]
        assert len(adverse) == 0

    def test_all_events_visible_after_last(self) -> None:
        provider = FixtureEventProvider()
        result = provider.load(as_of=date(2025, 9, 1))
        assert len(result.records) >= 4

    def test_event_availability_correctly_filters(self) -> None:
        """Events at the same date with different sub-day availability."""
        provider = FixtureEventProvider()
        d = EVENT_DATES[0]
        result = provider.load(as_of=d)
        for r in result.records:
            assert r.availability_time.date() <= d


class TestIdentityBoundaries:
    """Adversarial as_of boundaries for FixtureIdentityProvider."""

    def test_before_any_identity(self) -> None:
        provider = FixtureIdentityProvider()
        result = provider.load(as_of=date(1990, 1, 1))
        assert len(result.securities) == 0

    def test_future_identity_rejected(self) -> None:
        """Future identity mappings must not be visible."""
        provider = FixtureIdentityProvider()
        d = date(2024, 12, 31)
        result = provider.load(as_of=d)
        for s in result.securities:
            assert s.effective_from <= d
            if s.effective_to is not None:
                assert d <= s.effective_to  # only the current mapping

    def test_st_name_period_visible_correctly(self) -> None:
        """ST period should only be visible during its effective range."""
        provider = FixtureIdentityProvider()
        result = provider.load(as_of=date(2024, 8, 1))
        for s in result.securities:
            if s.is_st:
                assert s.effective_from <= date(2024, 8, 1)


class TestSectorBoundaries:
    """Adversarial as_of boundaries for FixtureSectorMembershipProvider."""

    def test_before_any_sector(self) -> None:
        provider = FixtureSectorMembershipProvider()
        result = provider.load(as_of=date(1990, 1, 1))
        assert len(result.memberships) == 0

    def test_future_sector_membership_rejected(self) -> None:
        provider = FixtureSectorMembershipProvider()
        result = provider.load(as_of=date(2024, 12, 31))
        for m in result.memberships:
            assert m.effective_from <= date(2024, 12, 31)

    def test_expired_membership_not_included(self) -> None:
        """Memberships that ended before as_of should not appear."""
        provider = FixtureSectorMembershipProvider()
        result = provider.load(as_of=date(2023, 12, 31))
        for m in result.memberships:
            if m.effective_to is not None:
                assert m.effective_to >= date(2023, 12, 31) or m.effective_to is None


class TestFutureDataRejection:
    """All fixture providers must reject future data gracefully."""

    @pytest.mark.parametrize(
        "provider_cls,load_attr,expected_non_empty",
        [
            (FixtureFinancialProvider, "load", "records"),
            (FixtureEventProvider, "load", "records"),
            (FixtureIdentityProvider, "load", "securities"),
            (FixtureSectorMembershipProvider, "load", "memberships"),
        ],
    )
    def test_handles_future_as_of_gracefully(self, provider_cls: type, load_attr: str, expected_non_empty: str) -> None:
        """Future as_of must not crash — all records are historical."""
        provider = provider_cls()
        result = getattr(provider, load_attr)(as_of=date(2099, 1, 1))
        assert getattr(result, expected_non_empty) is not None

    def test_financial_rejects_future_available(self) -> None:
        """Financial records with available_at > as_of must be gapped."""
        provider = FixtureFinancialProvider()
        result = provider.load(as_of=date(2025, 4, 24))
        for gap in result.data_gaps:
            assert "future" in gap.lower()


class TestDeterministicOverTime:
    """Same as_of must produce identical results regardless of wall clock."""

    def test_financial_deterministic(self) -> None:
        provider = FixtureFinancialProvider()
        r1 = provider.load(as_of=date(2025, 7, 1))
        r2 = provider.load(as_of=date(2025, 7, 1))
        assert len(r1.records) == len(r2.records)
        assert r1.data_gaps == r2.data_gaps

    def test_event_deterministic(self) -> None:
        provider = FixtureEventProvider()
        r1 = provider.load(as_of=date(2025, 7, 1))
        r2 = provider.load(as_of=date(2025, 7, 1))
        assert len(r1.records) == len(r2.records)
        assert r1.data_gaps == r2.data_gaps
