"""Persistence for evidence bundles not owned by a Thesis."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..evidence.context import ContextEvidenceBundle, EvidenceSubjectType
from ..evidence.models import Evidence
from .sqlite import SQLiteResearchRepository


CONTEXT_EVIDENCE_SCHEMA_VERSION = 8


class SQLiteContextEvidenceRepository:
    def __init__(self, path: Path):
        self.path = path
        self.research = SQLiteResearchRepository(path)
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
                CREATE TABLE IF NOT EXISTS context_evidence_bundles (
                    evidence_bundle_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(subject_type, subject_id, as_of)
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (CONTEXT_EVIDENCE_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def save_bundle(self, bundle: ContextEvidenceBundle, evidence: tuple[Evidence, ...]) -> None:
        bundle.validate_point_in_time(evidence)
        for item in evidence:
            if item.evidence_id in bundle.evidence_ids:
                try:
                    self.research.save_evidence(item)
                except sqlite3.IntegrityError:
                    if self.research.get_evidence(item.evidence_id) != item:
                        raise ValueError("evidence identity already exists with different content") from None
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO context_evidence_bundles VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    bundle.evidence_bundle_id, bundle.subject_type.value, bundle.subject_id,
                    bundle.as_of.isoformat(), json.dumps(bundle.evidence_ids, separators=(",", ":")),
                    bundle.created_at.isoformat(), CONTEXT_EVIDENCE_SCHEMA_VERSION,
                ),
            )

    def get_bundle(self, evidence_bundle_id: str) -> tuple[ContextEvidenceBundle, tuple[Evidence, ...]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM context_evidence_bundles WHERE evidence_bundle_id = ?", (evidence_bundle_id,)
            ).fetchone()
        if row is None:
            raise KeyError(evidence_bundle_id)
        ids = tuple(json.loads(row["evidence_ids_json"]))
        bundle = ContextEvidenceBundle(
            row["evidence_bundle_id"], EvidenceSubjectType(row["subject_type"]), row["subject_id"],
            datetime.fromisoformat(row["as_of"]), ids, datetime.fromisoformat(row["created_at"]),
        )
        return bundle, tuple(self.research.get_evidence(evidence_id) for evidence_id in ids)
