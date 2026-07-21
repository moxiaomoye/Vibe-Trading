"""AI-agnostic thesis review workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from ..contracts import ThesisStatus
from ..evidence.models import Evidence, EvidenceSet
from ..thesis.models import ResearchReview, ThesisVersion


@dataclass(frozen=True, slots=True)
class ReviewContext:
    review: ResearchReview
    current_version: ThesisVersion
    evidence_set: EvidenceSet
    evidence: tuple[Evidence, ...]
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    material_change: bool
    proposed_status: ThesisStatus
    confidence: float
    core_claim: str
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    catalysts: tuple[str, ...]
    kill_criteria: tuple[str, ...]
    change_summary: str
    next_review_at: datetime


class ThesisReviewer(Protocol):
    def review(self, context: ReviewContext) -> ReviewDecision: ...


class ResearchRepository(Protocol):
    def record_review_result(
        self,
        review_id: str,
        completed_at: datetime,
        resulting_version: ThesisVersion | None,
    ) -> None: ...


class ThesisReviewService:
    def __init__(self, repository: ResearchRepository, reviewer: ThesisReviewer):
        self.repository = repository
        self.reviewer = reviewer

    def run(self, context: ReviewContext) -> ThesisVersion | None:
        context.evidence_set.validate_point_in_time(context.evidence)
        decision = self.reviewer.review(context)
        known_ids = set(context.evidence_set.evidence_ids)
        referenced_ids = set(decision.supporting_evidence_ids) | set(decision.counter_evidence_ids)
        unknown_ids = referenced_ids - known_ids
        if unknown_ids:
            raise ValueError(f"reviewer referenced evidence outside the evidence set: {sorted(unknown_ids)}")

        if not decision.material_change:
            self.repository.record_review_result(context.review.review_id, context.reviewed_at, None)
            return None

        version = ThesisVersion(
            thesis_version_id=str(uuid4()),
            thesis_id=context.current_version.thesis_id,
            version_number=context.current_version.version_number + 1,
            status=decision.proposed_status,
            core_claim=decision.core_claim,
            confidence=decision.confidence,
            evidence_set_id=context.evidence_set.evidence_set_id,
            supporting_evidence_ids=decision.supporting_evidence_ids,
            counter_evidence_ids=decision.counter_evidence_ids,
            catalysts=decision.catalysts,
            kill_criteria=decision.kill_criteria,
            change_summary=decision.change_summary,
            effective_from=context.reviewed_at,
            next_review_at=decision.next_review_at,
            supersedes_version_id=context.current_version.thesis_version_id,
        )
        self.repository.record_review_result(context.review.review_id, context.reviewed_at, version)
        return version


@dataclass(frozen=True, slots=True)
class FixtureReviewer:
    """Deterministic reviewer for tests, local demos, and historical replay."""

    decision: ReviewDecision

    def review(self, context: ReviewContext) -> ReviewDecision:
        return self.decision
