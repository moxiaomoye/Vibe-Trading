"""Point-in-time universe eligibility (RRV-RELIABILITY-CLOSURE-001, RF-003).

Determines whether a watchlist symbol was investable as of a research date
using a priority chain: trusted asset metadata (listing date) first, then
verifiable trading records on or before the as-of date, otherwise UNKNOWN.
A provider failure is never presented as a listing-date judgement.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

ELIGIBILITY_POLICY_VERSION = "eligibility-v1"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    CONFIRMED_NOT_LISTED = "CONFIRMED_NOT_LISTED"
    UNKNOWN = "UNKNOWN"


class EligibilityVerdict(BaseModel):
    policy_version: str = ELIGIBILITY_POLICY_VERSION
    symbol: str
    name: str
    security_type: str = "stock"
    eligibility_status: EligibilityStatus
    listing_date: date | None = None
    eligibility_evidence_source: str
    eligibility_reason: str
    eligibility_as_of: date


def resolve_eligibility(
    symbol: str,
    security_type: str,
    as_of: date,
    *,
    listing_date: date | None = None,
    has_trading_history: bool | None = None,
    name: str = "",
) -> EligibilityVerdict:
    """Resolve eligibility with the frozen priority chain.

    Priority:
    1. Trusted listing_date metadata (watchlist / asset metadata).
    2. Verifiable trading records on or before ``as_of``.
    3. Provider failure -> UNKNOWN (never assert not listed).
    4. Otherwise UNKNOWN.
    """
    base = dict(
        symbol=symbol,
        name=name,
        security_type=security_type,
        eligibility_as_of=as_of,
        listing_date=listing_date,
    )
    if listing_date is not None:
        if listing_date > as_of:
            return EligibilityVerdict(
                **base,
                eligibility_status=EligibilityStatus.CONFIRMED_NOT_LISTED,
                eligibility_evidence_source="asset-metadata",
                eligibility_reason=(
                    f"上市日期 {listing_date.isoformat()} 晚于研究日期 {as_of.isoformat()}"
                ),
            )
        return EligibilityVerdict(
            **base,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            eligibility_evidence_source="asset-metadata",
            eligibility_reason="资产元数据上市日期不晚于研究日期",
        )
    if has_trading_history is True:
        return EligibilityVerdict(
            **base,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            eligibility_evidence_source="trading-records",
            eligibility_reason=f"研究日期 {as_of.isoformat()} 前存在可验证交易记录",
        )
    if has_trading_history is None:
        return EligibilityVerdict(
            **base,
            eligibility_status=EligibilityStatus.UNKNOWN,
            eligibility_evidence_source="provider-failure",
            eligibility_reason="Provider 本次调用失败，无法确认上市状态；不得把 Provider 故障冒充上市日判断",
        )
    return EligibilityVerdict(
        **base,
        eligibility_status=EligibilityStatus.UNKNOWN,
        eligibility_evidence_source="no-evidence",
        eligibility_reason="无资产元数据且研究日期前无可验证交易记录，无法确认上市状态",
    )


def listing_date_from_value(value: Any) -> date | None:
    """Parse an optional ``listing_date`` from watchlist metadata safely."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
