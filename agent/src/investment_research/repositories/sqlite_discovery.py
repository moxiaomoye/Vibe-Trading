"""Append-only persistence for point-in-time discovery snapshots and leads."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..discovery.models import DiscoveryDisposition, FundamentalIntegrity, ResearchLead, ResearchSnapshot
from .sqlite import SQLiteResearchRepository


DISCOVERY_SCHEMA_VERSION = 7


class SQLiteDiscoveryRepository:
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
                CREATE TABLE IF NOT EXISTS discovery_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    thesis_version_id TEXT NOT NULL,
                    evidence_set_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    drawdown_from_reference REAL,
                    sector_excess_return REAL,
                    valuation_percentile REAL,
                    fundamental_integrity TEXT NOT NULL,
                    fundamental_evidence_json TEXT NOT NULL,
                    attribution_evidence_json TEXT NOT NULL,
                    counter_evidence_json TEXT NOT NULL,
                    severe_risk_flags_json TEXT NOT NULL,
                    data_gaps_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_discovery_snapshot_pit
                    ON discovery_snapshots(asset_id, thesis_version_id, as_of DESC);
                CREATE TABLE IF NOT EXISTS research_leads (
                    lead_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL UNIQUE REFERENCES discovery_snapshots(snapshot_id),
                    asset_id TEXT NOT NULL,
                    thesis_version_id TEXT NOT NULL,
                    evidence_set_id TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    missing_evidence_json TEXT NOT NULL,
                    first_rejection_question TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_leads_pit
                    ON research_leads(disposition, as_of DESC);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (DISCOVERY_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    @staticmethod
    def _dump(values: tuple[str, ...]) -> str:
        return json.dumps(values, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load(value: str) -> tuple[str, ...]:
        return tuple(json.loads(value))

    def save_result(self, snapshot: ResearchSnapshot, lead: ResearchLead) -> None:
        if (
            lead.asset_id != snapshot.asset_id
            or lead.thesis_version_id != snapshot.thesis_version_id
            or lead.evidence_set_id != snapshot.evidence_set_id
            or lead.as_of != snapshot.as_of
        ):
            raise ValueError("discovery snapshot and research lead are inconsistent")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO discovery_snapshots VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.snapshot_id, snapshot.asset_id, snapshot.thesis_version_id,
                    snapshot.evidence_set_id, snapshot.as_of.isoformat(), snapshot.drawdown_from_reference,
                    snapshot.sector_excess_return, snapshot.valuation_percentile,
                    snapshot.fundamental_integrity.value, self._dump(snapshot.fundamental_evidence_ids),
                    self._dump(snapshot.attribution_evidence_ids), self._dump(snapshot.counter_evidence_ids),
                    self._dump(snapshot.severe_risk_flags), self._dump(snapshot.data_gaps), DISCOVERY_SCHEMA_VERSION,
                ),
            )
            connection.execute(
                """INSERT INTO research_leads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lead.lead_id, snapshot.snapshot_id, lead.asset_id, lead.thesis_version_id,
                    lead.evidence_set_id, lead.disposition.value, self._dump(lead.reasons),
                    self._dump(lead.missing_evidence), lead.first_rejection_question,
                    lead.as_of.isoformat(), DISCOVERY_SCHEMA_VERSION,
                ),
            )

    def get_result(self, lead_id: str) -> tuple[ResearchSnapshot, ResearchLead]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT s.*, l.lead_id, l.disposition, l.reasons_json,
                l.missing_evidence_json, l.first_rejection_question
                FROM research_leads l JOIN discovery_snapshots s ON s.snapshot_id = l.snapshot_id
                WHERE l.lead_id = ?""",
                (lead_id,),
            ).fetchone()
        if row is None:
            raise KeyError(lead_id)
        as_of = datetime.fromisoformat(row["as_of"])
        snapshot = ResearchSnapshot(
            row["snapshot_id"], row["asset_id"], row["thesis_version_id"], row["evidence_set_id"], as_of,
            row["drawdown_from_reference"], row["sector_excess_return"], row["valuation_percentile"],
            FundamentalIntegrity(row["fundamental_integrity"]), self._load(row["fundamental_evidence_json"]),
            self._load(row["attribution_evidence_json"]), self._load(row["counter_evidence_json"]),
            self._load(row["severe_risk_flags_json"]), self._load(row["data_gaps_json"]),
        )
        lead = ResearchLead(
            row["lead_id"], row["asset_id"], row["thesis_version_id"], row["evidence_set_id"],
            DiscoveryDisposition(row["disposition"]), self._load(row["reasons_json"]),
            self._load(row["missing_evidence_json"]), row["first_rejection_question"], as_of,
        )
        return snapshot, lead

    def list_leads(self, as_of: datetime, disposition: DiscoveryDisposition | None = None) -> tuple[ResearchLead, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        query = "SELECT * FROM research_leads WHERE as_of <= ?"
        params: list[str] = [as_of.isoformat()]
        if disposition is not None:
            query += " AND disposition = ?"
            params.append(disposition.value)
        query += " ORDER BY as_of DESC, lead_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(
            ResearchLead(
                row["lead_id"], row["asset_id"], row["thesis_version_id"], row["evidence_set_id"],
                DiscoveryDisposition(row["disposition"]), self._load(row["reasons_json"]),
                self._load(row["missing_evidence_json"]), row["first_rejection_question"],
                datetime.fromisoformat(row["as_of"]),
            )
            for row in rows
        )
