from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from src.investment_research.contracts import EvidenceDirection, ThesisStatus
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.thesis.models import ResearchReview, Thesis, ThesisVersion


NOW = datetime(2026, 7, 21, tzinfo=timezone.utc)


def _seed(repository: SQLiteResearchRepository) -> None:
    repository.save_thesis(Thesis("thesis", "AI Infrastructure", None, NOW))
    repository.save_evidence(
        Evidence(
            "evidence",
            "fixture",
            "fixture://evidence",
            "Evidence",
            "Summary",
            EvidenceDirection.SUPPORTING,
            NOW,
            NOW,
            NOW,
            "hash",
        )
    )
    repository.save_evidence_set(EvidenceSet("set", "thesis", NOW, ("evidence",), NOW))
    repository.append_thesis_version(
        ThesisVersion(
            "v1",
            "thesis",
            1,
            ThesisStatus.ACTIVE,
            "Claim",
            0.8,
            "set",
            ("evidence",),
            (),
            (),
            ("Kill criterion",),
            "Initial",
            NOW,
            NOW + timedelta(days=30),
        )
    )


def test_record_review_result_rolls_back_version_when_review_is_not_pending(tmp_path) -> None:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    _seed(repository)
    version = ThesisVersion(
        "v2",
        "thesis",
        2,
        ThesisStatus.ACTIVE,
        "Updated claim",
        0.82,
        "set",
        ("evidence",),
        (),
        (),
        ("Kill criterion",),
        "Update",
        NOW + timedelta(days=1),
        NOW + timedelta(days=31),
        "v1",
    )

    with pytest.raises(ValueError, match="missing or no longer pending"):
        repository.record_review_result("missing-review", NOW + timedelta(days=1), version)

    assert repository.current_version("thesis", NOW + timedelta(days=2)).thesis_version_id == "v1"


def test_repository_rejects_future_evidence_set(tmp_path) -> None:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    repository.save_thesis(Thesis("thesis", "AI Infrastructure", None, NOW))
    repository.save_evidence(
        Evidence(
            "future",
            "fixture",
            "fixture://future",
            "Future evidence",
            "Summary",
            EvidenceDirection.SUPPORTING,
            NOW,
            NOW + timedelta(days=1),
            NOW + timedelta(days=1),
            "future-hash",
        )
    )

    with pytest.raises(ValueError, match="future evidence"):
        repository.save_evidence_set(EvidenceSet("set", "thesis", NOW, ("future",), NOW))


def test_repository_reads_thesis_and_due_review(tmp_path) -> None:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    _seed(repository)
    review = ResearchReview("review", "thesis", "v1", NOW)
    repository.schedule_review(review)

    assert repository.get_thesis("thesis").name == "AI Infrastructure"
    assert repository.due_reviews(NOW) == [review]
    repository.complete_review("review", NOW, None)
    assert repository.due_reviews(NOW + timedelta(days=1)) == []

    with pytest.raises(KeyError):
        repository.get_thesis("missing")
    with pytest.raises(KeyError):
        repository.current_version("thesis", NOW - timedelta(days=1))
    with pytest.raises(ValueError, match="timezone-aware"):
        repository.current_version("thesis", NOW.replace(tzinfo=None))


def test_repository_rejects_unknown_evidence_and_broken_version_chain(tmp_path) -> None:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    repository.save_thesis(Thesis("thesis", "AI Infrastructure", None, NOW))
    with pytest.raises(ValueError, match="unknown evidence"):
        repository.save_evidence_set(EvidenceSet("set", "thesis", NOW, ("missing",), NOW))

    _seed(SQLiteResearchRepository(tmp_path / "seeded.sqlite3"))
    seeded = SQLiteResearchRepository(tmp_path / "seeded.sqlite3")
    bad_parent = ThesisVersion(
        "v2",
        "thesis",
        2,
        ThesisStatus.ACTIVE,
        "Claim",
        0.8,
        "set",
        ("evidence",),
        (),
        (),
        ("Kill",),
        "Update",
        NOW + timedelta(days=1),
        NOW + timedelta(days=30),
        "wrong-parent",
    )
    with pytest.raises(ValueError, match="supersedes"):
        seeded.append_thesis_version(bad_parent)

    wrong_set = replace(bad_parent, supersedes_version_id="v1", evidence_set_id="missing-set")
    with pytest.raises(ValueError, match="evidence set"):
        seeded.append_thesis_version(wrong_set)


def test_repository_migrates_legacy_initialization_audit_link(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE thesis_initialization_audits (
                thesis_version_id TEXT PRIMARY KEY,
                initializer TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                initialized_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );
            """
        )

    SQLiteResearchRepository(path)

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(thesis_initialization_audits)")}
        version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert "evidence_set_review_id" in columns
    assert version == 3
