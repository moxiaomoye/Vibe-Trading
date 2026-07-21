"""Human-gated readiness of a Thesis evidence set.

Readiness is deliberately categorical. It is not an investment score and an
approval does not create a Thesis Version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class EvidenceSetReadiness(StrEnum):
    NOT_READY = "not_ready"
    NEEDS_SUPPORT = "needs_support"
    NEEDS_COUNTER = "needs_counter"
    NEEDS_QUALITY_REVIEW = "needs_quality_review"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    APPROVED_FOR_INITIALIZATION = "approved_for_initialization"


class EvidenceSetReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"


@dataclass(frozen=True, slots=True)
class ThesisEvidenceReadiness:
    thesis_id: str
    as_of: datetime
    verdict: EvidenceSetReadiness
    supporting_association_ids: tuple[str, ...]
    counter_association_ids: tuple[str, ...]
    neutral_association_ids: tuple[str, ...]
    blocking_gaps: tuple[str, ...]
    quality_warnings: tuple[str, ...]
    first_rejection_question: str
    approval_review_id: str | None = None

    def __post_init__(self) -> None:
        if not self.thesis_id.strip():
            raise ValueError("thesis_id must not be empty")
        _require_aware(self.as_of, "as_of")

    @property
    def association_ids(self) -> tuple[str, ...]:
        return (
            self.supporting_association_ids
            + self.counter_association_ids
            + self.neutral_association_ids
        )


@dataclass(frozen=True, slots=True)
class EvidenceSetReview:
    review_id: str
    thesis_id: str
    association_ids: tuple[str, ...]
    information_cutoff: datetime
    decision: EvidenceSetReviewDecision
    reviewer: str
    rationale: str
    reviewed_at: datetime
    strongest_counter_association_id: str | None = None
    missing_evidence: tuple[str, ...] = ()
    quality_exception_rationale: str | None = None
    approval_reference: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("review_id", "thesis_id", "reviewer", "rationale"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        _require_aware(self.information_cutoff, "information_cutoff")
        _require_aware(self.reviewed_at, "reviewed_at")
        if self.reviewed_at < self.information_cutoff:
            raise ValueError("reviewed_at cannot precede the information cutoff")
        if not self.association_ids:
            raise ValueError("an evidence set review must select evidence associations")
        if len(self.association_ids) != len(set(self.association_ids)):
            raise ValueError("association_ids must be unique")
        if self.decision == EvidenceSetReviewDecision.APPROVE:
            if self.missing_evidence:
                raise ValueError("an approval cannot retain missing evidence")
            if not self.strongest_counter_association_id:
                raise ValueError("an approval must identify the strongest counter evidence")
            if self.strongest_counter_association_id not in self.association_ids:
                raise ValueError("strongest counter evidence must be part of the reviewed set")
            if not (self.approval_reference or "").strip():
                raise ValueError("an approval requires an approval reference")

    @classmethod
    def create(
        cls,
        thesis_id: str,
        association_ids: tuple[str, ...],
        information_cutoff: datetime,
        decision: EvidenceSetReviewDecision,
        reviewer: str,
        rationale: str,
        reviewed_at: datetime,
        strongest_counter_association_id: str | None = None,
        missing_evidence: tuple[str, ...] = (),
        quality_exception_rationale: str | None = None,
        approval_reference: str | None = None,
    ) -> "EvidenceSetReview":
        identity = "|".join(
            (
                thesis_id,
                ",".join(association_ids),
                information_cutoff.isoformat(),
                decision.value,
                reviewer,
                rationale,
                reviewed_at.isoformat(),
                strongest_counter_association_id or "",
                ",".join(missing_evidence),
                quality_exception_rationale or "",
                approval_reference or "",
            )
        )
        return cls(
            str(uuid5(NAMESPACE_URL, f"evidence-set-review:{identity}")),
            thesis_id,
            association_ids,
            information_cutoff,
            decision,
            reviewer,
            rationale,
            reviewed_at,
            strongest_counter_association_id,
            missing_evidence,
            quality_exception_rationale,
            approval_reference,
        )
