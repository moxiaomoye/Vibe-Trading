from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import (
    ActionLevel,
    EvidenceDirection,
    ExperimentSplit,
    OutcomeDirection,
    ProcessOutcomeClass,
    ProcessQuality,
    ResearchErrorType,
)
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.validation.models import (
    HistoricalOutcome,
    LockedResearchDecision,
    ProcessAssessment,
    ReplayManifest,
    ValidationCase,
)
from src.investment_research.validation.quality import HistoricalReplayValidator, ResearchQualityCalculator


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _manifest() -> ReplayManifest:
    return ReplayManifest(
        manifest_id="manifest-1",
        experiment_split=ExperimentSplit.HOLDOUT,
        evidence_cutoff=NOW,
        rules_frozen_at=NOW - timedelta(days=1),
        data_version="data-v1",
        code_version="code-v1",
        rule_version="rules-v1",
        model_version="model-v1",
        prompt_version="prompt-v1",
        modern_model_rerun=False,
        created_at=NOW + timedelta(minutes=1),
    )


def _decision() -> LockedResearchDecision:
    return LockedResearchDecision(
        decision_id="decision-1",
        manifest_id="manifest-1",
        candidate_id="candidate-1",
        assessment_id="assessment-1",
        opportunity_version_id="opportunity-version-1",
        thesis_version_id="thesis-version-1",
        evidence_set_id="evidence-set-1",
        action_level=ActionLevel.RESEARCH,
        confidence=0.78,
        evidence_cutoff=NOW,
        locked_at=NOW + timedelta(minutes=2),
    )


def _process(quality: ProcessQuality = ProcessQuality.SOUND) -> ProcessAssessment:
    errors = () if quality != ProcessQuality.FLAWED else (ResearchErrorType.CHEAP_NOT_MISPRICED,)
    return ProcessAssessment(
        process_assessment_id="process-1",
        decision_id="decision-1",
        quality=quality,
        point_in_time_clean=True,
        evidence_complete=True,
        counter_evidence_adequate=True,
        errors=errors,
        rationale="The research used a locked, two-sided evidence set.",
        assessed_at=NOW + timedelta(days=30),
    )


def _outcome(direction: OutcomeDirection = OutcomeDirection.POSITIVE) -> HistoricalOutcome:
    has_results = direction != OutcomeDirection.UNAVAILABLE
    return HistoricalOutcome(
        outcome_id="outcome-1",
        decision_id="decision-1",
        horizon_months=12,
        direction=direction,
        absolute_return=0.25 if has_results else None,
        benchmark_excess_return=0.12 if has_results else None,
        sector_excess_return=0.08 if has_results else None,
        maximum_drawdown=-0.18 if has_results else None,
        thesis_validated=True if has_results else None,
        attribution_validated=True if has_results else None,
        unknowable_event_occurred=False,
        event_description=None,
        revealed_at=NOW + timedelta(days=366),
    )


def _evidence(available_at: datetime = NOW) -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        provider="fixture",
        source_locator="fixture://evidence-1",
        title="Point-in-time public filing",
        summary="Public information available before the replay cutoff.",
        direction=EvidenceDirection.SUPPORTING,
        published_at=available_at - timedelta(minutes=5),
        available_at=available_at,
        observed_at=available_at + timedelta(minutes=1),
        content_hash="hash-evidence-1",
    )


def _evidence_set(as_of: datetime = NOW) -> EvidenceSet:
    return EvidenceSet("evidence-set-1", "thesis-ai", as_of, ("evidence-1",), as_of)


def test_replay_inputs_enforce_manifest_cutoff_and_point_in_time_evidence() -> None:
    validator = HistoricalReplayValidator()
    validator.validate_inputs(_manifest(), _decision(), _evidence_set(), (_evidence(),))

    with pytest.raises(ValueError, match="manifest"):
        validator.validate_inputs(_manifest(), replace(_decision(), manifest_id="other"), _evidence_set(), (_evidence(),))
    with pytest.raises(ValueError, match="cutoffs"):
        validator.validate_inputs(
            _manifest(), replace(_decision(), evidence_cutoff=NOW - timedelta(days=1)), _evidence_set(), (_evidence(),)
        )
    with pytest.raises(ValueError, match="different evidence set"):
        validator.validate_inputs(_manifest(), _decision(), replace(_evidence_set(), evidence_set_id="other"), (_evidence(),))
    with pytest.raises(ValueError, match="extends beyond"):
        validator.validate_inputs(_manifest(), _decision(), _evidence_set(NOW + timedelta(minutes=1)), (_evidence(),))
    with pytest.raises(ValueError, match="unavailable"):
        validator.validate_inputs(
            _manifest(), _decision(), _evidence_set(), (_evidence(NOW + timedelta(minutes=1)),)
        )


@pytest.mark.parametrize(
    ("quality", "direction", "expected"),
    [
        (ProcessQuality.SOUND, OutcomeDirection.POSITIVE, ProcessOutcomeClass.HIGH_QUALITY_SUCCESS),
        (ProcessQuality.SOUND, OutcomeDirection.NEGATIVE, ProcessOutcomeClass.REASONABLE_FAILURE),
        (ProcessQuality.FLAWED, OutcomeDirection.POSITIVE, ProcessOutcomeClass.LUCKY_GAIN),
        (ProcessQuality.FLAWED, OutcomeDirection.NEGATIVE, ProcessOutcomeClass.TYPICAL_ERROR),
        (ProcessQuality.UNDETERMINED, OutcomeDirection.POSITIVE, ProcessOutcomeClass.UNRESOLVED),
        (ProcessQuality.SOUND, OutcomeDirection.NEUTRAL, ProcessOutcomeClass.UNRESOLVED),
        (ProcessQuality.SOUND, OutcomeDirection.UNAVAILABLE, ProcessOutcomeClass.UNRESOLVED),
    ],
)
def test_process_and_outcome_are_classified_independently(
    quality: ProcessQuality, direction: OutcomeDirection, expected: ProcessOutcomeClass
) -> None:
    case = HistoricalReplayValidator().classify("case-1", _manifest(), _decision(), _process(quality), _outcome(direction))
    assert case.classification == expected


def test_unknowable_event_does_not_rewrite_a_sound_process_as_an_error() -> None:
    outcome = replace(
        _outcome(OutcomeDirection.NEGATIVE),
        unknowable_event_occurred=True,
        event_description="A material event was not public at the locked decision time.",
    )
    case = HistoricalReplayValidator().classify("case-1", _manifest(), _decision(), _process(), outcome)
    assert case.classification == ProcessOutcomeClass.REASONABLE_FAILURE


def test_research_quality_metrics_measure_process_quality_not_win_rate() -> None:
    validator = HistoricalReplayValidator()
    cases = (
        validator.classify("success", _manifest(), _decision(), _process(), _outcome()),
        validator.classify("failure", _manifest(), _decision(), _process(), _outcome(OutcomeDirection.NEGATIVE)),
        validator.classify(
            "lucky", _manifest(), _decision(), _process(ProcessQuality.FLAWED), _outcome(OutcomeDirection.POSITIVE)
        ),
        validator.classify(
            "error", _manifest(), _decision(), _process(ProcessQuality.FLAWED), _outcome(OutcomeDirection.NEGATIVE)
        ),
    )
    metrics = ResearchQualityCalculator().calculate(cases, missed_opportunity_count=1, eligible_public_opportunity_count=5)

    assert metrics.case_count == 4
    assert metrics.sound_process_count == 2
    assert metrics.flawed_process_count == 2
    assert metrics.process_precision == 0.5
    assert metrics.high_quality_success_count == 1
    assert metrics.reasonable_failure_count == 1
    assert metrics.lucky_gain_count == 1
    assert metrics.typical_error_count == 1
    assert metrics.missed_opportunity_rate == 0.2


def test_quality_metrics_count_explicit_research_errors_and_incomplete_evidence() -> None:
    process = replace(
        _process(ProcessQuality.FLAWED),
        point_in_time_clean=False,
        evidence_complete=False,
        errors=(ResearchErrorType.POINT_IN_TIME_CONTAMINATION, ResearchErrorType.STRUCTURAL_AS_TEMPORARY),
    )
    case = HistoricalReplayValidator().classify("case-1", _manifest(), _decision(), process, _outcome())
    metrics = ResearchQualityCalculator().calculate((case,), 0, 0)
    assert metrics.point_in_time_contamination_count == 1
    assert metrics.structural_as_temporary_count == 1
    assert metrics.evidence_omission_count == 1
    assert metrics.missed_opportunity_rate is None


def test_validation_models_reject_invalid_or_ambiguous_records() -> None:
    with pytest.raises(ValueError, match="frozen"):
        replace(_manifest(), rules_frozen_at=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="locked before"):
        replace(_decision(), locked_at=NOW - timedelta(minutes=1))
    with pytest.raises(ValueError, match="sound"):
        replace(_process(), errors=(ResearchErrorType.NARRATIVE_OVERREACH,))
    with pytest.raises(ValueError, match="at least one"):
        replace(_process(ProcessQuality.FLAWED), errors=())
    with pytest.raises(ValueError, match="explicitly classified"):
        replace(_process(ProcessQuality.FLAWED), point_in_time_clean=False)
    with pytest.raises(ValueError, match="performance results"):
        replace(_outcome(OutcomeDirection.UNAVAILABLE), sector_excess_return=0.1)
    with pytest.raises(ValueError, match="requires a description"):
        replace(_outcome(), unknowable_event_occurred=True)
    with pytest.raises(ValueError, match="after"):
        ValidationCase(
            "case-1", _manifest(), _decision(), _process(), replace(_outcome(), revealed_at=NOW),
            ProcessOutcomeClass.HIGH_QUALITY_SUCCESS,
        )
    with pytest.raises(ValueError, match="same decision"):
        ValidationCase(
            "case-1", _manifest(), _decision(), replace(_process(), decision_id="other"), _outcome(),
            ProcessOutcomeClass.HIGH_QUALITY_SUCCESS,
        )
    with pytest.raises(ValueError, match="classification"):
        ValidationCase(
            "case-1", _manifest(), _decision(), _process(), _outcome(), ProcessOutcomeClass.TYPICAL_ERROR
        )
    with pytest.raises(ValueError, match="negative"):
        ResearchQualityCalculator().calculate((), -1, 0)
