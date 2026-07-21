from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.application.evidence_readiness import ThesisEvidenceReadinessService
from src.investment_research.contracts import EvidenceDirection, ThesisScope
from src.investment_research.evidence.associations import EvidenceAssociation, EvidenceSubjectType
from src.investment_research.evidence.models import Evidence
from src.investment_research.evidence.readiness import (
    EvidenceSetReadiness,
    EvidenceSetReview,
    EvidenceSetReviewDecision,
)
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_evidence_associations import (
    SQLiteEvidenceAssociationRepository,
)
from src.investment_research.repositories.sqlite_evidence_set_reviews import (
    SQLiteEvidenceSetReviewRepository,
)
from src.investment_research.thesis.models import Thesis


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _setup(tmp_path):
    path = tmp_path / "research.sqlite3"
    research = SQLiteResearchRepository(path)
    research.save_thesis(Thesis("thesis-a", "Thesis A", None, NOW - timedelta(days=30), ThesisScope.THEME))
    associations = SQLiteEvidenceAssociationRepository(path)
    reviews = SQLiteEvidenceSetReviewRepository(path)
    service = ThesisEvidenceReadinessService(associations, research, reviews)
    return research, associations, reviews, service


def _add(
    research: SQLiteResearchRepository,
    associations: SQLiteEvidenceAssociationRepository,
    evidence_id: str,
    direction: EvidenceDirection,
    *,
    warnings: tuple[str, ...] = (),
    assessed_at: datetime = NOW,
) -> EvidenceAssociation:
    research.save_evidence(
        Evidence(
            evidence_id,
            "fixture",
            f"fixture://{evidence_id}",
            f"Evidence {evidence_id}",
            "A point-in-time public fact.",
            EvidenceDirection.NEUTRAL,
            NOW - timedelta(hours=2),
            NOW - timedelta(hours=1),
            NOW,
            f"hash-{evidence_id}",
            warnings,
        )
    )
    return associations.append(
        EvidenceAssociation.create(
            evidence_id,
            EvidenceSubjectType.THESIS,
            "thesis-a",
            direction,
            assessed_at,
            "analyst",
            f"Contextual {direction.value} assessment.",
        )
    )


def test_readiness_requires_both_sides_without_using_a_score(tmp_path) -> None:
    research, associations, _, service = _setup(tmp_path)
    assert service.assess("thesis-a", NOW).verdict == EvidenceSetReadiness.NOT_READY

    support = _add(research, associations, "support", EvidenceDirection.SUPPORTING)
    support_only = service.assess("thesis-a", NOW)
    assert support_only.verdict == EvidenceSetReadiness.NEEDS_COUNTER
    assert support_only.supporting_association_ids == (support.association_id,)

    counter = _add(research, associations, "counter", EvidenceDirection.COUNTER)
    ready = service.assess("thesis-a", NOW)
    assert ready.verdict == EvidenceSetReadiness.READY_FOR_HUMAN_REVIEW
    assert ready.counter_association_ids == (counter.association_id,)
    assert "score" not in ready.__dataclass_fields__


def test_quality_warning_requires_explicit_review(tmp_path) -> None:
    research, associations, _, service = _setup(tmp_path)
    _add(research, associations, "support", EvidenceDirection.SUPPORTING, warnings=("secondary source",))
    _add(research, associations, "counter", EvidenceDirection.COUNTER)

    readiness = service.assess("thesis-a", NOW)

    assert readiness.verdict == EvidenceSetReadiness.NEEDS_QUALITY_REVIEW
    assert readiness.quality_warnings == ("secondary source",)


def test_point_in_time_and_current_association_head_control_readiness(tmp_path) -> None:
    research, associations, _, service = _setup(tmp_path)
    support = _add(research, associations, "support", EvidenceDirection.SUPPORTING)
    _add(research, associations, "counter", EvidenceDirection.COUNTER)
    revised = associations.append(
        EvidenceAssociation.create(
            support.evidence_id,
            support.subject_type,
            support.subject_id,
            EvidenceDirection.NEUTRAL,
            NOW + timedelta(days=1),
            "analyst-2",
            "The later context no longer supports the claim.",
            support.association_id,
        )
    )

    assert service.assess("thesis-a", NOW).verdict == EvidenceSetReadiness.READY_FOR_HUMAN_REVIEW
    later = service.assess("thesis-a", NOW + timedelta(days=2))
    assert later.verdict == EvidenceSetReadiness.NEEDS_SUPPORT
    assert later.neutral_association_ids == (revised.association_id,)


def test_review_approval_is_append_only_idempotent_and_becomes_stale(tmp_path) -> None:
    research, associations, reviews, service = _setup(tmp_path)
    support = _add(research, associations, "support", EvidenceDirection.SUPPORTING)
    counter = _add(research, associations, "counter", EvidenceDirection.COUNTER)
    review = EvidenceSetReview.create(
        "thesis-a",
        (support.association_id, counter.association_id),
        NOW,
        EvidenceSetReviewDecision.APPROVE,
        "chief-analyst",
        "The claim survives the strongest known counter evidence.",
        NOW + timedelta(minutes=5),
        counter.association_id,
        approval_reference="research-committee-2026-07-21",
    )

    assert reviews.record(review) == review
    assert reviews.record(review) == review
    approved = service.assess("thesis-a", NOW + timedelta(minutes=10))
    assert approved.verdict == EvidenceSetReadiness.APPROVED_FOR_INITIALIZATION
    assert approved.approval_review_id == review.review_id

    _add(
        research,
        associations,
        "new-counter",
        EvidenceDirection.COUNTER,
        assessed_at=NOW + timedelta(days=1),
    )
    assert service.assess("thesis-a", NOW + timedelta(days=2)).verdict == (
        EvidenceSetReadiness.READY_FOR_HUMAN_REVIEW
    )


def test_approval_hard_gates_counter_quality_and_current_subject(tmp_path) -> None:
    research, associations, reviews, _ = _setup(tmp_path)
    support = _add(
        research,
        associations,
        "support",
        EvidenceDirection.SUPPORTING,
        warnings=("unverified translation",),
    )
    counter = _add(research, associations, "counter", EvidenceDirection.COUNTER)

    with pytest.raises(ValueError, match="exception rationale"):
        reviews.record(
            EvidenceSetReview.create(
                "thesis-a",
                (support.association_id, counter.association_id),
                NOW,
                EvidenceSetReviewDecision.APPROVE,
                "reviewer",
                "Reviewed both sides.",
                NOW + timedelta(minutes=1),
                counter.association_id,
                approval_reference="approval-1",
            )
        )
    approved = EvidenceSetReview.create(
        "thesis-a",
        (support.association_id, counter.association_id),
        NOW,
        EvidenceSetReviewDecision.APPROVE,
        "reviewer",
        "Reviewed both sides.",
        NOW + timedelta(minutes=1),
        counter.association_id,
        quality_exception_rationale="Checked the primary-language filing directly.",
        approval_reference="approval-1",
    )
    assert reviews.record(approved) == approved

    with pytest.raises(ValueError, match="strongest counter"):
        EvidenceSetReview.create(
            "thesis-a",
            (support.association_id,),
            NOW,
            EvidenceSetReviewDecision.APPROVE,
            "reviewer",
            "Incomplete review.",
            NOW + timedelta(minutes=1),
            approval_reference="approval-2",
        )


def test_non_approval_can_record_explicit_missing_evidence(tmp_path) -> None:
    research, associations, reviews, _ = _setup(tmp_path)
    support = _add(research, associations, "support", EvidenceDirection.SUPPORTING)
    review = EvidenceSetReview.create(
        "thesis-a",
        (support.association_id,),
        NOW,
        EvidenceSetReviewDecision.REQUEST_MORE_EVIDENCE,
        "reviewer",
        "Counter case is not represented.",
        NOW + timedelta(minutes=1),
        missing_evidence=("independent counter evidence",),
    )

    assert reviews.record(review) == review
    assert reviews.latest_for_thesis("thesis-a", NOW + timedelta(minutes=2)) == review
