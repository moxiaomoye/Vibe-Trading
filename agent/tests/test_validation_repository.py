from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import (
    ActionLevel,
    ExperimentSplit,
    OutcomeDirection,
    ProcessOutcomeClass,
    ProcessQuality,
    ResearchErrorType,
)
from src.investment_research.repositories.sqlite_validation import SQLiteValidationRepository
from src.investment_research.validation.models import (
    HistoricalOutcome,
    LockedResearchDecision,
    ProcessAssessment,
    ReplayManifest,
)
from src.investment_research.validation.quality import HistoricalReplayValidator, ResearchQualityCalculator


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _manifest() -> ReplayManifest:
    return ReplayManifest(
        "manifest-1", ExperimentSplit.HOLDOUT, NOW, NOW - timedelta(days=1),
        "data-v1", "code-v1", "rules-v1", "model-v1", "prompt-v1", False, NOW,
    )


def _decision() -> LockedResearchDecision:
    return LockedResearchDecision(
        "decision-1", "manifest-1", "candidate-1", "assessment-1", "opportunity-version-1",
        "thesis-version-1", "evidence-set-1", ActionLevel.RESEARCH, 0.78, NOW, NOW + timedelta(minutes=1),
    )


def _process(quality: ProcessQuality = ProcessQuality.SOUND) -> ProcessAssessment:
    errors = () if quality != ProcessQuality.FLAWED else (ResearchErrorType.CHEAP_NOT_MISPRICED,)
    return ProcessAssessment(
        "process-1", "decision-1", quality, True, True, True, errors,
        "Locked, two-sided research process.", NOW + timedelta(days=30),
    )


def _outcome(direction: OutcomeDirection = OutcomeDirection.POSITIVE) -> HistoricalOutcome:
    return HistoricalOutcome(
        "outcome-1", "decision-1", 12, direction, 0.25, 0.12, 0.08, -0.18,
        True, True, False, None, NOW + timedelta(days=366),
    )


def _case(case_id: str = "case-1"):
    return HistoricalReplayValidator().classify(case_id, _manifest(), _decision(), _process(), _outcome())


def test_validation_case_round_trip_is_append_only_and_atomic(tmp_path) -> None:
    repository = SQLiteValidationRepository(tmp_path / "research.sqlite3")
    case = _case()
    repository.save_manifest(case.manifest)
    repository.save_case(case)

    assert repository.get_case(case.case_id) == case
    with pytest.raises(Exception):
        repository.save_case(case)


def test_case_requires_a_saved_manifest(tmp_path) -> None:
    repository = SQLiteValidationRepository(tmp_path / "research.sqlite3")
    with pytest.raises(ValueError, match="manifest"):
        repository.save_case(_case())


def test_multiple_process_outcome_classes_are_persisted(tmp_path) -> None:
    repository = SQLiteValidationRepository(tmp_path / "research.sqlite3")
    manifest = _manifest()
    repository.save_manifest(manifest)
    decision = replace(_decision(), decision_id="decision-2")
    process = replace(
        _process(ProcessQuality.FLAWED),
        process_assessment_id="process-2",
        decision_id=decision.decision_id,
    )
    outcome = replace(
        _outcome(OutcomeDirection.POSITIVE),
        outcome_id="outcome-2",
        decision_id=decision.decision_id,
    )
    case = HistoricalReplayValidator().classify("case-2", manifest, decision, process, outcome)
    repository.save_case(case)

    assert repository.get_case("case-2").classification == ProcessOutcomeClass.LUCKY_GAIN


def test_quality_metrics_round_trip(tmp_path) -> None:
    repository = SQLiteValidationRepository(tmp_path / "research.sqlite3")
    case = _case()
    repository.save_manifest(case.manifest)
    repository.save_case(case)
    metrics = ResearchQualityCalculator().calculate((case,), 2, 10)
    repository.save_metrics("quality-1", case.manifest.manifest_id, NOW, metrics)

    assert repository.get_metrics("quality-1") == metrics
    with pytest.raises(Exception):
        repository.save_metrics("quality-2", case.manifest.manifest_id, NOW, metrics)
    with pytest.raises(KeyError):
        repository.get_metrics("missing")


def test_metrics_require_aware_calculation_time(tmp_path) -> None:
    repository = SQLiteValidationRepository(tmp_path / "research.sqlite3")
    repository.save_manifest(_manifest())
    metrics = ResearchQualityCalculator().calculate((), 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        repository.save_metrics("quality-1", "manifest-1", NOW.replace(tzinfo=None), metrics)
