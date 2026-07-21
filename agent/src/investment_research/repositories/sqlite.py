"""SQLite adapter for the versioned investment-research core."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..contracts import EvidenceDirection, ReviewStatus, ThesisScope, ThesisStatus
from ..evidence.models import Evidence, EvidenceSet
from ..intelligence.daily_thesis import DailyThesisReport
from ..thesis.models import ResearchReview, Thesis, ThesisInitializationAudit, ThesisVersion


SCHEMA_VERSION = 3


def _dump_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _load_tuple(value: str) -> tuple[str, ...]:
    return tuple(json.loads(value))


class SQLiteResearchRepository:
    """Append-only storage with explicit point-in-time reads."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS theses (
                    thesis_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_thesis_id TEXT REFERENCES theses(thesis_id),
                    created_at TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_locator TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    quality_warnings_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(provider, source_locator, content_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_available_at ON evidence(available_at);
                CREATE TABLE IF NOT EXISTS evidence_sets (
                    evidence_set_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id),
                    as_of TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS thesis_versions (
                    thesis_version_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id),
                    version_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    core_claim TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    supporting_evidence_ids_json TEXT NOT NULL,
                    counter_evidence_ids_json TEXT NOT NULL,
                    catalysts_json TEXT NOT NULL,
                    kill_criteria_json TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    next_review_at TEXT NOT NULL,
                    supersedes_version_id TEXT REFERENCES thesis_versions(thesis_version_id),
                    schema_version INTEGER NOT NULL,
                    UNIQUE(thesis_id, version_number)
                );
                CREATE INDEX IF NOT EXISTS idx_thesis_versions_pit
                    ON thesis_versions(thesis_id, effective_from DESC, version_number DESC);
                CREATE TABLE IF NOT EXISTS research_reviews (
                    review_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id),
                    base_version_id TEXT NOT NULL REFERENCES thesis_versions(thesis_version_id),
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completed_at TEXT,
                    resulting_version_id TEXT REFERENCES thesis_versions(thesis_version_id),
                    failure_reason TEXT,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reviews_due
                    ON research_reviews(status, scheduled_for);
                CREATE TABLE IF NOT EXISTS thesis_initialization_audits (
                    thesis_version_id TEXT PRIMARY KEY REFERENCES thesis_versions(thesis_version_id),
                    initializer TEXT NOT NULL,
                    approval_reference TEXT NOT NULL,
                    evidence_set_review_id TEXT NOT NULL,
                    initialized_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_thesis_reports (
                    report_id TEXT PRIMARY KEY,
                    report_date TEXT NOT NULL,
                    information_cutoff TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    initialized_count INTEGER NOT NULL,
                    uninitialized_count INTEGER NOT NULL,
                    due_review_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(report_date, mode)
                );
                """
            )
            thesis_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(theses)").fetchall()
            }
            if "scope" not in thesis_columns:
                connection.execute("ALTER TABLE theses ADD COLUMN scope TEXT NOT NULL DEFAULT 'theme'")
            audit_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(thesis_initialization_audits)").fetchall()
            }
            if "evidence_set_review_id" not in audit_columns:
                connection.execute(
                    """ALTER TABLE thesis_initialization_audits
                    ADD COLUMN evidence_set_review_id TEXT NOT NULL DEFAULT 'legacy-unlinked'"""
                )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def save_thesis(self, thesis: Thesis) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO theses
                (thesis_id, name, parent_thesis_id, created_at, scope, schema_version)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    thesis.thesis_id,
                    thesis.name,
                    thesis.parent_thesis_id,
                    thesis.created_at.isoformat(),
                    thesis.scope.value,
                    SCHEMA_VERSION,
                ),
            )

    def get_thesis(self, thesis_id: str) -> Thesis:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM theses WHERE thesis_id = ?", (thesis_id,)).fetchone()
        if row is None:
            raise KeyError(thesis_id)
        return Thesis(
            thesis_id=row["thesis_id"],
            name=row["name"],
            parent_thesis_id=row["parent_thesis_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            scope=ThesisScope(row["scope"]),
        )

    def list_theses(self) -> list[Thesis]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM theses ORDER BY created_at, thesis_id").fetchall()
        return [
            Thesis(
                thesis_id=row["thesis_id"],
                name=row["name"],
                parent_thesis_id=row["parent_thesis_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                scope=ThesisScope(row["scope"]),
            )
            for row in rows
        ]

    def save_evidence(self, evidence: Evidence) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO evidence
                (evidence_id, provider, source_locator, title, summary, direction,
                 published_at, available_at, observed_at, content_hash,
                 quality_warnings_json, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evidence.evidence_id,
                    evidence.provider,
                    evidence.source_locator,
                    evidence.title,
                    evidence.summary,
                    evidence.direction.value,
                    evidence.published_at.isoformat(),
                    evidence.available_at.isoformat(),
                    evidence.observed_at.isoformat(),
                    evidence.content_hash,
                    _dump_tuple(evidence.quality_warnings),
                    SCHEMA_VERSION,
                ),
            )

    def get_evidence(self, evidence_id: str) -> Evidence:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return Evidence(
            row["evidence_id"], row["provider"], row["source_locator"], row["title"], row["summary"],
            EvidenceDirection(row["direction"]), datetime.fromisoformat(row["published_at"]),
            datetime.fromisoformat(row["available_at"]), datetime.fromisoformat(row["observed_at"]),
            row["content_hash"], _load_tuple(row["quality_warnings_json"]),
        )

    def save_evidence_set(self, evidence_set: EvidenceSet) -> None:
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in evidence_set.evidence_ids)
            rows = connection.execute(
                f"SELECT evidence_id, available_at FROM evidence WHERE evidence_id IN ({placeholders})",
                evidence_set.evidence_ids,
            ).fetchall()
            if len(rows) != len(evidence_set.evidence_ids):
                raise ValueError("evidence set contains unknown evidence ids")
            if any(datetime.fromisoformat(row["available_at"]) > evidence_set.as_of for row in rows):
                raise ValueError("evidence set contains future evidence")
            connection.execute(
                """INSERT INTO evidence_sets
                (evidence_set_id, thesis_id, as_of, evidence_ids_json, created_at, schema_version)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    evidence_set.evidence_set_id,
                    evidence_set.thesis_id,
                    evidence_set.as_of.isoformat(),
                    _dump_tuple(evidence_set.evidence_ids),
                    evidence_set.created_at.isoformat(),
                    SCHEMA_VERSION,
                ),
            )

    def get_evidence_set(self, evidence_set_id: str) -> EvidenceSet:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_sets WHERE evidence_set_id = ?", (evidence_set_id,)
            ).fetchone()
        if row is None:
            raise KeyError(evidence_set_id)
        return EvidenceSet(
            row["evidence_set_id"], row["thesis_id"], datetime.fromisoformat(row["as_of"]),
            _load_tuple(row["evidence_ids_json"]), datetime.fromisoformat(row["created_at"]),
        )

    def append_thesis_version(self, version: ThesisVersion) -> None:
        with self._connect() as connection:
            self._append_version(connection, version)

    def record_initialization(
        self,
        version: ThesisVersion,
        audit: ThesisInitializationAudit,
        next_review: ResearchReview,
    ) -> None:
        """Atomically create Version 1, its audit record, and its first scheduled review."""
        if audit.thesis_version_id != version.thesis_version_id:
            raise ValueError("initialization audit does not reference the proposed version")
        if next_review.base_version_id != version.thesis_version_id or next_review.thesis_id != version.thesis_id:
            raise ValueError("initialization review does not reference the proposed version and thesis")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                evidence_review = connection.execute(
                    """SELECT decision, approval_reference FROM evidence_set_reviews
                    WHERE review_id = ? AND thesis_id = ?""",
                    (audit.evidence_set_review_id, version.thesis_id),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                raise ValueError(
                    "initialization requires a persisted Evidence Set Review ledger"
                ) from exc
            if evidence_review is None:
                raise ValueError("initialization Evidence Set Review is not persisted for this thesis")
            if evidence_review["decision"] != "approve":
                raise ValueError("initialization Evidence Set Review is not approved")
            if evidence_review["approval_reference"] != audit.approval_reference:
                raise ValueError("initialization approval reference does not match persisted review")
            self._append_version(connection, version)
            connection.execute(
                """INSERT INTO thesis_initialization_audits
                (thesis_version_id, initializer, approval_reference, evidence_set_review_id,
                 initialized_at, schema_version)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    audit.thesis_version_id, audit.initializer, audit.approval_reference,
                    audit.evidence_set_review_id, audit.initialized_at.isoformat(), SCHEMA_VERSION,
                ),
            )
            connection.execute(
                """INSERT INTO research_reviews
                (review_id, thesis_id, base_version_id, scheduled_for, status,
                 completed_at, resulting_version_id, failure_reason, schema_version)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?)""",
                (
                    next_review.review_id, next_review.thesis_id, next_review.base_version_id,
                    next_review.scheduled_for.isoformat(), next_review.status.value, SCHEMA_VERSION,
                ),
            )

    def get_initialization_audit(self, thesis_version_id: str) -> ThesisInitializationAudit:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM thesis_initialization_audits WHERE thesis_version_id = ?", (thesis_version_id,)
            ).fetchone()
        if row is None:
            raise KeyError(thesis_version_id)
        return ThesisInitializationAudit(
            row["thesis_version_id"], row["initializer"], row["approval_reference"],
            row["evidence_set_review_id"], datetime.fromisoformat(row["initialized_at"]),
        )

    def current_version(self, thesis_id: str, as_of: datetime) -> ThesisVersion:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM thesis_versions
                WHERE thesis_id = ? AND effective_from <= ?
                ORDER BY effective_from DESC, version_number DESC LIMIT 1""",
                (thesis_id, as_of.isoformat()),
            ).fetchone()
        if row is None:
            raise KeyError(f"no version for {thesis_id} as of {as_of.isoformat()}")
        return self._decode_version(row)

    def list_thesis_versions(self, thesis_id: str) -> list[ThesisVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM thesis_versions WHERE thesis_id = ? ORDER BY version_number",
                (thesis_id,),
            ).fetchall()
        return [self._decode_version(row) for row in rows]

    def schedule_review(self, review: ResearchReview) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO research_reviews
                (review_id, thesis_id, base_version_id, scheduled_for, status,
                 completed_at, resulting_version_id, failure_reason, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review.review_id,
                    review.thesis_id,
                    review.base_version_id,
                    review.scheduled_for.isoformat(),
                    review.status.value,
                    None,
                    None,
                    None,
                    SCHEMA_VERSION,
                ),
            )

    def due_reviews(self, as_of: datetime) -> list[ResearchReview]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM research_reviews
                WHERE status = ? AND scheduled_for <= ? ORDER BY scheduled_for""",
                (ReviewStatus.PENDING.value, as_of.isoformat()),
            ).fetchall()
        return [self._decode_review(row) for row in rows]

    def complete_review(self, review_id: str, completed_at: datetime, resulting_version_id: str | None) -> None:
        with self._connect() as connection:
            self._complete_review(connection, review_id, completed_at, resulting_version_id)

    def record_review_result(
        self,
        review_id: str,
        completed_at: datetime,
        resulting_version: ThesisVersion | None,
    ) -> None:
        """Atomically append the resulting version and close its review."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if resulting_version is not None:
                self._append_version(connection, resulting_version)
            self._complete_review(
                connection,
                review_id,
                completed_at,
                resulting_version.thesis_version_id if resulting_version else None,
            )

    def save_daily_thesis_report(self, report: DailyThesisReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO daily_thesis_reports
                (report_id, report_date, information_cutoff, generated_at, mode,
                 initialized_count, uninitialized_count, due_review_count,
                 payload_json, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.report_id,
                    report.report_date.isoformat(),
                    report.information_cutoff.isoformat(),
                    report.generated_at.isoformat(),
                    report.mode,
                    report.initialized_count,
                    report.uninitialized_count,
                    report.due_review_count,
                    json.dumps(report.to_dict(), ensure_ascii=False, separators=(",", ":")),
                    SCHEMA_VERSION,
                ),
            )

    def get_daily_thesis_report(self, report_date: date, mode: str = "shadow") -> DailyThesisReport:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_thesis_reports WHERE report_date = ? AND mode = ?",
                (report_date.isoformat(), mode),
            ).fetchone()
        if row is None:
            raise KeyError(f"no {mode} daily thesis report for {report_date.isoformat()}")
        return DailyThesisReport.from_dict(json.loads(row["payload_json"]))

    @staticmethod
    def _complete_review(
        connection: sqlite3.Connection,
        review_id: str,
        completed_at: datetime,
        resulting_version_id: str | None,
    ) -> None:
        cursor = connection.execute(
            """UPDATE research_reviews SET status = ?, completed_at = ?, resulting_version_id = ?
            WHERE review_id = ? AND status = ?""",
            (
                ReviewStatus.COMPLETED.value,
                completed_at.isoformat(),
                resulting_version_id,
                review_id,
                ReviewStatus.PENDING.value,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("review is missing or no longer pending")

    @staticmethod
    def _append_version(connection: sqlite3.Connection, version: ThesisVersion) -> None:
        latest = connection.execute(
            """SELECT thesis_version_id, version_number
            FROM thesis_versions WHERE thesis_id = ?
            ORDER BY version_number DESC LIMIT 1""",
            (version.thesis_id,),
        ).fetchone()
        expected = 1 if latest is None else latest["version_number"] + 1
        if version.version_number != expected:
            raise ValueError(f"version must be sequential; expected {expected}")
        expected_parent = None if latest is None else latest["thesis_version_id"]
        if version.supersedes_version_id != expected_parent:
            raise ValueError("supersedes_version_id must reference the latest version")
        evidence_set = connection.execute(
            "SELECT thesis_id FROM evidence_sets WHERE evidence_set_id = ?",
            (version.evidence_set_id,),
        ).fetchone()
        if evidence_set is None or evidence_set["thesis_id"] != version.thesis_id:
            raise ValueError("version must reference an evidence set for the same thesis")
        connection.execute(
            """INSERT INTO thesis_versions
            (thesis_version_id, thesis_id, version_number, status, core_claim,
             confidence, evidence_set_id, supporting_evidence_ids_json,
             counter_evidence_ids_json, catalysts_json, kill_criteria_json,
             change_summary, effective_from, next_review_at,
             supersedes_version_id, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                version.thesis_version_id,
                version.thesis_id,
                version.version_number,
                version.status.value,
                version.core_claim,
                version.confidence,
                version.evidence_set_id,
                _dump_tuple(version.supporting_evidence_ids),
                _dump_tuple(version.counter_evidence_ids),
                _dump_tuple(version.catalysts),
                _dump_tuple(version.kill_criteria),
                version.change_summary,
                version.effective_from.isoformat(),
                version.next_review_at.isoformat(),
                version.supersedes_version_id,
                SCHEMA_VERSION,
            ),
        )

    @staticmethod
    def _decode_version(row: sqlite3.Row) -> ThesisVersion:
        return ThesisVersion(
            thesis_version_id=row["thesis_version_id"],
            thesis_id=row["thesis_id"],
            version_number=row["version_number"],
            status=ThesisStatus(row["status"]),
            core_claim=row["core_claim"],
            confidence=row["confidence"],
            evidence_set_id=row["evidence_set_id"],
            supporting_evidence_ids=_load_tuple(row["supporting_evidence_ids_json"]),
            counter_evidence_ids=_load_tuple(row["counter_evidence_ids_json"]),
            catalysts=_load_tuple(row["catalysts_json"]),
            kill_criteria=_load_tuple(row["kill_criteria_json"]),
            change_summary=row["change_summary"],
            effective_from=datetime.fromisoformat(row["effective_from"]),
            next_review_at=datetime.fromisoformat(row["next_review_at"]),
            supersedes_version_id=row["supersedes_version_id"],
        )

    @staticmethod
    def _decode_review(row: sqlite3.Row) -> ResearchReview:
        return ResearchReview(
            review_id=row["review_id"],
            thesis_id=row["thesis_id"],
            base_version_id=row["base_version_id"],
            scheduled_for=datetime.fromisoformat(row["scheduled_for"]),
            status=ReviewStatus(row["status"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            resulting_version_id=row["resulting_version_id"],
            failure_reason=row["failure_reason"],
        )
