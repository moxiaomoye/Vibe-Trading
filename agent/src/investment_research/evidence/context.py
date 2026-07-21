"""Generic evidence bundles for market, asset, and opportunity context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .models import Evidence


class EvidenceSubjectType(StrEnum):
    MARKET = "market"
    ASSET = "asset"
    OPPORTUNITY = "opportunity"
    VALIDATION = "validation"


@dataclass(frozen=True, slots=True)
class ContextEvidenceBundle:
    evidence_bundle_id: str
    subject_type: EvidenceSubjectType
    subject_id: str
    as_of: datetime
    evidence_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for value, name in ((self.as_of, "as_of"), (self.created_at, "created_at")):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if not self.evidence_bundle_id or not self.subject_id or not self.evidence_ids:
            raise ValueError("context evidence identity, subject, and evidence are required")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("context evidence ids must be unique")

    def validate_point_in_time(self, evidence: tuple[Evidence, ...]) -> None:
        by_id = {item.evidence_id: item for item in evidence}
        missing = set(self.evidence_ids) - set(by_id)
        if missing:
            raise ValueError(f"unknown context evidence ids: {sorted(missing)}")
        future = [item.evidence_id for item in evidence if item.evidence_id in self.evidence_ids and not item.is_available(self.as_of)]
        if future:
            raise ValueError(f"context evidence unavailable as of {self.as_of.isoformat()}: {future}")
