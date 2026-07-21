"""SQLite persistence for Research Candidates, assessments, and alerts."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..candidates.models import ActionAssessment, ResearchCandidate
from ..contracts import (
    ActionLevel,
    AssessmentVerdict,
    MarketRegime,
    OpportunityStatus,
    Permanence,
    ResearchPriority,
    ThesisStatus,
)
from ..intelligence.alert_eligibility import AlertEligibilityDecision, OpportunityAlert
from ..intelligence.daily_research import DailyResearchReport
from ..market.models import MarketState
from .sqlite_mispricing import SQLiteMispricingRepository


INTELLIGENCE_SCHEMA_VERSION = 4


def _dump(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> tuple[str, ...]:
    return tuple(json.loads(value))


class SQLiteIntelligenceRepository:
    def __init__(self, path: Path):
        self.path = path
        SQLiteMispricingRepository(path)
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
                CREATE TABLE IF NOT EXISTS market_states (
                    market_state_id TEXT PRIMARY KEY,
                    regime TEXT NOT NULL,
                    evidence_set_id TEXT NOT NULL,
                    drivers_json TEXT NOT NULL,
                    data_gaps_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    as_of TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_market_states_as_of ON market_states(as_of DESC);
                CREATE TABLE IF NOT EXISTS research_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL REFERENCES mispricing_opportunities(opportunity_id),
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(opportunity_id)
                );
                CREATE TABLE IF NOT EXISTS action_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL REFERENCES research_candidates(candidate_id),
                    version_number INTEGER NOT NULL,
                    opportunity_version_id TEXT NOT NULL REFERENCES mispricing_opportunity_versions(opportunity_version_id),
                    thesis_version_id TEXT NOT NULL REFERENCES thesis_versions(thesis_version_id),
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    market_state_id TEXT NOT NULL REFERENCES market_states(market_state_id),
                    action_level TEXT NOT NULL,
                    research_priority TEXT NOT NULL,
                    thesis_integrity TEXT NOT NULL,
                    mispricing_strength TEXT NOT NULL,
                    fundamental_integrity TEXT NOT NULL,
                    evidence_completeness TEXT NOT NULL,
                    market_context_fit TEXT NOT NULL,
                    asset_expression_quality TEXT NOT NULL,
                    thesis_status_snapshot TEXT NOT NULL,
                    opportunity_status_snapshot TEXT NOT NULL,
                    permanence_snapshot TEXT NOT NULL,
                    market_regime_snapshot TEXT NOT NULL,
                    evidence_complete INTEGER NOT NULL,
                    mispricing_significant INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    strongest_counter_case TEXT NOT NULL,
                    unknowns_json TEXT NOT NULL,
                    first_rejection_question TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    next_review_at TEXT NOT NULL,
                    supersedes_assessment_id TEXT REFERENCES action_assessments(assessment_id),
                    schema_version INTEGER NOT NULL,
                    UNIQUE(candidate_id, version_number)
                );
                CREATE INDEX IF NOT EXISTS idx_assessments_pit
                    ON action_assessments(candidate_id, effective_from DESC, version_number DESC);
                CREATE TABLE IF NOT EXISTS opportunity_alerts (
                    alert_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL REFERENCES research_candidates(candidate_id),
                    assessment_id TEXT NOT NULL UNIQUE REFERENCES action_assessments(assessment_id),
                    opportunity_version_id TEXT NOT NULL REFERENCES mispricing_opportunity_versions(opportunity_version_id),
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    created_at TEXT NOT NULL,
                    disclaimer TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_research_reports (
                    report_id TEXT PRIMARY KEY,
                    trade_date TEXT NOT NULL,
                    information_cutoff TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    market_regime TEXT,
                    candidate_count INTEGER NOT NULL,
                    eligible_alert_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(trade_date, mode)
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (INTELLIGENCE_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )
        self._remove_legacy_market_evidence_foreign_key()

    def _remove_legacy_market_evidence_foreign_key(self) -> None:
        """Migrate early V2 databases where Market State incorrectly depended on Thesis EvidenceSet."""
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            foreign_keys = connection.execute("PRAGMA foreign_key_list(market_states)").fetchall()
            if not any(row[2] == "evidence_sets" for row in foreign_keys):
                return
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA legacy_alter_table = ON")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                ALTER TABLE market_states RENAME TO market_states_legacy_v2;
                CREATE TABLE market_states (
                    market_state_id TEXT PRIMARY KEY,
                    regime TEXT NOT NULL,
                    evidence_set_id TEXT NOT NULL,
                    drivers_json TEXT NOT NULL,
                    data_gaps_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    as_of TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                INSERT INTO market_states SELECT * FROM market_states_legacy_v2;
                DROP TABLE market_states_legacy_v2;
                CREATE INDEX IF NOT EXISTS idx_market_states_as_of ON market_states(as_of DESC);
                COMMIT;
                """
            )
        finally:
            connection.execute("PRAGMA legacy_alter_table = OFF")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.close()

    def save_market_state(self, market_state: MarketState) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO market_states
                (market_state_id, regime, evidence_set_id, drivers_json,
                 data_gaps_json, confidence, as_of, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    market_state.market_state_id,
                    market_state.regime.value,
                    market_state.evidence_set_id,
                    _dump(market_state.drivers),
                    _dump(market_state.data_gaps),
                    market_state.confidence,
                    market_state.as_of.isoformat(),
                    INTELLIGENCE_SCHEMA_VERSION,
                ),
            )

    def get_market_state(self, market_state_id: str) -> MarketState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM market_states WHERE market_state_id = ?",
                (market_state_id,),
            ).fetchone()
        if row is None:
            raise KeyError(market_state_id)
        return MarketState(
            row["market_state_id"],
            MarketRegime(row["regime"]),
            row["evidence_set_id"],
            _load(row["drivers_json"]),
            _load(row["data_gaps_json"]),
            row["confidence"],
            datetime.fromisoformat(row["as_of"]),
        )

    def save_candidate(self, candidate: ResearchCandidate) -> None:
        with self._connect() as connection:
            opportunity = connection.execute(
                "SELECT asset_id FROM mispricing_opportunities WHERE opportunity_id = ?",
                (candidate.opportunity_id,),
            ).fetchone()
            if opportunity is None or opportunity["asset_id"] != candidate.asset_id:
                raise ValueError("candidate asset must match its opportunity")
            connection.execute(
                """INSERT INTO research_candidates
                (candidate_id, opportunity_id, asset_id, created_at, schema_version)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    candidate.candidate_id,
                    candidate.opportunity_id,
                    candidate.asset_id,
                    candidate.created_at.isoformat(),
                    INTELLIGENCE_SCHEMA_VERSION,
                ),
            )

    def get_candidate(self, candidate_id: str) -> ResearchCandidate:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return ResearchCandidate(
            row["candidate_id"],
            row["opportunity_id"],
            row["asset_id"],
            datetime.fromisoformat(row["created_at"]),
        )

    def append_assessment(self, assessment: ActionAssessment) -> None:
        with self._connect() as connection:
            relationship = connection.execute(
                """SELECT candidate.opportunity_id AS candidate_opportunity,
                          version.opportunity_id AS version_opportunity,
                          version.evidence_set_id AS version_evidence_set
                FROM research_candidates candidate
                JOIN mispricing_opportunity_versions version
                  ON version.opportunity_version_id = ?
                WHERE candidate.candidate_id = ?""",
                (assessment.opportunity_version_id, assessment.candidate_id),
            ).fetchone()
            if relationship is None or relationship["candidate_opportunity"] != relationship["version_opportunity"]:
                raise ValueError("assessment candidate and opportunity version are inconsistent")
            if relationship["version_evidence_set"] != assessment.evidence_set_id:
                raise ValueError("assessment must use its opportunity version evidence set")
            latest = connection.execute(
                """SELECT assessment_id, version_number FROM action_assessments
                WHERE candidate_id = ? ORDER BY version_number DESC LIMIT 1""",
                (assessment.candidate_id,),
            ).fetchone()
            expected = 1 if latest is None else latest["version_number"] + 1
            expected_parent = None if latest is None else latest["assessment_id"]
            if assessment.version_number != expected:
                raise ValueError(f"assessment version must be sequential; expected {expected}")
            if assessment.supersedes_assessment_id != expected_parent:
                raise ValueError("assessment must supersede the latest assessment")
            connection.execute(
                """INSERT INTO action_assessments
                (assessment_id, candidate_id, version_number, opportunity_version_id,
                 thesis_version_id, evidence_set_id, market_state_id, action_level,
                 research_priority, thesis_integrity, mispricing_strength,
                 fundamental_integrity, evidence_completeness, market_context_fit,
                 asset_expression_quality, thesis_status_snapshot,
                 opportunity_status_snapshot, permanence_snapshot,
                 market_regime_snapshot, evidence_complete, mispricing_significant,
                 confidence, rationale, strongest_counter_case, unknowns_json,
                 first_rejection_question, effective_from, next_review_at,
                 supersedes_assessment_id, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    assessment.assessment_id,
                    assessment.candidate_id,
                    assessment.version_number,
                    assessment.opportunity_version_id,
                    assessment.thesis_version_id,
                    assessment.evidence_set_id,
                    assessment.market_state_id,
                    assessment.action_level.value,
                    assessment.research_priority.value,
                    assessment.thesis_integrity.value,
                    assessment.mispricing_strength.value,
                    assessment.fundamental_integrity.value,
                    assessment.evidence_completeness.value,
                    assessment.market_context_fit.value,
                    assessment.asset_expression_quality.value,
                    assessment.thesis_status_snapshot.value,
                    assessment.opportunity_status_snapshot.value,
                    assessment.permanence_snapshot.value,
                    assessment.market_regime_snapshot.value,
                    int(assessment.evidence_complete),
                    int(assessment.mispricing_significant),
                    assessment.confidence,
                    assessment.rationale,
                    assessment.strongest_counter_case,
                    _dump(assessment.unknowns),
                    assessment.first_rejection_question,
                    assessment.effective_from.isoformat(),
                    assessment.next_review_at.isoformat(),
                    assessment.supersedes_assessment_id,
                    INTELLIGENCE_SCHEMA_VERSION,
                ),
            )

    def current_assessment(self, candidate_id: str, as_of: datetime) -> ActionAssessment:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM action_assessments
                WHERE candidate_id = ? AND effective_from <= ?
                ORDER BY effective_from DESC, version_number DESC LIMIT 1""",
                (candidate_id, as_of.isoformat()),
            ).fetchone()
        if row is None:
            raise KeyError(f"no assessment for {candidate_id} as of {as_of.isoformat()}")
        return self._decode_assessment(row)

    def save_alert(self, alert: OpportunityAlert, decision: AlertEligibilityDecision) -> None:
        if not decision.eligible or decision.assessment_id != alert.assessment_id:
            raise ValueError("only an eligible decision for the same assessment can create an alert")
        with self._connect() as connection:
            assessment = connection.execute(
                """SELECT candidate_id, opportunity_version_id, evidence_set_id
                FROM action_assessments WHERE assessment_id = ?""",
                (alert.assessment_id,),
            ).fetchone()
            expected = (alert.candidate_id, alert.opportunity_version_id, alert.evidence_set_id)
            actual = (
                assessment["candidate_id"],
                assessment["opportunity_version_id"],
                assessment["evidence_set_id"],
            ) if assessment else None
            if actual != expected:
                raise ValueError("alert references do not match the saved assessment")
            connection.execute(
                """INSERT INTO opportunity_alerts
                (alert_id, candidate_id, assessment_id, opportunity_version_id,
                 evidence_set_id, created_at, disclaimer, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert.alert_id,
                    alert.candidate_id,
                    alert.assessment_id,
                    alert.opportunity_version_id,
                    alert.evidence_set_id,
                    alert.created_at.isoformat(),
                    alert.disclaimer,
                    INTELLIGENCE_SCHEMA_VERSION,
                ),
            )

    def get_alert(self, alert_id: str) -> OpportunityAlert:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM opportunity_alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        if row is None:
            raise KeyError(alert_id)
        return OpportunityAlert(
            row["alert_id"],
            row["candidate_id"],
            row["assessment_id"],
            row["opportunity_version_id"],
            row["evidence_set_id"],
            datetime.fromisoformat(row["created_at"]),
            row["disclaimer"],
        )

    def save_daily_research_report(self, report: DailyResearchReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO daily_research_reports
                (report_id, trade_date, information_cutoff, generated_at, mode,
                 market_regime, candidate_count, eligible_alert_count,
                 payload_json, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.report_id,
                    report.trade_date.isoformat(),
                    report.information_cutoff.isoformat(),
                    report.generated_at.isoformat(),
                    report.mode,
                    report.market_state.regime.value if report.market_state else None,
                    len(report.candidates),
                    report.eligible_alert_count,
                    json.dumps(report.to_dict(), ensure_ascii=False, separators=(",", ":")),
                    INTELLIGENCE_SCHEMA_VERSION,
                ),
            )

    def get_daily_research_report(self, trade_date: date, mode: str = "shadow") -> DailyResearchReport:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_research_reports WHERE trade_date = ? AND mode = ?",
                (trade_date.isoformat(), mode),
            ).fetchone()
        if row is None:
            raise KeyError(f"no {mode} daily research report for {trade_date.isoformat()}")
        return DailyResearchReport.from_dict(json.loads(row["payload_json"]))

    @staticmethod
    def _decode_assessment(row: sqlite3.Row) -> ActionAssessment:
        return ActionAssessment(
            assessment_id=row["assessment_id"],
            candidate_id=row["candidate_id"],
            version_number=row["version_number"],
            opportunity_version_id=row["opportunity_version_id"],
            thesis_version_id=row["thesis_version_id"],
            evidence_set_id=row["evidence_set_id"],
            market_state_id=row["market_state_id"],
            action_level=ActionLevel(row["action_level"]),
            research_priority=ResearchPriority(row["research_priority"]),
            thesis_integrity=AssessmentVerdict(row["thesis_integrity"]),
            mispricing_strength=AssessmentVerdict(row["mispricing_strength"]),
            fundamental_integrity=AssessmentVerdict(row["fundamental_integrity"]),
            evidence_completeness=AssessmentVerdict(row["evidence_completeness"]),
            market_context_fit=AssessmentVerdict(row["market_context_fit"]),
            asset_expression_quality=AssessmentVerdict(row["asset_expression_quality"]),
            thesis_status_snapshot=ThesisStatus(row["thesis_status_snapshot"]),
            opportunity_status_snapshot=OpportunityStatus(row["opportunity_status_snapshot"]),
            permanence_snapshot=Permanence(row["permanence_snapshot"]),
            market_regime_snapshot=MarketRegime(row["market_regime_snapshot"]),
            evidence_complete=bool(row["evidence_complete"]),
            mispricing_significant=bool(row["mispricing_significant"]),
            confidence=row["confidence"],
            rationale=row["rationale"],
            strongest_counter_case=row["strongest_counter_case"],
            unknowns=_load(row["unknowns_json"]),
            first_rejection_question=row["first_rejection_question"],
            effective_from=datetime.fromisoformat(row["effective_from"]),
            next_review_at=datetime.fromisoformat(row["next_review_at"]),
            supersedes_assessment_id=row["supersedes_assessment_id"],
        )
