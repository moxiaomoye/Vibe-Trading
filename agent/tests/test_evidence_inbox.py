from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import EvidenceDirection
from src.investment_research.evidence.inbox import (
    EvidenceInboxDecision,
    EvidenceInboxItem,
    EvidenceInboxReview,
    EvidenceInboxStatus,
    EvidenceInboxSubjectType,
)
from src.investment_research.repositories.sqlite_evidence_inbox import SQLiteEvidenceInboxRepository


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _item(item_id: str = "inbox-1") -> EvidenceInboxItem:
    return EvidenceInboxItem(
        item_id, "fixture", "fixture://capex", "CapEx evidence", "CapEx remains durable.",
        NOW - timedelta(hours=3), NOW - timedelta(hours=2), NOW - timedelta(hours=1),
        "content-hash-1", (), NOW, EvidenceInboxSubjectType.THESIS, "thesis-ai",
        EvidenceDirection.SUPPORTING,
    )


def _review(
    decision: EvidenceInboxDecision = EvidenceInboxDecision.ACCEPT,
) -> EvidenceInboxReview:
    if decision == EvidenceInboxDecision.ACCEPT:
        return EvidenceInboxReview(
            "review-1", "inbox-1", decision, "Source and relevance verified.", "analyst-1",
            NOW + timedelta(minutes=1), EvidenceInboxSubjectType.THESIS, "thesis-ai",
            EvidenceDirection.SUPPORTING,
        )
    return EvidenceInboxReview(
        "review-1", "inbox-1", decision, "Source is not decision-useful.", "analyst-1",
        NOW + timedelta(minutes=1),
    )


def test_inbox_ingestion_is_immutable_and_idempotent(tmp_path) -> None:
    repository = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    item = _item()

    assert repository.ingest(item) == item
    assert repository.ingest(item) == item
    assert repository.get_item(item.inbox_item_id) == item
    with pytest.raises(ValueError, match="different immutable content"):
        repository.ingest(replace(item, inbox_item_id="other-id", title="Changed title"))


@pytest.mark.parametrize("decision", [EvidenceInboxDecision.ACCEPT, EvidenceInboxDecision.REJECT])
def test_inbox_review_is_append_only_and_queryable_by_status(tmp_path, decision) -> None:
    repository = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    repository.ingest(_item())
    review = _review(decision)

    assert repository.review(review) == review
    assert repository.review(review) == review
    expected_status = (
        EvidenceInboxStatus.ACCEPTED
        if decision == EvidenceInboxDecision.ACCEPT
        else EvidenceInboxStatus.REJECTED
    )
    rows = repository.list_items(expected_status)
    assert len(rows) == 1
    assert rows[0].status == expected_status
    assert rows[0].review == review
    assert repository.list_items(EvidenceInboxStatus.PENDING) == []
    if decision == EvidenceInboxDecision.ACCEPT:
        accepted = repository.accept(review)
        assert accepted.evidence.direction == EvidenceDirection.NEUTRAL
        assert accepted.association.direction == EvidenceDirection.SUPPORTING
        assert accepted.association.subject_id == "thesis-ai"
    with pytest.raises(ValueError, match="append-only"):
        repository.review(replace(review, review_id="review-2", rationale="Changed decision rationale."))


def test_pending_evidence_is_not_treated_as_accepted(tmp_path) -> None:
    repository = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    repository.ingest(_item())
    pending = repository.list_items(EvidenceInboxStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].review is None
    assert repository.list_items(EvidenceInboxStatus.ACCEPTED) == []


def test_acceptance_requires_explicit_classification_and_rejection_has_none() -> None:
    with pytest.raises(ValueError, match="final subject and direction"):
        replace(_review(), final_direction=None)
    with pytest.raises(ValueError, match="cannot define"):
        EvidenceInboxReview(
            "review-x", "inbox-1", EvidenceInboxDecision.REJECT, "Rejected.", "analyst-1",
            NOW, EvidenceInboxSubjectType.THESIS, "thesis-ai", EvidenceDirection.COUNTER,
        )


def test_review_time_and_page_size_are_guarded(tmp_path) -> None:
    repository = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    repository.ingest(_item())
    with pytest.raises(ValueError, match="earlier than ingested"):
        repository.review(replace(_review(), reviewed_at=NOW - timedelta(seconds=1)))
    with pytest.raises(ValueError, match="between 1 and 1000"):
        repository.list_items(limit=0)


def test_same_source_is_materialized_once_but_can_have_different_contextual_directions(tmp_path) -> None:
    repository = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    first_item = _item("inbox-1")
    second_item = replace(
        first_item, inbox_item_id="inbox-2", proposed_subject_id="thesis-b",
        proposed_direction=EvidenceDirection.COUNTER,
    )
    repository.ingest(first_item)
    repository.ingest(second_item)
    first = repository.accept(_review())
    second_review = EvidenceInboxReview(
        "review-2", "inbox-2", EvidenceInboxDecision.ACCEPT, "Relevant counter evidence.",
        "analyst-2", NOW + timedelta(minutes=2), EvidenceInboxSubjectType.THESIS, "thesis-b",
        EvidenceDirection.COUNTER,
    )
    second = repository.accept(second_review)

    assert first.evidence.evidence_id == second.evidence.evidence_id
    assert first.association.direction == EvidenceDirection.SUPPORTING
    assert second.association.direction == EvidenceDirection.COUNTER
