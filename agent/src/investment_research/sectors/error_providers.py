from __future__ import annotations

from datetime import date

from .models import SectorMembershipResult, SectorProviderStatus
from .protocol import SectorMembershipProviderProtocol


class UnconfiguredSectorProvider(SectorMembershipProviderProtocol):
    provider_name = "unconfigured_sector"
    status = SectorProviderStatus.UNCONFIGURED.value

    def load(self, *, as_of: date) -> SectorMembershipResult:
        return SectorMembershipResult(
            status=SectorProviderStatus.UNCONFIGURED,
            memberships=(), as_of=as_of,
            data_gaps=("sector_data_unconfigured",),
            errors=(),
        )


class UpstreamUnavailableSectorProvider(SectorMembershipProviderProtocol):
    provider_name = "upstream_unavailable_sector"
    status = SectorProviderStatus.UPSTREAM_UNAVAILABLE.value

    def load(self, *, as_of: date) -> SectorMembershipResult:
        return SectorMembershipResult(
            status=SectorProviderStatus.UPSTREAM_UNAVAILABLE,
            memberships=(), as_of=as_of,
            data_gaps=("sector_data_upstream_unavailable",),
            errors=("upstream_connection_failed",),
        )


class CurrentMembershipBackfillGuardProvider(SectorMembershipProviderProtocol):
    """Provider that refuses to return current data for historical dates."""
    provider_name = "current_backfill_guard_sector"
    status = SectorProviderStatus.FIXTURE.value

    def load(self, *, as_of: date) -> SectorMembershipResult:
        return SectorMembershipResult(
            status=SectorProviderStatus.FIXTURE,
            memberships=(),
            as_of=as_of,
            data_gaps=("current_membership_cannot_backfill",),
            errors=(),
        )
