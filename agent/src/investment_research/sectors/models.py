from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class SectorProviderStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    PERMISSION_DENIED = "permission_denied"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    CONFIGURED = "configured"
    FIXTURE = "fixture"


class ClassificationStandard(StrEnum):
    CITICS = "citics"
    SW = "sw"
    CSI = "csi"
    GICS = "gics"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class SectorMembershipRecord:
    normalized_symbol: str
    issuer_id: str
    sector_id: str
    sector_name: str
    classification_standard: ClassificationStandard
    effective_from: date
    effective_to: date | None
    availability_time: datetime
    source: str
    membership_version: str

    def __post_init__(self) -> None:
        if not self.normalized_symbol.strip() or not self.issuer_id.strip():
            raise ValueError("symbol and issuer_id are required")
        if not self.sector_id.strip() or not self.sector_name.strip():
            raise ValueError("sector_id and sector_name are required")
        if not self.source.strip() or not self.membership_version.strip():
            raise ValueError("source and membership_version are required")
        if self.effective_from > (self.effective_to or self.effective_from):
            raise ValueError("effective_from cannot follow effective_to")
        _require_aware(self.availability_time, "availability_time")


@dataclass(frozen=True, slots=True)
class SectorMembershipResult:
    status: SectorProviderStatus
    memberships: tuple[SectorMembershipRecord, ...]
    as_of: date
    data_gaps: tuple[str, ...]
    errors: tuple[str, ...]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
