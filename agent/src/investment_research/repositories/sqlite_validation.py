"""Append-only SQLite persistence for historical research validation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ..contracts import (
    ActionLevel,
    ExperimentSplit,
    OutcomeDirection,
    ProcessOutcomeClass,
    ProcessQuality,
    ResearchErrorType,
)
from ..validation.models import (
    HistoricalOutcome,
    LockedResearchDecision,
    ProcessAssessment,
    ReplayManifest,
    ResearchQualityMetrics,
    ValidationCase,
)
from .sqlite import SQLiteResearchRepository


VALIDATION_SCHEMA_VERSION = 5


class SQLiteValidationRepository:
    def __init__(self, path: Path):
        self.path = path
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
                CREATE TABLE IF NOT EXISTS replay_manifests (
                    manifest_id TEXT PRIMARY KEY,
                    experiment_split TEXT NOT NULL,
                    evidence_cutoff TEXT NOT NULL,
                    rules_frozen_at TEXT NOT NULL,
                    data_version TEXT NOT NULL,
                    code_version TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    modern_model_rerun INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS locked_research_decisions (
                    decision_id TEXT PRIMARY KEY,
                    manifest_id TEXT NOT NULL REFERENCES replay_manifests(manifest_id),
                    candidate_id TEXT,
                    assessment_id TEXT,
                    opportunity_version_id TEXT,
                    thesis_version_id TEXT NOT NULL,
                    evidence_set_id TEXT NOT NULL,
                    action_level TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_cutoff TEXT NOT NULL,
                    locked_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS process_assessments (
                    process_assessment_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL UNIQUE REFERENCES locked_research_decisions(decision_id),
                    quality TEXT NOT NULL,
                    point_in_time_clean INTEGER NOT NULL,
                    evidence_complete INTEGER NOT NULL,
                    counter_evidence_adequate INTEGER NOT NULL,
                    errors_json TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    assessed_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS historical_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL UNIQUE REFERENCES locked_research_decisions(decision_id),
                    horizon_months INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    absolute_return REAL,
                    benchmark_excess_return REAL,
                    sector_excess_return REAL,
                    maximum_drawdown REAL,
                    thesis_validated INTEGER,
                    attribution_validated INTEGER,
                    unknowable_event_occurred INTEGER NOT NULL,
                    event_description TEXT,
                    revealed_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS validation_cases (
                    case_id TEXT PRIMARY KEY,
                    manifest_id TEXT NOT NULL REFERENCES replay_manifests(manifest_id),
                    decision_id TEXT NOT NULL UNIQUE REFERENCES locked_research_decisions(decision_id),
                    process_assessment_id TEXT NOT NULL UNIQUE REFERENCES process_assessments(process_assessment_id),
                    outcome_id TEXT NOT NULL UNIQUE REFERENCES historical_outcomes(outcome_id),
                    classification TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_quality_reports (
                    report_id TEXT PRIMARY KEY,
                    manifest_id TEXT NOT NULL REFERENCES replay_manifests(manifest_id),
                    calculated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(manifest_id)
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (VALIDATION_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def save_manifest(self, manifest: ReplayManifest) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO replay_manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    manifest.manifest_id,
                    manifest.experiment_split.value,
                    manifest.evidence_cutoff.isoformat(),
                    manifest.rules_frozen_at.isoformat(),
                    manifest.data_version,
                    manifest.code_version,
                    manifest.rule_version,
                    manifest.model_version,
                    manifest.prompt_version,
                    int(manifest.modern_model_rerun),
                    manifest.created_at.isoformat(),
                    VALIDATION_SCHEMA_VERSION,
                ),
            )

    def save_case(self, case: ValidationCase) -> None:
        """Persist a complete validation case atomically; all records are immutable."""
        with self._connect() as connection:
            manifest_exists = connection.execute(
                "SELECT 1 FROM replay_manifests WHERE manifest_id = ?", (case.manifest.manifest_id,)
            ).fetchone()
            if manifest_exists is None:
                raise ValueError("validation manifest must be saved before its cases")
            decision = case.decision
            connection.execute(
                """INSERT INTO locked_research_decisions VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.decision_id, decision.manifest_id, decision.candidate_id, decision.assessment_id,
                    decision.opportunity_version_id, decision.thesis_version_id, decision.evidence_set_id,
                    decision.action_level.value, decision.confidence, decision.evidence_cutoff.isoformat(),
                    decision.locked_at.isoformat(), VALIDATION_SCHEMA_VERSION,
                ),
            )
            process = case.process
            connection.execute(
                """INSERT INTO process_assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    process.process_assessment_id, process.decision_id, process.quality.value,
                    int(process.point_in_time_clean), int(process.evidence_complete),
                    int(process.counter_evidence_adequate),
                    json.dumps([item.value for item in process.errors], separators=(",", ":")),
                    process.rationale, process.assessed_at.isoformat(), VALIDATION_SCHEMA_VERSION,
                ),
            )
            outcome = case.outcome
            connection.execute(
                """INSERT INTO historical_outcomes VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome.outcome_id, outcome.decision_id, outcome.horizon_months, outcome.direction.value,
                    outcome.absolute_return, outcome.benchmark_excess_return, outcome.sector_excess_return,
                    outcome.maximum_drawdown, self._optional_bool(outcome.thesis_validated),
                    self._optional_bool(outcome.attribution_validated), int(outcome.unknowable_event_occurred),
                    outcome.event_description, outcome.revealed_at.isoformat(), VALIDATION_SCHEMA_VERSION,
                ),
            )
            connection.execute(
                """INSERT INTO validation_cases VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    case.case_id, case.manifest.manifest_id, decision.decision_id,
                    process.process_assessment_id, outcome.outcome_id, case.classification.value,
                    VALIDATION_SCHEMA_VERSION,
                ),
            )

    def get_case(self, case_id: str) -> ValidationCase:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT c.classification, m.*, d.*, p.*, o.*
                FROM validation_cases c
                JOIN replay_manifests m ON m.manifest_id = c.manifest_id
                JOIN locked_research_decisions d ON d.decision_id = c.decision_id
                JOIN process_assessments p ON p.process_assessment_id = c.process_assessment_id
                JOIN historical_outcomes o ON o.outcome_id = c.outcome_id
                WHERE c.case_id = ?""",
                (case_id,),
            ).fetchone()
        if row is None:
            raise KeyError(case_id)
        return ValidationCase(
            case_id,
            self._decode_manifest(row),
            self._decode_decision(row),
            self._decode_process(row),
            self._decode_outcome(row),
            ProcessOutcomeClass(row["classification"]),
        )

    def save_metrics(
        self,
        report_id: str,
        manifest_id: str,
        calculated_at: datetime,
        metrics: ResearchQualityMetrics,
    ) -> None:
        if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
            raise ValueError("calculated_at must be timezone-aware")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO research_quality_reports VALUES (?, ?, ?, ?, ?)",
                (
                    report_id, manifest_id, calculated_at.isoformat(),
                    json.dumps(asdict(metrics), separators=(",", ":")), VALIDATION_SCHEMA_VERSION,
                ),
            )

    def get_metrics(self, report_id: str) -> ResearchQualityMetrics:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM research_quality_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
        if row is None:
            raise KeyError(report_id)
        return ResearchQualityMetrics(**json.loads(row["payload_json"]))

    @staticmethod
    def _optional_bool(value: bool | None) -> int | None:
        return None if value is None else int(value)

    @staticmethod
    def _decode_manifest(row: sqlite3.Row) -> ReplayManifest:
        return ReplayManifest(
            row["manifest_id"], ExperimentSplit(row["experiment_split"]),
            datetime.fromisoformat(row["evidence_cutoff"]), datetime.fromisoformat(row["rules_frozen_at"]),
            row["data_version"], row["code_version"], row["rule_version"], row["model_version"],
            row["prompt_version"], bool(row["modern_model_rerun"]), datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _decode_decision(row: sqlite3.Row) -> LockedResearchDecision:
        return LockedResearchDecision(
            row["decision_id"], row["manifest_id"], row["candidate_id"], row["assessment_id"],
            row["opportunity_version_id"], row["thesis_version_id"], row["evidence_set_id"],
            ActionLevel(row["action_level"]), row["confidence"], datetime.fromisoformat(row["evidence_cutoff"]),
            datetime.fromisoformat(row["locked_at"]),
        )

    @staticmethod
    def _decode_process(row: sqlite3.Row) -> ProcessAssessment:
        return ProcessAssessment(
            row["process_assessment_id"], row["decision_id"], ProcessQuality(row["quality"]),
            bool(row["point_in_time_clean"]), bool(row["evidence_complete"]),
            bool(row["counter_evidence_adequate"]),
            tuple(ResearchErrorType(item) for item in json.loads(row["errors_json"])),
            row["rationale"], datetime.fromisoformat(row["assessed_at"]),
        )

    @staticmethod
    def _decode_outcome(row: sqlite3.Row) -> HistoricalOutcome:
        def optional_bool(value: int | None) -> bool | None:
            return None if value is None else bool(value)

        return HistoricalOutcome(
            row["outcome_id"], row["decision_id"], row["horizon_months"],
            OutcomeDirection(row["direction"]), row["absolute_return"], row["benchmark_excess_return"],
            row["sector_excess_return"], row["maximum_drawdown"], optional_bool(row["thesis_validated"]),
            optional_bool(row["attribution_validated"]), bool(row["unknowable_event_occurred"]),
            row["event_description"], datetime.fromisoformat(row["revealed_at"]),
        )
