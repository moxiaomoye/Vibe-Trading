from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.application.initialization import (
    ThesisInitializationProposal,
    ThesisInitializationService,
)
from src.investment_research.contracts import EvidenceDirection, ThesisScope, ThesisStatus
from src.investment_research.evidence.associations import EvidenceAssociation, EvidenceSubjectType
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.evidence.readiness import (
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


def _evidence(evidence_id: str, direction: EvidenceDirection) -> Evidence:
    return Evidence(
        evidence_id, "fixture", f"fixture://{evidence_id}", f"Evidence {evidence_id}",
        "Point-in-time public evidence.", direction, NOW - timedelta(hours=1), NOW, NOW,
        f"hash-{evidence_id}",
    )


def _proposal() -> ThesisInitializationProposal:
    return ThesisInitializationProposal(
        ThesisStatus.ACTIVE,
        "AI infrastructure demand is supported by durable hyperscaler capital expenditure.",
        0.76,
        ("support-1",),
        ("counter-1",),
        ("capital expenditure acceleration",),
        ("multi-quarter capital expenditure contraction",),
        "Initial evidence-backed Thesis version.",
        NOW + timedelta(days=30),
        "research-committee-v2",
        "approval://fixture/initialization-1",
        "review-1",
    )


def _repository(tmp_path):
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    thesis = Thesis("thesis-ai", "AI Infrastructure", None, NOW, ThesisScope.THEME)
    support = _evidence("support-1", EvidenceDirection.SUPPORTING)
    counter = _evidence("counter-1", EvidenceDirection.COUNTER)
    repository.save_thesis(thesis)
    repository.save_evidence(support)
    repository.save_evidence(counter)
    evidence_set = EvidenceSet("set-1", thesis.thesis_id, NOW, (support.evidence_id, counter.evidence_id), NOW)
    repository.save_evidence_set(evidence_set)
    associations = (
        EvidenceAssociation.create(
            "support-1", EvidenceSubjectType.THESIS, thesis.thesis_id,
            EvidenceDirection.SUPPORTING, NOW, "analyst-1", "Supports this Thesis in context.",
        ),
        EvidenceAssociation.create(
            "counter-1", EvidenceSubjectType.THESIS, thesis.thesis_id,
            EvidenceDirection.COUNTER, NOW, "analyst-1", "Opposes this Thesis in context.",
        ),
    )
    review = EvidenceSetReview(
        "review-1", thesis.thesis_id, tuple(item.association_id for item in associations),
        NOW, EvidenceSetReviewDecision.APPROVE, "chief-analyst",
        "The Thesis survives its strongest known counter evidence.", NOW,
        associations[1].association_id, (), None, "approval://fixture/initialization-1",
    )
    association_repository = SQLiteEvidenceAssociationRepository(repository.path)
    for association in associations:
        association_repository.append(association)
    SQLiteEvidenceSetReviewRepository(repository.path).record(review)
    return repository, thesis, evidence_set, (support, counter), review, associations


def test_initialization_atomically_creates_version_audit_and_review(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    version = ThesisInitializationService(repository).initialize(
        thesis, evidence_set, evidence, _proposal(), NOW, review, associations
    )

    assert version.version_number == 1
    assert version.status == ThesisStatus.ACTIVE
    assert repository.current_version(thesis.thesis_id, NOW) == version
    audit = repository.get_initialization_audit(version.thesis_version_id)
    assert audit.approval_reference == "approval://fixture/initialization-1"
    assert audit.evidence_set_review_id == "review-1"
    due = repository.due_reviews(NOW + timedelta(days=31))
    assert len(due) == 1
    assert due[0].base_version_id == version.thesis_version_id


def test_identical_initialization_is_idempotent_but_changed_proposal_is_rejected(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    service = ThesisInitializationService(repository)
    first = service.initialize(thesis, evidence_set, evidence, _proposal(), NOW, review, associations)
    assert service.initialize(thesis, evidence_set, evidence, _proposal(), NOW, review, associations) == first
    with pytest.raises(ValueError, match="already"):
        service.initialize(
            thesis, evidence_set, evidence, replace(_proposal(), confidence=0.74), NOW,
            review, associations,
        )


@pytest.mark.parametrize(
    ("proposal", "message"),
    [
        (replace(_proposal(), supporting_evidence_ids=()), "both supporting and counter"),
        (replace(_proposal(), counter_evidence_ids=()), "both supporting and counter"),
        (replace(_proposal(), catalysts=()), "catalysts"),
        (replace(_proposal(), kill_criteria=()), "kill criteria"),
        (replace(_proposal(), initializer=""), "initializer"),
        (replace(_proposal(), approval_reference=""), "approval"),
        (replace(_proposal(), evidence_set_review_id=""), "Evidence Set Review id"),
        (replace(_proposal(), next_review_at=NOW), "after initialization"),
        (replace(_proposal(), status=ThesisStatus.DRAFT), "active or weakening"),
        (replace(_proposal(), supporting_evidence_ids=("missing",)), "outside the set"),
    ],
)
def test_initialization_rejects_incomplete_research_contract(tmp_path, proposal, message: str) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    with pytest.raises(ValueError, match=message):
        ThesisInitializationService(repository).initialize(
            thesis, evidence_set, evidence, proposal, NOW, review, associations
        )


def test_initialization_rejects_direction_mismatch_and_future_evidence(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    service = ThesisInitializationService(repository)
    with pytest.raises(ValueError, match="classified as supporting"):
        service.initialize(
            thesis, evidence_set, evidence,
            replace(_proposal(), supporting_evidence_ids=("counter-1",), counter_evidence_ids=("support-1",)),
            NOW, review, associations,
        )
    future_set = replace(evidence_set, as_of=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="precede"):
        service.initialize(thesis, future_set, evidence, _proposal(), NOW, review, associations)


def test_initialization_references_the_correct_thesis(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    with pytest.raises(ValueError, match="different thesis"):
        ThesisInitializationService(repository).initialize(
            replace(thesis, thesis_id="other"), evidence_set, evidence, _proposal(), NOW,
            review, associations,
        )


def test_initialization_uses_contextual_associations_for_neutral_evidence(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    neutral_evidence = tuple(replace(item, direction=EvidenceDirection.NEUTRAL) for item in evidence)
    version = ThesisInitializationService(repository).initialize(
        thesis, evidence_set, neutral_evidence, _proposal(), NOW, review, associations
    )
    assert version.version_number == 1


def test_initialization_rejects_wrong_or_missing_contextual_associations(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    wrong_subject = (
        EvidenceAssociation.create(
            "support-1", EvidenceSubjectType.THESIS, "other-thesis", EvidenceDirection.SUPPORTING,
            NOW, "analyst-1", "Wrong subject.",
        ),
        EvidenceAssociation.create(
            "counter-1", EvidenceSubjectType.THESIS, thesis.thesis_id, EvidenceDirection.COUNTER,
            NOW, "analyst-1", "Counter evidence.",
        ),
    )
    with pytest.raises(ValueError, match="different subject"):
        ThesisInitializationService(repository).initialize(
            thesis, evidence_set, evidence, _proposal(), NOW, review, wrong_subject
        )
    with pytest.raises(ValueError, match="lacks contextual associations"):
        ThesisInitializationService(repository).initialize(
            thesis, evidence_set, evidence, _proposal(), NOW, review, wrong_subject[1:]
        )


def test_initialization_cannot_bypass_or_mismatch_evidence_set_review(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    service = ThesisInitializationService(repository)

    with pytest.raises(ValueError, match="different Evidence Set Review"):
        service.initialize(
            thesis, evidence_set, evidence, _proposal(), NOW,
            replace(review, review_id="another-review"), associations,
        )
    with pytest.raises(ValueError, match="approved Evidence Set Review"):
        service.initialize(
            thesis, evidence_set, evidence, _proposal(), NOW,
            replace(review, decision=EvidenceSetReviewDecision.REQUEST_MORE_EVIDENCE), associations,
        )
    with pytest.raises(ValueError, match="approval reference"):
        service.initialize(
            thesis, evidence_set, evidence, _proposal(), NOW,
            replace(review, approval_reference="approval://different"), associations,
        )
    warned = (replace(evidence[0], quality_warnings=("source warning",)), evidence[1])
    with pytest.raises(ValueError, match="exception rationale"):
        service.initialize(
            thesis, evidence_set, warned, _proposal(), NOW, review, associations,
        )


def test_initialization_transaction_rejects_unpersisted_approval_object(tmp_path) -> None:
    repository, thesis, evidence_set, evidence, review, associations = _repository(tmp_path)
    fabricated = replace(review, review_id="fabricated-review")
    proposal = replace(_proposal(), evidence_set_review_id="fabricated-review")

    with pytest.raises(ValueError, match="not persisted"):
        ThesisInitializationService(repository).initialize(
            thesis, evidence_set, evidence, proposal, NOW, fabricated, associations,
        )

    assert repository.list_thesis_versions(thesis.thesis_id) == []
