"""Point-in-time issuer disclosure identities before research classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class IssuerDisclosureSubscription:
    subscription_id: str
    asset_id: str
    market: str
    symbol: str
    issuer_id: str | None = None
    forms: tuple[str, ...] = ("10-K", "10-Q", "8-K", "20-F", "6-K")
    enabled: bool = True

    def __post_init__(self) -> None:
        for name in ("subscription_id", "asset_id", "market", "symbol"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.market.upper() != "US":
            raise ValueError("SEC EDGAR subscriptions currently support the US market only")
        if not self.forms or any(not form.strip() for form in self.forms):
            raise ValueError("forms must contain at least one non-empty form")


@dataclass(frozen=True, slots=True)
class IssuerDisclosure:
    provider: str
    asset_id: str
    issuer_id: str
    filing_id: str
    form: str
    title: str
    source_locator: str
    summary: str
    published_at: datetime
    available_at: datetime
    observed_at: datetime
    content_hash: str
    quality_warnings: tuple[str, ...] = ()
    reporting_period: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "provider", "asset_id", "issuer_id", "filing_id", "form", "title",
            "source_locator", "summary", "content_hash",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("published_at", "available_at", "observed_at"):
            _aware(getattr(self, name), name)
        if self.available_at < self.published_at:
            raise ValueError("available_at cannot be earlier than published_at")
        if self.observed_at < self.available_at:
            raise ValueError("observed_at cannot be earlier than available_at")
