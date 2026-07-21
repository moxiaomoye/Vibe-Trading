"""SQLite ledger for context-relative evidence classifications."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ..contracts import EvidenceDirection
from ..evidence.associations import EvidenceAssociation, EvidenceSubjectType
from .sqlite import SQLiteResearchRepository


EVIDENCE_ASSOCIATION_SCHEMA_VERSION = 10


class SQLiteEvidenceAssociationRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        SQLiteResearchRepository(path)
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
                CREATE TABLE IF NOT EXISTS evidence_associations (
                    association_id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    assessed_at TEXT NOT NULL,
                    assessor TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    supersedes_association_id TEXT UNIQUE
                        REFERENCES evidence_associations(association_id),
                    schema_version INTEGER NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_association_initial
                    ON evidence_associations(evidence_id, subject_type, subject_id)
                    WHERE supersedes_association_id IS NULL;
                CREATE INDEX IF NOT EXISTS idx_evidence_association_subject_pit
                    ON evidence_associations(subject_type, subject_id, assessed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_evidence_association_evidence_pit
                    ON evidence_associations(evidence_id, assessed_at DESC);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (EVIDENCE_ASSOCIATION_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def append(self, association: EvidenceAssociation) -> EvidenceAssociation:
        with self._connect() as connection:
            evidence = connection.execute(
                "SELECT available_at FROM evidence WHERE evidence_id = ?", (association.evidence_id,)
            ).fetchone()
            if evidence is None:
                raise ValueError("evidence association references unknown evidence")
            if datetime.fromisoformat(evidence["available_at"]) > association.assessed_at:
                raise ValueError("evidence association predates evidence availability")
            if association.supersedes_association_id:
                previous = connection.execute(
                    "SELECT * FROM evidence_associations WHERE association_id = ?",
                    (association.supersedes_association_id,),
                ).fetchone()
                if previous is None:
                    raise ValueError("superseded evidence association does not exist")
                if (
                    previous["evidence_id"] != association.evidence_id
                    or previous["subject_type"] != association.subject_type.value
                    or previous["subject_id"] != association.subject_id
                ):
                    raise ValueError("a superseding association must keep the same evidence and subject")
                if datetime.fromisoformat(previous["assessed_at"]) >= association.assessed_at:
                    raise ValueError("a superseding association must be assessed later")
                child = connection.execute(
                    "SELECT association_id FROM evidence_associations WHERE supersedes_association_id = ?",
                    (association.supersedes_association_id,),
                ).fetchone()
                if child is not None and child["association_id"] != association.association_id:
                    raise ValueError("evidence association history cannot branch")
            try:
                connection.execute(
                    """INSERT INTO evidence_associations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        association.association_id, association.evidence_id, association.subject_type.value,
                        association.subject_id, association.direction.value, association.assessed_at.isoformat(),
                        association.assessor, association.rationale, association.supersedes_association_id,
                        EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                try:
                    existing = self.get(association.association_id)
                except KeyError:
                    raise ValueError("evidence association conflicts with existing history") from exc
                if existing == association:
                    return existing
                raise ValueError("evidence association identity exists with different content") from exc
        return association

    def get(self, association_id: str) -> EvidenceAssociation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_associations WHERE association_id = ?", (association_id,)
            ).fetchone()
        if row is None:
            raise KeyError(association_id)
        return self._decode(row)

    def current(
        self,
        evidence_id: str,
        subject_type: EvidenceSubjectType,
        subject_id: str,
        as_of: datetime,
    ) -> EvidenceAssociation:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM evidence_associations
                WHERE evidence_id = ? AND subject_type = ? AND subject_id = ?""",
                (evidence_id, subject_type.value, subject_id),
            ).fetchall()
        candidates = [self._decode(row) for row in rows]
        candidates = [association for association in candidates if association.assessed_at <= as_of]
        if not candidates:
            raise KeyError(f"no evidence association for {evidence_id} and {subject_type.value}/{subject_id}")
        return max(candidates, key=lambda association: (association.assessed_at, association.association_id))

    def list_for_subject(
        self, subject_type: EvidenceSubjectType, subject_id: str, as_of: datetime,
    ) -> list[EvidenceAssociation]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM evidence_associations
                WHERE subject_type = ? AND subject_id = ?""",
                (subject_type.value, subject_id),
            ).fetchall()
        candidates = [self._decode(row) for row in rows]
        candidates = [association for association in candidates if association.assessed_at <= as_of]
        superseded = {
            association.supersedes_association_id
            for association in candidates
            if association.supersedes_association_id is not None
        }
        heads = [association for association in candidates if association.association_id not in superseded]
        return sorted(heads, key=lambda association: (association.assessed_at, association.association_id), reverse=True)

    @staticmethod
    def _decode(row: sqlite3.Row) -> EvidenceAssociation:
        return EvidenceAssociation(
            row["association_id"], row["evidence_id"], EvidenceSubjectType(row["subject_type"]),
            row["subject_id"], EvidenceDirection(row["direction"]), datetime.fromisoformat(row["assessed_at"]),
            row["assessor"], row["rationale"], row["supersedes_association_id"],
        )
