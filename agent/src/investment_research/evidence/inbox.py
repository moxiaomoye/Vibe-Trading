"""Immutable evidence intake and explicit human research classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..contracts import EvidenceDirection
from .associations import EvidenceAssociation, EvidenceSubjectType
from .models import Evidence


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class EvidenceInboxStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvidenceInboxDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


EvidenceInboxSubjectType = EvidenceSubjectType


@dataclass(frozen=True, slots=True)
class EvidenceInboxItem:
    inbox_item_id: str
    provider: str
    source_locator: str
    title: str
    summary: str
    published_at: datetime
    available_at: datetime
    observed_at: datetime
    content_hash: str
    quality_warnings: tuple[str, ...]
    ingested_at: datetime
    proposed_subject_type: EvidenceInboxSubjectType
    proposed_subject_id: str
    proposed_direction: EvidenceDirection = EvidenceDirection.NEUTRAL

    def __post_init__(self) -> None:
        required = {
            "inbox_item_id": self.inbox_item_id,
            "provider": self.provider,
            "source_locator": self.source_locator,
            "title": self.title,
            "summary": self.summary,
            "content_hash": self.content_hash,
            "proposed_subject_id": self.proposed_subject_id,
        }
        for field_name, value in required.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        for field_name in ("published_at", "available_at", "observed_at", "ingested_at"):
            _require_aware(getattr(self, field_name), field_name)
        if self.available_at < self.published_at:
            raise ValueError("available_at cannot be earlier than published_at")
        if self.observed_at < self.available_at:
            raise ValueError("observed_at cannot be earlier than available_at")
        if self.ingested_at < self.observed_at:
            raise ValueError("ingested_at cannot be earlier than observed_at")


@dataclass(frozen=True, slots=True)
class EvidenceInboxReview:
    review_id: str
    inbox_item_id: str
    decision: EvidenceInboxDecision
    rationale: str
    reviewer: str
    reviewed_at: datetime
    final_subject_type: EvidenceInboxSubjectType | None = None
    final_subject_id: str | None = None
    final_direction: EvidenceDirection | None = None

    def __post_init__(self) -> None:
        for field_name in ("review_id", "inbox_item_id", "rationale", "reviewer"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        _require_aware(self.reviewed_at, "reviewed_at")
        classification = (self.final_subject_type, self.final_subject_id, self.final_direction)
        if self.decision == EvidenceInboxDecision.ACCEPT:
            if any(value is None for value in classification) or not self.final_subject_id.strip():
                raise ValueError("accepted evidence requires a final subject and direction")
        elif any(value is not None for value in classification):
            raise ValueError("rejected evidence cannot define a final classification")


@dataclass(frozen=True, slots=True)
class ReviewedEvidenceInboxItem:
    item: EvidenceInboxItem
    status: EvidenceInboxStatus
    review: EvidenceInboxReview | None = None

    def __post_init__(self) -> None:
        if self.status == EvidenceInboxStatus.PENDING and self.review is not None:
            raise ValueError("pending evidence cannot have a terminal review")
        if self.status != EvidenceInboxStatus.PENDING and self.review is None:
            raise ValueError("terminal evidence status requires a review")


@dataclass(frozen=True, slots=True)
class AcceptedEvidenceInboxItem:
    review: EvidenceInboxReview
    evidence: Evidence
    association: EvidenceAssociation

    def __post_init__(self) -> None:
        if self.review.decision != EvidenceInboxDecision.ACCEPT:
            raise ValueError("accepted evidence result requires an accept decision")
        if self.association.evidence_id != self.evidence.evidence_id:
            raise ValueError("accepted evidence association references the wrong evidence")
