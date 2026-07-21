"""Append-only SQLite ledger for human Evidence Set Reviews."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..contracts import EvidenceDirection
from ..evidence.associations import EvidenceSubjectType
from ..evidence.readiness import EvidenceSetReview, EvidenceSetReviewDecision
from .sqlite import SQLiteResearchRepository
from .sqlite_evidence_associations import SQLiteEvidenceAssociationRepository


EVIDENCE_SET_REVIEW_SCHEMA_VERSION = 11


class SQLiteEvidenceSetReviewRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        SQLiteResearchRepository(path)
        self.associations = SQLiteEvidenceAssociationRepository(path)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_set_reviews (
                    review_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id),
                    association_ids_json TEXT NOT NULL,
                    information_cutoff TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    strongest_counter_association_id TEXT
                        REFERENCES evidence_associations(association_id),
                    missing_evidence_json TEXT NOT NULL,
                    quality_exception_rationale TEXT,
                    approval_reference TEXT,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_set_reviews_thesis_time
                    ON evidence_set_reviews(thesis_id, reviewed_at DESC);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (EVIDENCE_SET_REVIEW_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def record(self, review: EvidenceSetReview) -> EvidenceSetReview:
        self._validate_references(review)
        with self._connect() as connection:
            try:
                connection.execute(
                    """INSERT INTO evidence_set_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        review.review_id,
                        review.thesis_id,
                        json.dumps(review.association_ids, ensure_ascii=False, separators=(",", ":")),
                        review.information_cutoff.isoformat(),
                        review.decision.value,
                        review.reviewer,
                        review.rationale,
                        review.reviewed_at.isoformat(),
                        review.strongest_counter_association_id,
                        json.dumps(review.missing_evidence, ensure_ascii=False, separators=(",", ":")),
                        review.quality_exception_rationale,
                        review.approval_reference,
                        EVIDENCE_SET_REVIEW_SCHEMA_VERSION,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                try:
                    existing = self.get(review.review_id)
                except KeyError:
                    raise ValueError("evidence set review conflicts with existing history") from exc
                if existing == review:
                    return existing
                raise ValueError("evidence set review identity exists with different content") from exc
        return review

    def _validate_references(self, review: EvidenceSetReview) -> None:
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM theses WHERE thesis_id = ?", (review.thesis_id,)
            ).fetchone() is None:
                raise ValueError("evidence set review references unknown thesis")
            placeholders = ",".join("?" for _ in review.association_ids)
            rows = connection.execute(
                f"""SELECT a.*, e.available_at, e.quality_warnings_json
                FROM evidence_associations a JOIN evidence e ON e.evidence_id = a.evidence_id
                WHERE a.association_id IN ({placeholders})""",
                review.association_ids,
            ).fetchall()
        if len(rows) != len(review.association_ids):
            raise ValueError("evidence set review references unknown association")
        current = self.associations.list_for_subject(
            EvidenceSubjectType.THESIS, review.thesis_id, review.information_cutoff
        )
        current_ids = {item.association_id for item in current}
        if not set(review.association_ids).issubset(current_ids):
            raise ValueError("evidence set review must use current Thesis associations at the cutoff")
        for row in rows:
            if row["subject_type"] != EvidenceSubjectType.THESIS.value or row["subject_id"] != review.thesis_id:
                raise ValueError("evidence set review association belongs to a different subject")
            if datetime.fromisoformat(row["available_at"]) > review.information_cutoff:
                raise ValueError("evidence set review contains evidence unavailable at the cutoff")
        if review.decision != EvidenceSetReviewDecision.APPROVE:
            return
        if set(review.association_ids) != current_ids:
            raise ValueError("approval must review the complete current Thesis evidence set")
        directions = {row["association_id"]: EvidenceDirection(row["direction"]) for row in rows}
        if EvidenceDirection.SUPPORTING not in directions.values():
            raise ValueError("approval requires supporting evidence")
        if EvidenceDirection.COUNTER not in directions.values():
            raise ValueError("approval requires counter evidence")
        if directions.get(review.strongest_counter_association_id) != EvidenceDirection.COUNTER:
            raise ValueError("strongest counter association must be counter evidence")
        warnings = tuple(
            warning
            for row in rows
            for warning in json.loads(row["quality_warnings_json"])
        )
        if warnings and not (review.quality_exception_rationale or "").strip():
            raise ValueError("approval with quality warnings requires an exception rationale")

    def get(self, review_id: str) -> EvidenceSetReview:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_set_reviews WHERE review_id = ?", (review_id,)
            ).fetchone()
        if row is None:
            raise KeyError(review_id)
        return self._decode(row)

    def list_for_thesis(self, thesis_id: str, as_of: datetime | None = None) -> list[EvidenceSetReview]:
        if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence_set_reviews WHERE thesis_id = ? ORDER BY reviewed_at, review_id",
                (thesis_id,),
            ).fetchall()
        reviews = [self._decode(row) for row in rows]
        return reviews if as_of is None else [item for item in reviews if item.reviewed_at <= as_of]

    def latest_for_thesis(self, thesis_id: str, as_of: datetime) -> EvidenceSetReview:
        reviews = self.list_for_thesis(thesis_id, as_of)
        if not reviews:
            raise KeyError(f"no evidence set review for {thesis_id}")
        return max(reviews, key=lambda item: (item.reviewed_at, item.review_id))

    @staticmethod
    def _decode(row: sqlite3.Row) -> EvidenceSetReview:
        return EvidenceSetReview(
            row["review_id"],
            row["thesis_id"],
            tuple(json.loads(row["association_ids_json"])),
            datetime.fromisoformat(row["information_cutoff"]),
            EvidenceSetReviewDecision(row["decision"]),
            row["reviewer"],
            row["rationale"],
            datetime.fromisoformat(row["reviewed_at"]),
            row["strongest_counter_association_id"],
            tuple(json.loads(row["missing_evidence_json"])),
            row["quality_exception_rationale"],
            row["approval_reference"],
        )
