from __future__ import annotations

from datetime import date, datetime, timezone

from .models import (
    ClassificationStandard,
    SectorMembershipRecord,
    SectorMembershipResult,
    SectorProviderStatus,
)
from .protocol import SectorMembershipProviderProtocol


class FixtureSectorMembershipProvider(SectorMembershipProviderProtocol):
    """Fixture sector membership provider with date-effective data.

    Covers: valid members, expired members, overlapping members,
    classification standard changes, and current-member gap detection.
    """

    provider_name = "fixture_sector"
    status = SectorProviderStatus.FIXTURE.value

    def __init__(self) -> None:
        self._memberships = (
            # 600519.SH — baijiu sector since IPO
            SectorMembershipRecord(
                normalized_symbol="600519.SH",
                issuer_id="issuer_600519",
                sector_id="sector_baijiu",
                sector_name="白酒",
                classification_standard=ClassificationStandard.SW,
                effective_from=date(2001, 8, 27),
                effective_to=None,
                availability_time=datetime(2001, 8, 27, 15, 0, tzinfo=timezone.utc),
                source="fixture_sector",
                membership_version="1.0.0",
            ),
            # 002371.SZ — semiconductor sector since IPO
            SectorMembershipRecord(
                normalized_symbol="002371.SZ",
                issuer_id="issuer_002371",
                sector_id="sector_semiconductor",
                sector_name="半导体",
                classification_standard=ClassificationStandard.SW,
                effective_from=date(2010, 3, 16),
                effective_to=None,
                availability_time=datetime(2010, 3, 16, 15, 0, tzinfo=timezone.utc),
                source="fixture_sector",
                membership_version="1.0.0",
            ),
            # 300750.SZ — changed sector in 2022 (battery → EV)
            SectorMembershipRecord(
                normalized_symbol="300750.SZ",
                issuer_id="issuer_300750",
                sector_id="sector_battery",
                sector_name="电池",
                classification_standard=ClassificationStandard.SW,
                effective_from=date(2018, 6, 11),
                effective_to=date(2022, 6, 30),
                availability_time=datetime(2018, 6, 11, 15, 0, tzinfo=timezone.utc),
                source="fixture_sector",
                membership_version="1.0.0",
            ),
            SectorMembershipRecord(
                normalized_symbol="300750.SZ",
                issuer_id="issuer_300750",
                sector_id="sector_ev",
                sector_name="新能源车",
                classification_standard=ClassificationStandard.SW,
                effective_from=date(2022, 7, 1),
                effective_to=None,
                availability_time=datetime(2022, 7, 1, 15, 0, tzinfo=timezone.utc),
                source="fixture_sector",
                membership_version="2.0.0",
            ),
            # 688981.SH — semiconductor since IPO
            SectorMembershipRecord(
                normalized_symbol="688981.SH",
                issuer_id="issuer_688981",
                sector_id="sector_semiconductor",
                sector_name="半导体",
                classification_standard=ClassificationStandard.SW,
                effective_from=date(2020, 7, 16),
                effective_to=None,
                availability_time=datetime(2020, 7, 16, 15, 0, tzinfo=timezone.utc),
                source="fixture_sector",
                membership_version="1.0.0",
            ),
            # Overlapping membership (classification standard change)
            # Both CITICS and SW classifications active during overlap period
            SectorMembershipRecord(
                normalized_symbol="002371.SZ",
                issuer_id="issuer_002371",
                sector_id="sector_electronics_citics",
                sector_name="电子(CITICS)",
                classification_standard=ClassificationStandard.CITICS,
                effective_from=date(2020, 1, 1),
                effective_to=None,
                availability_time=datetime(2020, 1, 1, 15, 0, tzinfo=timezone.utc),
                source="fixture_sector",
                membership_version="1.0.0",
            ),
        )

    def load(self, *, as_of: date) -> SectorMembershipResult:
        gaps: list[str] = []
        errors: list[str] = []
        eligible: list[SectorMembershipRecord] = []

        for m in self._memberships:
            if m.effective_from > as_of:
                gaps.append(f"future_membership: {m.normalized_symbol}")
                continue
            if m.effective_to is not None and m.effective_to < as_of:
                gaps.append(f"expired_membership: {m.normalized_symbol}")
                continue
            if m.availability_time.date() > as_of:
                gaps.append(f"future_availability: {m.normalized_symbol}")
                continue
            eligible.append(m)

        return SectorMembershipResult(
            status=SectorProviderStatus.FIXTURE,
            memberships=tuple(eligible),
            as_of=as_of,
            data_gaps=tuple(gaps),
            errors=tuple(errors),
        )
