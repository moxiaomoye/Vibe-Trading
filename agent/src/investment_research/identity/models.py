from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class IdentityProviderStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    PERMISSION_DENIED = "permission_denied"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    CONFIGURED = "configured"
    FIXTURE = "fixture"


class BoardType(StrEnum):
    MAIN_BOARD = "main_board"
    STAR = "star"
    CHINEXT = "chinext"
    SME = "sme"
    BEIJING = "beijing"


class Exchange(StrEnum):
    SSE = "SSE"
    SZSE = "SZSE"
    BSE = "BSE"


@dataclass(frozen=True, slots=True)
class Issuer:
    issuer_id: str
    issuer_name: str
    legal_name: str | None = None

    def __post_init__(self) -> None:
        if not self.issuer_id.strip() or not self.issuer_name.strip():
            raise ValueError("issuer_id and issuer_name are required")


@dataclass(frozen=True, slots=True)
class SecurityIdentity:
    normalized_symbol: str
    raw_symbol: str
    security_code: str
    security_name: str
    exchange: Exchange
    board: BoardType
    issuer_id: str
    issuer_name: str
    listing_date: date
    delisting_date: date | None
    is_st: bool
    effective_from: date
    effective_to: date | None
    availability_time: datetime
    source: str
    mapping_version: str

    def __post_init__(self) -> None:
        if not self.normalized_symbol.strip() or not self.raw_symbol.strip():
            raise ValueError("normalized_symbol and raw_symbol are required")
        if not self.security_code.strip() or not self.security_name.strip():
            raise ValueError("security_code and security_name are required")
        if not self.issuer_id.strip() or not self.issuer_name.strip():
            raise ValueError("issuer_id and issuer_name are required")
        if self.listing_date > self.effective_from:
            raise ValueError("listing cannot precede effective_from")
        if self.effective_to is not None and self.effective_from > self.effective_to:
            raise ValueError("effective_from cannot follow effective_to")
        if not self.source.strip() or not self.mapping_version.strip():
            raise ValueError("source and mapping_version are required")
        _require_aware(self.availability_time, "availability_time")


@dataclass(frozen=True, slots=True)
class IdentityResult:
    status: IdentityProviderStatus
    issuers: tuple[Issuer, ...]
    securities: tuple[SecurityIdentity, ...]
    as_of: date
    data_gaps: tuple[str, ...]
    errors: tuple[str, ...]
    ambiguity_warnings: tuple[str, ...]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
