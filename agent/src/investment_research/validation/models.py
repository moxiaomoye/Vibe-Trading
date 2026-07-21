"""Immutable historical-validation records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import (
    ActionLevel,
    ExperimentSplit,
    OutcomeDirection,
    ProcessOutcomeClass,
    ProcessQuality,
    ResearchErrorType,
    confidence_band,
)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def classify_process_outcome(quality: ProcessQuality, direction: OutcomeDirection) -> ProcessOutcomeClass:
    """Classify research process and realized outcome without conflating them."""
    if quality == ProcessQuality.UNDETERMINED or direction in {
        OutcomeDirection.NEUTRAL,
        OutcomeDirection.UNAVAILABLE,
    }:
        return ProcessOutcomeClass.UNRESOLVED
    if quality == ProcessQuality.SOUND and direction == OutcomeDirection.POSITIVE:
        return ProcessOutcomeClass.HIGH_QUALITY_SUCCESS
    if quality == ProcessQuality.SOUND and direction == OutcomeDirection.NEGATIVE:
        return ProcessOutcomeClass.REASONABLE_FAILURE
    if quality == ProcessQuality.FLAWED and direction == OutcomeDirection.POSITIVE:
        return ProcessOutcomeClass.LUCKY_GAIN
    return ProcessOutcomeClass.TYPICAL_ERROR


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    manifest_id: str
    experiment_split: ExperimentSplit
    evidence_cutoff: datetime
    rules_frozen_at: datetime
    data_version: str
    code_version: str
    rule_version: str
    model_version: str
    prompt_version: str
    modern_model_rerun: bool
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("evidence_cutoff", "rules_frozen_at", "created_at"):
            _require_aware(getattr(self, field_name), field_name)
        references = (
            self.manifest_id,
            self.data_version,
            self.code_version,
            self.rule_version,
            self.model_version,
            self.prompt_version,
        )
        if not all(references):
            raise ValueError("replay manifest versions and identity are required")
        if self.rules_frozen_at > self.evidence_cutoff:
            raise ValueError("replay rules must be frozen no later than the evidence cutoff")


@dataclass(frozen=True, slots=True)
class LockedResearchDecision:
    decision_id: str
    manifest_id: str
    candidate_id: str | None
    assessment_id: str | None
    opportunity_version_id: str | None
    thesis_version_id: str
    evidence_set_id: str
    action_level: ActionLevel
    confidence: float
    evidence_cutoff: datetime
    locked_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.evidence_cutoff, "evidence_cutoff")
        _require_aware(self.locked_at, "locked_at")
        confidence_band(self.confidence)
        if not all((self.decision_id, self.manifest_id, self.thesis_version_id, self.evidence_set_id)):
            raise ValueError("locked decision identity and research references are required")
        if self.locked_at < self.evidence_cutoff:
            raise ValueError("a research decision cannot be locked before its evidence cutoff")


@dataclass(frozen=True, slots=True)
class ProcessAssessment:
    process_assessment_id: str
    decision_id: str
    quality: ProcessQuality
    point_in_time_clean: bool
    evidence_complete: bool
    counter_evidence_adequate: bool
    errors: tuple[ResearchErrorType, ...]
    rationale: str
    assessed_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.assessed_at, "assessed_at")
        if not self.process_assessment_id or not self.decision_id or not self.rationale.strip():
            raise ValueError("process assessment identity and rationale are required")
        if self.quality == ProcessQuality.SOUND and self.errors:
            raise ValueError("a sound process assessment cannot contain research errors")
        if self.quality == ProcessQuality.FLAWED and not self.errors:
            raise ValueError("a flawed process assessment must classify at least one research error")
        if not self.point_in_time_clean and ResearchErrorType.POINT_IN_TIME_CONTAMINATION not in self.errors:
            raise ValueError("point-in-time contamination must be explicitly classified")


@dataclass(frozen=True, slots=True)
class HistoricalOutcome:
    outcome_id: str
    decision_id: str
    horizon_months: int
    direction: OutcomeDirection
    absolute_return: float | None
    benchmark_excess_return: float | None
    sector_excess_return: float | None
    maximum_drawdown: float | None
    thesis_validated: bool | None
    attribution_validated: bool | None
    unknowable_event_occurred: bool
    event_description: str | None
    revealed_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.revealed_at, "revealed_at")
        if not self.outcome_id or not self.decision_id or self.horizon_months < 1:
            raise ValueError("historical outcome identity and positive horizon are required")
        if self.direction == OutcomeDirection.UNAVAILABLE:
            if any(
                value is not None
                for value in (
                    self.absolute_return,
                    self.benchmark_excess_return,
                    self.sector_excess_return,
                    self.maximum_drawdown,
                )
            ):
                raise ValueError("an unavailable outcome cannot include performance results")
        if self.unknowable_event_occurred and not (self.event_description or "").strip():
            raise ValueError("an unknowable event requires a description")


@dataclass(frozen=True, slots=True)
class ValidationCase:
    case_id: str
    manifest: ReplayManifest
    decision: LockedResearchDecision
    process: ProcessAssessment
    outcome: HistoricalOutcome
    classification: ProcessOutcomeClass

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("validation case id is required")
        ids = {self.decision.decision_id, self.process.decision_id, self.outcome.decision_id}
        if len(ids) != 1 or self.decision.manifest_id != self.manifest.manifest_id:
            raise ValueError("validation case components do not share the same decision and manifest")
        if self.outcome.revealed_at <= self.decision.locked_at:
            raise ValueError("historical outcome must be revealed after the research decision is locked")
        expected = classify_process_outcome(self.process.quality, self.outcome.direction)
        if self.classification != expected:
            raise ValueError("validation case classification does not match process quality and outcome")


@dataclass(frozen=True, slots=True)
class ResearchQualityMetrics:
    case_count: int
    classified_case_count: int
    sound_process_count: int
    flawed_process_count: int
    high_quality_success_count: int
    reasonable_failure_count: int
    lucky_gain_count: int
    typical_error_count: int
    point_in_time_contamination_count: int
    structural_as_temporary_count: int
    evidence_omission_count: int
    missed_opportunity_count: int
    eligible_public_opportunity_count: int
    process_precision: float | None
    missed_opportunity_rate: float | None
