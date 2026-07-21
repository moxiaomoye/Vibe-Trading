"""Evidence-first models for explaining possible market mispricing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import (
    AttributionCategory,
    AttributionRole,
    OpportunityStatus,
    Permanence,
    confidence_band,
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MarketImpliedView:
    view_id: str
    asset_id: str
    evidence_set_id: str
    as_of: datetime
    narrative: str
    implied_expectations: tuple[str, ...]
    priced_positives: tuple[str, ...]
    possible_overdiscounted_negatives: tuple[str, ...]
    unknowns: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        confidence_band(self.confidence)
        if not self.view_id or not self.asset_id or not self.evidence_set_id:
            raise ValueError("market-implied view identity and evidence set are required")
        if not self.narrative.strip() or not self.implied_expectations:
            raise ValueError("market-implied view needs a narrative and implied expectations")
        if not self.evidence_ids:
            raise ValueError("market-implied view must cite evidence")


@dataclass(frozen=True, slots=True)
class PriceMoveCause:
    category: AttributionCategory
    role: AttributionRole
    permanence: Permanence
    description: str
    relative_importance: float
    confidence: float
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    next_validation_event: str

    def __post_init__(self) -> None:
        confidence_band(self.confidence)
        if not 0 <= self.relative_importance <= 1:
            raise ValueError("relative importance must be between 0 and 1")
        if not self.description.strip() or not self.next_validation_event.strip():
            raise ValueError("cause description and next validation event are required")
        if set(self.supporting_evidence_ids) & set(self.counter_evidence_ids):
            raise ValueError("the same evidence cannot support and oppose one cause")
        if self.category != AttributionCategory.UNKNOWN and not self.supporting_evidence_ids:
            raise ValueError("a known attribution cause must cite supporting evidence")
        if self.category == AttributionCategory.UNKNOWN and self.permanence != Permanence.UNCERTAIN:
            raise ValueError("an unknown cause must remain uncertain")


@dataclass(frozen=True, slots=True)
class PriceMoveAttribution:
    attribution_id: str
    asset_id: str
    evidence_set_id: str
    window_start: datetime
    window_end: datetime
    causes: tuple[PriceMoveCause, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("window_start", "window_end", "created_at"):
            _require_aware(getattr(self, field_name), field_name)
        if self.window_end < self.window_start:
            raise ValueError("attribution window end cannot precede its start")
        if not self.attribution_id or not self.asset_id or not self.evidence_set_id:
            raise ValueError("attribution identity and evidence set are required")
        if not self.causes:
            raise ValueError("price move attribution must contain at least one cause")
        if not any(cause.role == AttributionRole.TRIGGER for cause in self.causes):
            raise ValueError("price move attribution must identify a trigger")

    @property
    def is_fully_unknown(self) -> bool:
        return all(cause.category == AttributionCategory.UNKNOWN for cause in self.causes)


@dataclass(frozen=True, slots=True)
class PermanenceAssessment:
    assessment_id: str
    evidence_set_id: str
    overall: Permanence
    rationale: str
    temporary_evidence_ids: tuple[str, ...]
    structural_evidence_ids: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    confidence: float
    as_of: datetime

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        confidence_band(self.confidence)
        if not self.assessment_id or not self.evidence_set_id or not self.rationale.strip():
            raise ValueError("permanence assessment identity and rationale are required")
        if self.overall == Permanence.UNCERTAIN and not self.unresolved_questions:
            raise ValueError("an uncertain assessment must state unresolved questions")
        if self.overall == Permanence.TEMPORARY and not self.temporary_evidence_ids:
            raise ValueError("a temporary assessment must cite temporary evidence")
        if self.overall == Permanence.STRUCTURAL and not self.structural_evidence_ids:
            raise ValueError("a structural assessment must cite structural evidence")


@dataclass(frozen=True, slots=True)
class MispricingOpportunity:
    opportunity_id: str
    thesis_id: str
    asset_id: str
    dedupe_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if not all((self.opportunity_id, self.thesis_id, self.asset_id, self.dedupe_key)):
            raise ValueError("opportunity identity, thesis, asset, and dedupe key are required")


@dataclass(frozen=True, slots=True)
class MispricingOpportunityVersion:
    opportunity_version_id: str
    opportunity_id: str
    version_number: int
    status: OpportunityStatus
    thesis_version_id: str
    exposure_id: str
    market_implied_view_id: str
    attribution_id: str
    permanence_assessment_id: str
    evidence_set_id: str
    research_view: str
    variant_wedge: str
    why_now: str
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    unknowns: tuple[str, ...]
    convergence_paths: tuple[str, ...]
    first_rejection_question: str
    kill_criteria: tuple[str, ...]
    confidence: float
    change_summary: str
    effective_from: datetime
    next_review_at: datetime
    supersedes_version_id: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.effective_from, "effective_from")
        _require_aware(self.next_review_at, "next_review_at")
        confidence_band(self.confidence)
        if self.version_number < 1:
            raise ValueError("opportunity version number must be positive")
        references = (
            self.opportunity_version_id,
            self.opportunity_id,
            self.thesis_version_id,
            self.exposure_id,
            self.market_implied_view_id,
            self.attribution_id,
            self.permanence_assessment_id,
            self.evidence_set_id,
        )
        if not all(references):
            raise ValueError("opportunity version references are required")
        if self.next_review_at < self.effective_from:
            raise ValueError("opportunity next review cannot precede effective time")
        if set(self.supporting_evidence_ids) & set(self.counter_evidence_ids):
            raise ValueError("the same evidence cannot support and oppose an opportunity")
        if self.status in {OpportunityStatus.OPEN, OpportunityStatus.STRENGTHENING}:
            if not all(
                (
                    self.research_view.strip(),
                    self.variant_wedge.strip(),
                    self.why_now.strip(),
                    self.supporting_evidence_ids,
                    self.counter_evidence_ids,
                    self.convergence_paths,
                    self.first_rejection_question.strip(),
                    self.kill_criteria,
                )
            ):
                raise ValueError("an active opportunity requires a complete two-sided research case")
