"""SQLite persistence for immutable raw evidence and append-only research decisions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection
from ..evidence.associations import EvidenceAssociation
from ..evidence.inbox import (
    AcceptedEvidenceInboxItem,
    EvidenceInboxDecision,
    EvidenceInboxItem,
    EvidenceInboxReview,
    EvidenceInboxStatus,
    EvidenceInboxSubjectType,
    ReviewedEvidenceInboxItem,
)
from ..evidence.models import Evidence
from .sqlite import SCHEMA_VERSION, SQLiteResearchRepository
from .sqlite_evidence_associations import (
    EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
    SQLiteEvidenceAssociationRepository,
)


EVIDENCE_INBOX_SCHEMA_VERSION = 9


class SQLiteEvidenceInboxRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.research = SQLiteResearchRepository(path)
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
                CREATE TABLE IF NOT EXISTS evidence_inbox_items (
                    inbox_item_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_locator TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    quality_warnings_json TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    proposed_subject_type TEXT NOT NULL,
                    proposed_subject_id TEXT NOT NULL,
                    proposed_direction TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(
                        provider, source_locator, content_hash,
                        proposed_subject_type, proposed_subject_id
                    )
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_inbox_ingested
                    ON evidence_inbox_items(ingested_at DESC);
                CREATE TABLE IF NOT EXISTS evidence_inbox_reviews (
                    review_id TEXT PRIMARY KEY,
                    inbox_item_id TEXT NOT NULL UNIQUE
                        REFERENCES evidence_inbox_items(inbox_item_id),
                    decision TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    final_subject_type TEXT,
                    final_subject_id TEXT,
                    final_direction TEXT,
                    schema_version INTEGER NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (EVIDENCE_INBOX_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def ingest(self, item: EvidenceInboxItem) -> EvidenceInboxItem:
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO evidence_inbox_items VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.inbox_item_id, item.provider, item.source_locator, item.title, item.summary,
                        item.published_at.isoformat(), item.available_at.isoformat(), item.observed_at.isoformat(),
                        item.content_hash, json.dumps(item.quality_warnings, ensure_ascii=False, separators=(",", ":")),
                        item.ingested_at.isoformat(), item.proposed_subject_type.value,
                        item.proposed_subject_id, item.proposed_direction.value, EVIDENCE_INBOX_SCHEMA_VERSION,
                    ),
                )
            return item
        except sqlite3.IntegrityError as exc:
            existing = self._find_identity(item)
            if existing == item:
                return existing
            raise ValueError("evidence inbox identity already exists with different immutable content") from exc

    def review(self, review: EvidenceInboxReview) -> EvidenceInboxReview:
        if review.decision == EvidenceInboxDecision.ACCEPT:
            return self.accept(review).review
        item = self.get_item(review.inbox_item_id)
        if review.reviewed_at < item.ingested_at:
            raise ValueError("reviewed_at cannot be earlier than ingested_at")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT INTO evidence_inbox_reviews VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        review.review_id, review.inbox_item_id, review.decision.value, review.rationale,
                        review.reviewer, review.reviewed_at.isoformat(),
                        review.final_subject_type.value if review.final_subject_type else None,
                        review.final_subject_id,
                        review.final_direction.value if review.final_direction else None,
                        EVIDENCE_INBOX_SCHEMA_VERSION,
                    ),
                )
            return review
        except sqlite3.IntegrityError as exc:
            try:
                existing = self.get_review(review.inbox_item_id)
            except KeyError:
                raise ValueError("evidence inbox review identity conflicts with an existing review") from exc
            if existing == review:
                return existing
            raise ValueError("evidence inbox decisions are append-only and already finalized") from exc

    def accept(self, review: EvidenceInboxReview) -> AcceptedEvidenceInboxItem:
        if review.decision != EvidenceInboxDecision.ACCEPT:
            raise ValueError("accept requires an accept decision")
        item = self.get_item(review.inbox_item_id)
        if review.reviewed_at < item.ingested_at:
            raise ValueError("reviewed_at cannot be earlier than ingested_at")
        canonical_id = str(
            uuid5(
                NAMESPACE_URL,
                f"canonical-evidence:{item.provider}:{item.source_locator}:{item.content_hash}",
            )
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                evidence_row = connection.execute(
                    """SELECT * FROM evidence
                    WHERE provider = ? AND source_locator = ? AND content_hash = ?""",
                    (item.provider, item.source_locator, item.content_hash),
                ).fetchone()
                if evidence_row is None:
                    evidence = Evidence(
                        canonical_id, item.provider, item.source_locator, item.title, item.summary,
                        EvidenceDirection.NEUTRAL, item.published_at, item.available_at, item.observed_at,
                        item.content_hash, item.quality_warnings,
                    )
                    connection.execute(
                        """INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            evidence.evidence_id, evidence.provider, evidence.source_locator, evidence.title,
                            evidence.summary, evidence.direction.value, evidence.published_at.isoformat(),
                            evidence.available_at.isoformat(), evidence.observed_at.isoformat(),
                            evidence.content_hash,
                            json.dumps(evidence.quality_warnings, ensure_ascii=False, separators=(",", ":")),
                            SCHEMA_VERSION,
                        ),
                    )
                else:
                    evidence = self._decode_evidence(evidence_row)
                    expected = (
                        item.provider, item.source_locator, item.title, item.summary, item.published_at,
                        item.available_at, item.observed_at, item.content_hash, item.quality_warnings,
                    )
                    actual = (
                        evidence.provider, evidence.source_locator, evidence.title, evidence.summary,
                        evidence.published_at, evidence.available_at, evidence.observed_at,
                        evidence.content_hash, evidence.quality_warnings,
                    )
                    if actual != expected:
                        raise ValueError("canonical evidence identity conflicts with immutable source content")
                association = EvidenceAssociation.create(
                    evidence.evidence_id, review.final_subject_type, review.final_subject_id,
                    review.final_direction, review.reviewed_at, review.reviewer, review.rationale,
                )
                connection.execute(
                    """INSERT INTO evidence_inbox_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        review.review_id, review.inbox_item_id, review.decision.value, review.rationale,
                        review.reviewer, review.reviewed_at.isoformat(), review.final_subject_type.value,
                        review.final_subject_id, review.final_direction.value, EVIDENCE_INBOX_SCHEMA_VERSION,
                    ),
                )
                connection.execute(
                    """INSERT INTO evidence_associations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        association.association_id, association.evidence_id, association.subject_type.value,
                        association.subject_id, association.direction.value, association.assessed_at.isoformat(),
                        association.assessor, association.rationale, association.supersedes_association_id,
                        EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
                    ),
                )
            return AcceptedEvidenceInboxItem(review, evidence, association)
        except sqlite3.IntegrityError as exc:
            try:
                existing_review = self.get_review(review.inbox_item_id)
            except KeyError:
                raise ValueError("accepted evidence conflicts with existing contextual history") from exc
            if existing_review != review:
                raise ValueError("evidence inbox decisions are append-only and already finalized") from exc
            evidence = self._canonical_evidence(item)
            association = EvidenceAssociation.create(
                evidence.evidence_id, review.final_subject_type, review.final_subject_id,
                review.final_direction, review.reviewed_at, review.reviewer, review.rationale,
            )
            try:
                persisted = self.associations.get(association.association_id)
            except KeyError as key_error:
                raise ValueError("accepted evidence review is missing its contextual association") from key_error
            return AcceptedEvidenceInboxItem(existing_review, evidence, persisted)

    def get_item(self, inbox_item_id: str) -> EvidenceInboxItem:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_inbox_items WHERE inbox_item_id = ?", (inbox_item_id,)
            ).fetchone()
        if row is None:
            raise KeyError(inbox_item_id)
        return self._decode_item(row)

    def get_review(self, inbox_item_id: str) -> EvidenceInboxReview:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_inbox_reviews WHERE inbox_item_id = ?", (inbox_item_id,)
            ).fetchone()
        if row is None:
            raise KeyError(inbox_item_id)
        return self._decode_review(row)

    def list_items(
        self, status: EvidenceInboxStatus | None = None, limit: int = 100,
    ) -> list[ReviewedEvidenceInboxItem]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses: list[str] = []
        parameters: list[object] = []
        if status == EvidenceInboxStatus.PENDING:
            clauses.append("r.review_id IS NULL")
        elif status == EvidenceInboxStatus.ACCEPTED:
            clauses.append("r.decision = ?")
            parameters.append(EvidenceInboxDecision.ACCEPT.value)
        elif status == EvidenceInboxStatus.REJECTED:
            clauses.append("r.decision = ?")
            parameters.append(EvidenceInboxDecision.REJECT.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT i.*, r.review_id, r.decision, r.rationale, r.reviewer, r.reviewed_at,
                r.final_subject_type, r.final_subject_id, r.final_direction
                FROM evidence_inbox_items i
                LEFT JOIN evidence_inbox_reviews r ON r.inbox_item_id = i.inbox_item_id
                {where}
                ORDER BY i.ingested_at DESC, i.inbox_item_id
                LIMIT ?""",
                parameters,
            ).fetchall()
        result: list[ReviewedEvidenceInboxItem] = []
        for row in rows:
            review = self._decode_review(row) if row["review_id"] else None
            item_status = EvidenceInboxStatus.PENDING
            if review:
                item_status = (
                    EvidenceInboxStatus.ACCEPTED
                    if review.decision == EvidenceInboxDecision.ACCEPT
                    else EvidenceInboxStatus.REJECTED
                )
            result.append(ReviewedEvidenceInboxItem(self._decode_item(row), item_status, review))
        return result

    def status_counts(self) -> dict[EvidenceInboxStatus, int]:
        counts = {status: 0 for status in EvidenceInboxStatus}
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT CASE
                    WHEN r.review_id IS NULL THEN 'pending'
                    WHEN r.decision = 'accept' THEN 'accepted'
                    ELSE 'rejected'
                END AS status, COUNT(*) AS item_count
                FROM evidence_inbox_items i
                LEFT JOIN evidence_inbox_reviews r ON r.inbox_item_id = i.inbox_item_id
                GROUP BY status"""
            ).fetchall()
        for row in rows:
            counts[EvidenceInboxStatus(row["status"])] = int(row["item_count"])
        return counts

    def has_identity(self, item: EvidenceInboxItem) -> bool:
        """Return whether the exact immutable intake identity already exists."""
        return self._find_identity(item) is not None

    def provider_status_counts(self, provider: str) -> dict[EvidenceInboxStatus, int]:
        """Read-only operational counts for one evidence provider."""
        if not provider.strip():
            raise ValueError("provider must not be empty")
        counts = {status: 0 for status in EvidenceInboxStatus}
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT CASE
                    WHEN r.review_id IS NULL THEN 'pending'
                    WHEN r.decision = 'accept' THEN 'accepted'
                    ELSE 'rejected'
                END AS status, COUNT(*) AS item_count
                FROM evidence_inbox_items i
                LEFT JOIN evidence_inbox_reviews r ON r.inbox_item_id = i.inbox_item_id
                WHERE i.provider = ? GROUP BY status""",
                (provider,),
            ).fetchall()
        for row in rows:
            counts[EvidenceInboxStatus(row["status"])] = int(row["item_count"])
        return counts

    def _find_identity(self, item: EvidenceInboxItem) -> EvidenceInboxItem | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM evidence_inbox_items
                WHERE provider = ? AND source_locator = ? AND content_hash = ?
                  AND proposed_subject_type = ? AND proposed_subject_id = ?""",
                (
                    item.provider, item.source_locator, item.content_hash,
                    item.proposed_subject_type.value, item.proposed_subject_id,
                ),
            ).fetchone()
        return self._decode_item(row) if row else None

    def _canonical_evidence(self, item: EvidenceInboxItem) -> Evidence:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM evidence
                WHERE provider = ? AND source_locator = ? AND content_hash = ?""",
                (item.provider, item.source_locator, item.content_hash),
            ).fetchone()
        if row is None:
            raise KeyError(item.inbox_item_id)
        return self._decode_evidence(row)

    @staticmethod
    def _decode_item(row: sqlite3.Row) -> EvidenceInboxItem:
        return EvidenceInboxItem(
            row["inbox_item_id"], row["provider"], row["source_locator"], row["title"], row["summary"],
            datetime.fromisoformat(row["published_at"]), datetime.fromisoformat(row["available_at"]),
            datetime.fromisoformat(row["observed_at"]), row["content_hash"],
            tuple(json.loads(row["quality_warnings_json"])), datetime.fromisoformat(row["ingested_at"]),
            EvidenceInboxSubjectType(row["proposed_subject_type"]), row["proposed_subject_id"],
            EvidenceDirection(row["proposed_direction"]),
        )

    @staticmethod
    def _decode_review(row: sqlite3.Row) -> EvidenceInboxReview:
        return EvidenceInboxReview(
            row["review_id"], row["inbox_item_id"], EvidenceInboxDecision(row["decision"]),
            row["rationale"], row["reviewer"], datetime.fromisoformat(row["reviewed_at"]),
            EvidenceInboxSubjectType(row["final_subject_type"]) if row["final_subject_type"] else None,
            row["final_subject_id"], EvidenceDirection(row["final_direction"]) if row["final_direction"] else None,
        )

    @staticmethod
    def _decode_evidence(row: sqlite3.Row) -> Evidence:
        return Evidence(
            row["evidence_id"], row["provider"], row["source_locator"], row["title"], row["summary"],
            EvidenceDirection(row["direction"]), datetime.fromisoformat(row["published_at"]),
            datetime.fromisoformat(row["available_at"]), datetime.fromisoformat(row["observed_at"]),
            row["content_hash"], tuple(json.loads(row["quality_warnings_json"])),
        )
