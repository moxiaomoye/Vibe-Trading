from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from decimal import Decimal


class EventProviderStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    PERMISSION_DENIED = "permission_denied"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    CONFIGURED = "configured"
    FIXTURE = "fixture"


class EventType(StrEnum):
    COMPANY_ANNOUNCEMENT = "company_announcement"
    REGULATORY_FILING = "regulatory_filing"
    EARNINGS_CALL = "earnings_call"
    ANALYST_ACTION = "analyst_action"
    NEWS_ARTICLE = "news_article"
    INDUSTRY_EVENT = "industry_event"
    MACRO_EVENT = "macro_event"
    MARKET_SYSTEMIC = "market_systemic"
    ADVERSE_EVENT = "adverse_event"


@dataclass(frozen=True, slots=True)
class PointInTimeEventRecord:
    issuer_id: str
    normalized_symbol: str
    event_type: EventType
    headline: str
    occurrence_time: datetime
    publication_time: datetime
    availability_time: datetime
    retrieved_at: datetime
    source: str
    source_record_id: str
    source_url: str
    body_available: bool
    parser_version: str
    confidence: Decimal
    normalized_facts: tuple[str, ...] = ()
    body_excerpt: str = ""

    def __post_init__(self) -> None:
        _require_aware(self.occurrence_time, "occurrence_time")
        _require_aware(self.publication_time, "publication_time")
        _require_aware(self.availability_time, "availability_time")
        _require_aware(self.retrieved_at, "retrieved_at")
        if self.event_type not in (EventType.MARKET_SYSTEMIC, EventType.MACRO_EVENT):
            if not self.issuer_id.strip() or not self.normalized_symbol.strip():
                raise ValueError("issuer_id and normalized_symbol are required")
        if not self.headline.strip():
            raise ValueError("headline is required")
        if not self.source.strip() or not self.source_record_id.strip():
            raise ValueError("source and source_record_id are required")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("confidence must be between 0 and 1")
        if self.occurrence_time > self.publication_time:
            raise ValueError("occurrence cannot follow publication")
        if self.publication_time > self.availability_time:
            raise ValueError("publication cannot follow availability")
        if self.retrieved_at < self.availability_time:
            raise ValueError("retrieved_at cannot precede availability_time")
        if "://" in self.source_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.source_url)
            if parsed.username or parsed.password:
                raise ValueError("source_url must not contain credentials")
        if not self.parser_version.strip():
            raise ValueError("parser_version is required")


@dataclass(frozen=True, slots=True)
class EventProviderResult:
    status: EventProviderStatus
    records: tuple[PointInTimeEventRecord, ...]
    as_of: date
    data_gaps: tuple[str, ...]
    errors: tuple[str, ...]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
