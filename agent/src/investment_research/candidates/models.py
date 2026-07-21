"""Research-priority outputs that remain distinct from trade instructions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import (
    ActionLevel,
    AssessmentVerdict,
    MarketRegime,
    OpportunityStatus,
    Permanence,
    ResearchPriority,
    ThesisStatus,
    confidence_band,
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ResearchCandidate:
    candidate_id: str
    opportunity_id: str
    asset_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if not self.candidate_id or not self.opportunity_id or not self.asset_id:
            raise ValueError("candidate identity, opportunity, and asset are required")


@dataclass(frozen=True, slots=True)
class ActionAssessment:
    assessment_id: str
    candidate_id: str
    version_number: int
    opportunity_version_id: str
    thesis_version_id: str
    evidence_set_id: str
    market_state_id: str
    action_level: ActionLevel
    research_priority: ResearchPriority
    thesis_integrity: AssessmentVerdict
    mispricing_strength: AssessmentVerdict
    fundamental_integrity: AssessmentVerdict
    evidence_completeness: AssessmentVerdict
    market_context_fit: AssessmentVerdict
    asset_expression_quality: AssessmentVerdict
    thesis_status_snapshot: ThesisStatus
    opportunity_status_snapshot: OpportunityStatus
    permanence_snapshot: Permanence
    market_regime_snapshot: MarketRegime
    evidence_complete: bool
    mispricing_significant: bool
    confidence: float
    rationale: str
    strongest_counter_case: str
    unknowns: tuple[str, ...]
    first_rejection_question: str
    effective_from: datetime
    next_review_at: datetime
    supersedes_assessment_id: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.effective_from, "effective_from")
        _require_aware(self.next_review_at, "next_review_at")
        confidence_band(self.confidence)
        references = (
            self.assessment_id,
            self.candidate_id,
            self.opportunity_version_id,
            self.thesis_version_id,
            self.evidence_set_id,
            self.market_state_id,
        )
        if not all(references):
            raise ValueError("assessment identity and version references are required")
        if self.version_number < 1:
            raise ValueError("assessment version number must be positive")
        if self.next_review_at < self.effective_from:
            raise ValueError("assessment next review cannot precede effective time")
        if not self.rationale.strip() or not self.strongest_counter_case.strip():
            raise ValueError("assessment requires rationale and strongest counter case")
        if not self.first_rejection_question.strip():
            raise ValueError("assessment requires a first rejection question")

