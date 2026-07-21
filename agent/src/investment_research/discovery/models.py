"""Point-in-time observations and explainable discovery outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class FundamentalIntegrity(StrEnum):
    INTACT = "intact"
    MIXED = "mixed"
    DETERIORATING = "deteriorating"
    UNKNOWN = "unknown"


class DiscoveryDisposition(StrEnum):
    REJECTED = "rejected"
    EVIDENCE_GAP = "evidence_gap"
    ATTRIBUTION_REQUIRED = "attribution_required"
    OPPORTUNITY_REVIEW = "opportunity_review"


@dataclass(frozen=True, slots=True)
class ResearchSnapshot:
    snapshot_id: str
    asset_id: str
    thesis_version_id: str
    evidence_set_id: str
    as_of: datetime
    drawdown_from_reference: float | None
    sector_excess_return: float | None
    valuation_percentile: float | None
    fundamental_integrity: FundamentalIntegrity
    fundamental_evidence_ids: tuple[str, ...]
    attribution_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    severe_risk_flags: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research snapshot as_of must be timezone-aware")
        if not all((self.snapshot_id, self.asset_id, self.thesis_version_id, self.evidence_set_id)):
            raise ValueError("research snapshot identity and evidence references are required")
        if self.valuation_percentile is not None and not 0 <= self.valuation_percentile <= 1:
            raise ValueError("valuation_percentile must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ResearchLead:
    lead_id: str
    asset_id: str
    thesis_version_id: str
    evidence_set_id: str
    disposition: DiscoveryDisposition
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    first_rejection_question: str
    as_of: datetime

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research lead as_of must be timezone-aware")
        if not all((self.lead_id, self.asset_id, self.thesis_version_id, self.evidence_set_id)):
            raise ValueError("research lead identity and evidence references are required")
        if not self.reasons or not self.first_rejection_question.strip():
            raise ValueError("research lead reasons and first rejection question are required")
