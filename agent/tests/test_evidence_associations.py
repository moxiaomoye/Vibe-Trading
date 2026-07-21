from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import EvidenceDirection
from src.investment_research.evidence.associations import EvidenceAssociation, EvidenceSubjectType
from src.investment_research.evidence.models import Evidence
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_evidence_associations import SQLiteEvidenceAssociationRepository


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _repositories(tmp_path):
    path = tmp_path / "research.sqlite3"
    research = SQLiteResearchRepository(path)
    research.save_evidence(
        Evidence(
            "evidence-1", "fixture", "fixture://fact", "Public fact", "One immutable public fact.",
            EvidenceDirection.NEUTRAL, NOW - timedelta(hours=2), NOW - timedelta(hours=1), NOW,
            "content-hash-1",
        )
    )
    return research, SQLiteEvidenceAssociationRepository(path)


def _association(subject_id: str, direction: EvidenceDirection) -> EvidenceAssociation:
    return EvidenceAssociation.create(
        "evidence-1", EvidenceSubjectType.THESIS, subject_id, direction, NOW,
        "analyst-1", f"Evidence is {direction.value} in this Thesis context.",
    )


def test_same_fact_can_support_one_thesis_and_oppose_another(tmp_path) -> None:
    _, repository = _repositories(tmp_path)
    supports = repository.append(_association("thesis-a", EvidenceDirection.SUPPORTING))
    counters = repository.append(_association("thesis-b", EvidenceDirection.COUNTER))

    assert repository.current("evidence-1", EvidenceSubjectType.THESIS, "thesis-a", NOW).direction == EvidenceDirection.SUPPORTING
    assert repository.current("evidence-1", EvidenceSubjectType.THESIS, "thesis-b", NOW).direction == EvidenceDirection.COUNTER
    assert repository.append(supports) == supports
    assert counters in repository.list_for_subject(EvidenceSubjectType.THESIS, "thesis-b", NOW)


def test_association_history_is_append_only_and_point_in_time(tmp_path) -> None:
    _, repository = _repositories(tmp_path)
    initial = repository.append(_association("thesis-a", EvidenceDirection.SUPPORTING))
    revised = EvidenceAssociation.create(
        initial.evidence_id, initial.subject_type, initial.subject_id, EvidenceDirection.COUNTER,
        NOW + timedelta(days=1), "analyst-2", "New evidence changes the contextual interpretation.",
        initial.association_id,
    )
    repository.append(revised)

    assert repository.current("evidence-1", EvidenceSubjectType.THESIS, "thesis-a", NOW) == initial
    assert repository.current(
        "evidence-1", EvidenceSubjectType.THESIS, "thesis-a", NOW + timedelta(days=2)
    ) == revised
    assert repository.list_for_subject(
        EvidenceSubjectType.THESIS, "thesis-a", NOW + timedelta(days=2)
    ) == [revised]


def test_association_rejects_future_unknown_and_branched_history(tmp_path) -> None:
    _, repository = _repositories(tmp_path)
    with pytest.raises(ValueError, match="unknown evidence"):
        repository.append(replace(_association("thesis-a", EvidenceDirection.SUPPORTING), evidence_id="missing"))
    with pytest.raises(ValueError, match="predates evidence availability"):
        repository.append(replace(_association("thesis-a", EvidenceDirection.SUPPORTING), assessed_at=NOW - timedelta(days=1)))

    initial = repository.append(_association("thesis-a", EvidenceDirection.SUPPORTING))
    revised = EvidenceAssociation.create(
        "evidence-1", EvidenceSubjectType.THESIS, "thesis-a", EvidenceDirection.COUNTER,
        NOW + timedelta(days=1), "analyst-2", "First revision.", initial.association_id,
    )
    repository.append(revised)
    branch = EvidenceAssociation.create(
        "evidence-1", EvidenceSubjectType.THESIS, "thesis-a", EvidenceDirection.NEUTRAL,
        NOW + timedelta(days=2), "analyst-3", "Conflicting branch.", initial.association_id,
    )
    with pytest.raises(ValueError, match="cannot branch"):
        repository.append(branch)


def test_association_requires_context_and_aware_time() -> None:
    with pytest.raises(ValueError, match="subject_id"):
        replace(_association("thesis-a", EvidenceDirection.SUPPORTING), subject_id="")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_association("thesis-a", EvidenceDirection.SUPPORTING), assessed_at=NOW.replace(tzinfo=None))


def test_point_in_time_reads_compare_instants_not_iso_offset_strings(tmp_path) -> None:
    _, repository = _repositories(tmp_path)
    china_time = timezone(timedelta(hours=8))
    association = replace(
        _association("thesis-a", EvidenceDirection.SUPPORTING),
        assessed_at=NOW.astimezone(china_time),
    )
    repository.append(association)

    as_of = NOW + timedelta(minutes=30)
    assert repository.current("evidence-1", EvidenceSubjectType.THESIS, "thesis-a", as_of) == association
    assert repository.list_for_subject(EvidenceSubjectType.THESIS, "thesis-a", as_of) == [association]
