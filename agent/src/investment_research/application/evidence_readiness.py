"""Compute Thesis evidence readiness without manufacturing a score."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..contracts import EvidenceDirection
from ..evidence.associations import EvidenceAssociation, EvidenceSubjectType
from ..evidence.models import Evidence
from ..evidence.readiness import (
    EvidenceSetReadiness,
    EvidenceSetReview,
    EvidenceSetReviewDecision,
    ThesisEvidenceReadiness,
)


class AssociationReader(Protocol):
    def list_for_subject(
        self, subject_type: EvidenceSubjectType, subject_id: str, as_of: datetime
    ) -> list[EvidenceAssociation]: ...


class EvidenceReader(Protocol):
    def get_evidence(self, evidence_id: str) -> Evidence: ...


class EvidenceSetReviewReader(Protocol):
    def latest_for_thesis(self, thesis_id: str, as_of: datetime) -> EvidenceSetReview: ...


class ThesisEvidenceReadinessService:
    def __init__(
        self,
        associations: AssociationReader,
        evidence: EvidenceReader,
        reviews: EvidenceSetReviewReader | None = None,
    ):
        self.associations = associations
        self.evidence = evidence
        self.reviews = reviews

    def assess(self, thesis_id: str, as_of: datetime) -> ThesisEvidenceReadiness:
        if not thesis_id.strip():
            raise ValueError("thesis_id must not be empty")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        associations = self.associations.list_for_subject(EvidenceSubjectType.THESIS, thesis_id, as_of)
        available: list[tuple[EvidenceAssociation, Evidence]] = []
        gaps: list[str] = []
        for association in associations:
            try:
                item = self.evidence.get_evidence(association.evidence_id)
            except KeyError:
                gaps.append(f"Evidence {association.evidence_id} is missing from the canonical store.")
                continue
            if item.available_at > as_of:
                gaps.append(f"Evidence {item.evidence_id} was not available at the information cutoff.")
                continue
            available.append((association, item))
        supporting = tuple(
            association.association_id
            for association, _ in available
            if association.direction == EvidenceDirection.SUPPORTING
        )
        counter = tuple(
            association.association_id
            for association, _ in available
            if association.direction == EvidenceDirection.COUNTER
        )
        neutral = tuple(
            association.association_id
            for association, _ in available
            if association.direction == EvidenceDirection.NEUTRAL
        )
        warnings = tuple(sorted({warning for _, item in available for warning in item.quality_warnings}))

        if not available:
            verdict = EvidenceSetReadiness.NOT_READY
            gaps.append("No reviewed contextual evidence is available for this Thesis.")
            question = "What is the first source-backed fact that could support or reject this Thesis?"
        elif not supporting:
            verdict = EvidenceSetReadiness.NEEDS_SUPPORT
            gaps.append("No current supporting evidence is available.")
            question = "What independently verifiable evidence supports the core claim?"
        elif not counter:
            verdict = EvidenceSetReadiness.NEEDS_COUNTER
            gaps.append("No current counter evidence is available.")
            question = "What is the strongest evidence that could make this Thesis wrong?"
        elif warnings:
            verdict = EvidenceSetReadiness.NEEDS_QUALITY_REVIEW
            gaps.append("One or more selected sources have unresolved quality warnings.")
            question = "Can the material source-quality warning be resolved or explicitly justified?"
        else:
            verdict = EvidenceSetReadiness.READY_FOR_HUMAN_REVIEW
            question = "Does the strongest counter evidence invalidate or materially weaken the core claim?"

        approval_id: str | None = None
        if self.reviews is not None and available:
            try:
                latest = self.reviews.latest_for_thesis(thesis_id, as_of)
            except KeyError:
                latest = None
            current_ids = {association.association_id for association, _ in available}
            if (
                latest is not None
                and latest.decision == EvidenceSetReviewDecision.APPROVE
                and set(latest.association_ids) == current_ids
                and latest.information_cutoff <= as_of
            ):
                verdict = EvidenceSetReadiness.APPROVED_FOR_INITIALIZATION
                approval_id = latest.review_id
                gaps = []
                question = "Has the reviewed initialization proposal preserved this exact evidence cutoff?"

        return ThesisEvidenceReadiness(
            thesis_id,
            as_of,
            verdict,
            supporting,
            counter,
            neutral,
            tuple(dict.fromkeys(gaps)),
            warnings,
            question,
            approval_id,
        )
