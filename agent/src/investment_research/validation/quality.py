"""Historical replay guards and process-first Research Quality metrics."""

from __future__ import annotations

from ..contracts import ProcessOutcomeClass, ProcessQuality, ResearchErrorType
from ..evidence.models import Evidence, EvidenceSet
from .models import (
    HistoricalOutcome,
    LockedResearchDecision,
    ProcessAssessment,
    ReplayManifest,
    ResearchQualityMetrics,
    ValidationCase,
    classify_process_outcome,
)


class HistoricalReplayValidator:
    def validate_inputs(
        self,
        manifest: ReplayManifest,
        decision: LockedResearchDecision,
        evidence_set: EvidenceSet,
        evidence: tuple[Evidence, ...],
    ) -> None:
        if decision.manifest_id != manifest.manifest_id:
            raise ValueError("locked decision does not belong to the replay manifest")
        if decision.evidence_cutoff != manifest.evidence_cutoff:
            raise ValueError("locked decision and replay manifest use different evidence cutoffs")
        if evidence_set.evidence_set_id != decision.evidence_set_id:
            raise ValueError("locked decision references a different evidence set")
        if evidence_set.as_of > manifest.evidence_cutoff:
            raise ValueError("replay evidence set extends beyond the manifest cutoff")
        evidence_set.validate_point_in_time(evidence)

    def classify(
        self,
        case_id: str,
        manifest: ReplayManifest,
        decision: LockedResearchDecision,
        process: ProcessAssessment,
        outcome: HistoricalOutcome,
    ) -> ValidationCase:
        classification = classify_process_outcome(process.quality, outcome.direction)
        return ValidationCase(case_id, manifest, decision, process, outcome, classification)


class ResearchQualityCalculator:
    def calculate(
        self,
        cases: tuple[ValidationCase, ...],
        missed_opportunity_count: int,
        eligible_public_opportunity_count: int,
    ) -> ResearchQualityMetrics:
        if missed_opportunity_count < 0 or eligible_public_opportunity_count < 0:
            raise ValueError("opportunity counts cannot be negative")
        classified = [case for case in cases if case.process.quality != ProcessQuality.UNDETERMINED]
        sound = sum(case.process.quality == ProcessQuality.SOUND for case in classified)
        flawed = sum(case.process.quality == ProcessQuality.FLAWED for case in classified)
        process_precision = sound / len(classified) if classified else None
        missed_rate = (
            missed_opportunity_count / eligible_public_opportunity_count
            if eligible_public_opportunity_count
            else None
        )
        return ResearchQualityMetrics(
            case_count=len(cases),
            classified_case_count=len(classified),
            sound_process_count=sound,
            flawed_process_count=flawed,
            high_quality_success_count=sum(case.classification == ProcessOutcomeClass.HIGH_QUALITY_SUCCESS for case in cases),
            reasonable_failure_count=sum(case.classification == ProcessOutcomeClass.REASONABLE_FAILURE for case in cases),
            lucky_gain_count=sum(case.classification == ProcessOutcomeClass.LUCKY_GAIN for case in cases),
            typical_error_count=sum(case.classification == ProcessOutcomeClass.TYPICAL_ERROR for case in cases),
            point_in_time_contamination_count=sum(
                ResearchErrorType.POINT_IN_TIME_CONTAMINATION in case.process.errors for case in cases
            ),
            structural_as_temporary_count=sum(
                ResearchErrorType.STRUCTURAL_AS_TEMPORARY in case.process.errors for case in cases
            ),
            evidence_omission_count=sum(not case.process.evidence_complete for case in cases),
            missed_opportunity_count=missed_opportunity_count,
            eligible_public_opportunity_count=eligible_public_opportunity_count,
            process_precision=process_precision,
            missed_opportunity_rate=missed_rate,
        )
