"""Contextual, append-only classification of immutable research evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection


class EvidenceSubjectType(StrEnum):
    THESIS = "thesis"
    MARKET = "market"
    ASSET = "asset"
    OPPORTUNITY = "opportunity"
    VALIDATION = "validation"


@dataclass(frozen=True, slots=True)
class EvidenceAssociation:
    association_id: str
    evidence_id: str
    subject_type: EvidenceSubjectType
    subject_id: str
    direction: EvidenceDirection
    assessed_at: datetime
    assessor: str
    rationale: str
    supersedes_association_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("association_id", "evidence_id", "subject_id", "assessor", "rationale"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be timezone-aware")
        if self.supersedes_association_id == self.association_id:
            raise ValueError("an evidence association cannot supersede itself")

    @classmethod
    def create(
        cls,
        evidence_id: str,
        subject_type: EvidenceSubjectType,
        subject_id: str,
        direction: EvidenceDirection,
        assessed_at: datetime,
        assessor: str,
        rationale: str,
        supersedes_association_id: str | None = None,
    ) -> "EvidenceAssociation":
        identity = "|".join(
            (
                evidence_id, subject_type.value, subject_id, direction.value, assessed_at.isoformat(),
                assessor, rationale, supersedes_association_id or "initial",
            )
        )
        return cls(
            str(uuid5(NAMESPACE_URL, f"evidence-association:{identity}")),
            evidence_id,
            subject_type,
            subject_id,
            direction,
            assessed_at,
            assessor,
            rationale,
            supersedes_association_id,
        )
