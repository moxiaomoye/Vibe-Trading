"""Fixed, non-AI Opportunity Alert eligibility policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..candidates.models import ActionAssessment
from ..contracts import ActionLevel, MarketRegime, OpportunityStatus, Permanence, ThesisStatus


@dataclass(frozen=True, slots=True)
class AlertEligibilityDecision:
    assessment_id: str
    eligible: bool
    failed_gates: tuple[str, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("alert evaluation time must be timezone-aware")
        if self.eligible == bool(self.failed_gates):
            raise ValueError("eligible decisions cannot have failed gates and ineligible decisions must have them")


@dataclass(frozen=True, slots=True)
class OpportunityAlert:
    alert_id: str
    candidate_id: str
    assessment_id: str
    opportunity_version_id: str
    evidence_set_id: str
    created_at: datetime
    disclaimer: str = "Research alert, not a trade instruction."

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("alert creation time must be timezone-aware")
        if not all((self.alert_id, self.candidate_id, self.assessment_id, self.opportunity_version_id, self.evidence_set_id)):
            raise ValueError("alert identity and research references are required")
        if not self.disclaimer.strip():
            raise ValueError("alert disclaimer is required")


@dataclass(frozen=True, slots=True)
class AlertEligibilityPolicy:
    minimum_confidence: float = 0.85
    eligible_regimes: tuple[MarketRegime, ...] = (MarketRegime.PANIC, MarketRegime.SYSTEMIC_STRESS)

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_confidence <= 1:
            raise ValueError("minimum confidence must be between 0 and 1")
        if not self.eligible_regimes:
            raise ValueError("at least one alert-eligible market regime is required")

    def evaluate(self, assessment: ActionAssessment, evaluated_at: datetime) -> AlertEligibilityDecision:
        failed: list[str] = []
        if assessment.action_level != ActionLevel.ACTION_CANDIDATE:
            failed.append("action_level")
        if assessment.confidence < self.minimum_confidence:
            failed.append("confidence")
        if assessment.thesis_status_snapshot != ThesisStatus.ACTIVE:
            failed.append("thesis_status")
        if not assessment.evidence_complete:
            failed.append("evidence_completeness")
        if assessment.market_regime_snapshot not in self.eligible_regimes:
            failed.append("market_regime")
        if not assessment.mispricing_significant:
            failed.append("mispricing_significance")
        if assessment.opportunity_status_snapshot not in {OpportunityStatus.OPEN, OpportunityStatus.STRENGTHENING}:
            failed.append("opportunity_status")
        if assessment.permanence_snapshot != Permanence.TEMPORARY:
            failed.append("permanence")
        return AlertEligibilityDecision(
            assessment_id=assessment.assessment_id,
            eligible=not failed,
            failed_gates=tuple(failed),
            evaluated_at=evaluated_at,
        )

    def create_alert(
        self,
        alert_id: str,
        assessment: ActionAssessment,
        evaluated_at: datetime,
    ) -> OpportunityAlert:
        decision = self.evaluate(assessment, evaluated_at)
        if not decision.eligible:
            raise ValueError(f"assessment is report-only; failed gates: {decision.failed_gates}")
        return OpportunityAlert(
            alert_id=alert_id,
            candidate_id=assessment.candidate_id,
            assessment_id=assessment.assessment_id,
            opportunity_version_id=assessment.opportunity_version_id,
            evidence_set_id=assessment.evidence_set_id,
            created_at=evaluated_at,
        )
