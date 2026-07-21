from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.application.review import (
    FixtureReviewer,
    ReviewContext,
    ReviewDecision,
    ThesisReviewService,
)
from src.investment_research.contracts import (
    ConfidenceBand,
    EvidenceDirection,
    ReviewStatus,
    ThesisStatus,
    confidence_band,
)
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.thesis.models import ResearchReview, Thesis, ThesisVersion


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _evidence(evidence_id: str = "evidence-1", available_at: datetime = NOW) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        provider="fixture",
        source_locator=f"fixture://{evidence_id}",
        title="Hyperscaler capital expenditure update",
        summary="Capital expenditure remains supportive of the infrastructure thesis.",
        direction=EvidenceDirection.SUPPORTING,
        published_at=available_at - timedelta(minutes=5),
        available_at=available_at,
        observed_at=available_at + timedelta(minutes=1),
        content_hash=f"hash-{evidence_id}",
    )


def _evidence_set(evidence_id: str = "evidence-1", as_of: datetime = NOW) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="evidence-set-1",
        thesis_id="thesis-ai",
        as_of=as_of,
        evidence_ids=(evidence_id,),
        created_at=as_of,
    )


def _version() -> ThesisVersion:
    return ThesisVersion(
        thesis_version_id="version-1",
        thesis_id="thesis-ai",
        version_number=1,
        status=ThesisStatus.ACTIVE,
        core_claim="AI infrastructure demand remains durable.",
        confidence=0.78,
        evidence_set_id="evidence-set-1",
        supporting_evidence_ids=("evidence-1",),
        counter_evidence_ids=(),
        catalysts=("capex acceleration",),
        kill_criteria=("multi-quarter hyperscaler capex contraction",),
        change_summary="Initial version",
        effective_from=NOW,
        next_review_at=NOW + timedelta(days=30),
    )


def _repository(tmp_path) -> SQLiteResearchRepository:
    repository = SQLiteResearchRepository(tmp_path / "investment-research.sqlite3")
    repository.save_thesis(Thesis("thesis-ai", "AI Infrastructure", None, NOW))
    repository.save_evidence(_evidence())
    repository.save_evidence_set(_evidence_set())
    repository.append_thesis_version(_version())
    return repository


def test_evidence_set_rejects_future_evidence() -> None:
    future = _evidence(available_at=NOW + timedelta(days=1))
    evidence_set = _evidence_set(as_of=NOW)

    with pytest.raises(ValueError, match="unavailable"):
        evidence_set.validate_point_in_time((future,))


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [(0.2, ConfidenceBand.LOW), (0.5, ConfidenceBand.MEDIUM), (0.7, ConfidenceBand.HIGH), (0.85, ConfidenceBand.VERY_HIGH)],
)
def test_confidence_bands(confidence: float, expected: ConfidenceBand) -> None:
    assert confidence_band(confidence) == expected


def test_domain_models_reject_invalid_boundaries() -> None:
    naive = NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        _evidence(available_at=naive)
    with pytest.raises(ValueError, match="must not be empty"):
        replace(_evidence(), title=" ")
    with pytest.raises(ValueError, match="earlier than published"):
        replace(_evidence(), available_at=NOW - timedelta(minutes=10))
    with pytest.raises(ValueError, match="earlier than available"):
        replace(_evidence(), observed_at=NOW - timedelta(minutes=1))
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(_version(), confidence=1.1)
    with pytest.raises(ValueError, match="positive"):
        replace(_version(), version_number=0)
    with pytest.raises(ValueError, match="precede"):
        replace(_version(), next_review_at=NOW - timedelta(days=1))
    with pytest.raises(ValueError, match="support and oppose"):
        replace(_version(), counter_evidence_ids=("evidence-1",))
    with pytest.raises(ValueError, match="kill criteria"):
        replace(_version(), kill_criteria=())


def test_evidence_set_and_review_contracts_reject_invalid_state() -> None:
    with pytest.raises(ValueError, match="at least one"):
        replace(_evidence_set(), evidence_ids=())
    with pytest.raises(ValueError, match="unique"):
        replace(_evidence_set(), evidence_ids=("evidence-1", "evidence-1"))
    with pytest.raises(ValueError, match="unknown evidence"):
        _evidence_set("missing").validate_point_in_time((_evidence(),))
    with pytest.raises(ValueError, match="completed_at"):
        ResearchReview("review", "thesis-ai", "version-1", NOW, ReviewStatus.COMPLETED)
    with pytest.raises(ValueError, match="failure_reason"):
        ResearchReview("review", "thesis-ai", "version-1", NOW, ReviewStatus.FAILED)
    completed = ResearchReview(
        "review",
        "thesis-ai",
        "version-1",
        NOW,
        ReviewStatus.COMPLETED,
        completed_at=NOW,
    )
    assert completed.completed_at == NOW


def test_thesis_versions_are_append_only_and_point_in_time(tmp_path) -> None:
    repository = _repository(tmp_path)
    second = replace(
        _version(),
        thesis_version_id="version-2",
        version_number=2,
        confidence=0.82,
        change_summary="New evidence strengthened the thesis",
        effective_from=NOW + timedelta(days=1),
        next_review_at=NOW + timedelta(days=31),
        supersedes_version_id="version-1",
    )
    repository.append_thesis_version(second)

    assert repository.current_version("thesis-ai", NOW).thesis_version_id == "version-1"
    assert repository.current_version("thesis-ai", NOW + timedelta(days=2)).thesis_version_id == "version-2"

    with pytest.raises(ValueError, match="sequential"):
        repository.append_thesis_version(second)


def test_material_review_creates_a_new_version(tmp_path) -> None:
    repository = _repository(tmp_path)
    review = ResearchReview("review-1", "thesis-ai", "version-1", NOW, ReviewStatus.PENDING)
    repository.schedule_review(review)
    decision = ReviewDecision(
        material_change=True,
        proposed_status=ThesisStatus.WEAKENING,
        confidence=0.71,
        core_claim="AI infrastructure demand remains durable but capex risk has increased.",
        supporting_evidence_ids=("evidence-1",),
        counter_evidence_ids=(),
        catalysts=("capex reacceleration",),
        kill_criteria=("multi-quarter hyperscaler capex contraction",),
        change_summary="Confidence reduced after review.",
        next_review_at=NOW + timedelta(days=7),
    )
    context = ReviewContext(review, _version(), _evidence_set(), (_evidence(),), NOW + timedelta(hours=1))

    result = ThesisReviewService(repository, FixtureReviewer(decision)).run(context)

    assert result is not None
    assert result.version_number == 2
    assert result.status == ThesisStatus.WEAKENING
    assert repository.due_reviews(NOW + timedelta(days=1)) == []


def test_non_material_review_does_not_create_a_version(tmp_path) -> None:
    repository = _repository(tmp_path)
    review = ResearchReview("review-1", "thesis-ai", "version-1", NOW)
    repository.schedule_review(review)
    decision = ReviewDecision(
        material_change=False,
        proposed_status=ThesisStatus.ACTIVE,
        confidence=0.78,
        core_claim=_version().core_claim,
        supporting_evidence_ids=("evidence-1",),
        counter_evidence_ids=(),
        catalysts=_version().catalysts,
        kill_criteria=_version().kill_criteria,
        change_summary="No material change.",
        next_review_at=NOW + timedelta(days=30),
    )
    context = ReviewContext(review, _version(), _evidence_set(), (_evidence(),), NOW + timedelta(hours=1))

    assert ThesisReviewService(repository, FixtureReviewer(decision)).run(context) is None
    assert repository.current_version("thesis-ai", NOW + timedelta(days=2)).version_number == 1


def test_reviewer_cannot_reference_unknown_evidence(tmp_path) -> None:
    repository = _repository(tmp_path)
    review = ResearchReview("review-1", "thesis-ai", "version-1", NOW)
    repository.schedule_review(review)
    decision = ReviewDecision(
        material_change=True,
        proposed_status=ThesisStatus.ACTIVE,
        confidence=0.8,
        core_claim=_version().core_claim,
        supporting_evidence_ids=("invented-evidence",),
        counter_evidence_ids=(),
        catalysts=_version().catalysts,
        kill_criteria=_version().kill_criteria,
        change_summary="Invalid fixture",
        next_review_at=NOW + timedelta(days=30),
    )
    context = ReviewContext(review, _version(), _evidence_set(), (_evidence(),), NOW + timedelta(hours=1))

    with pytest.raises(ValueError, match="outside the evidence set"):
        ThesisReviewService(repository, FixtureReviewer(decision)).run(context)
