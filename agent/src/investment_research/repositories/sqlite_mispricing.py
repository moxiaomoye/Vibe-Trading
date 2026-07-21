"""SQLite persistence for asset-neutral Mispricing Opportunities."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..assets.models import Asset, ThesisExposure
from ..contracts import (
    AssetType,
    AttributionCategory,
    AttributionRole,
    OpportunityStatus,
    Permanence,
)
from ..mispricing.models import (
    MarketImpliedView,
    MispricingOpportunity,
    MispricingOpportunityVersion,
    PermanenceAssessment,
    PriceMoveAttribution,
    PriceMoveCause,
)
from .sqlite import SQLiteResearchRepository


MISPRICING_SCHEMA_VERSION = 3


def _dump(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> tuple[str, ...]:
    return tuple(json.loads(value))


def _dump_causes(causes: tuple[PriceMoveCause, ...]) -> str:
    payload = [
        {
            "category": cause.category.value,
            "role": cause.role.value,
            "permanence": cause.permanence.value,
            "description": cause.description,
            "relative_importance": cause.relative_importance,
            "confidence": cause.confidence,
            "supporting_evidence_ids": list(cause.supporting_evidence_ids),
            "counter_evidence_ids": list(cause.counter_evidence_ids),
            "alternative_explanations": list(cause.alternative_explanations),
            "next_validation_event": cause.next_validation_event,
        }
        for cause in causes
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _load_causes(payload: str) -> tuple[PriceMoveCause, ...]:
    return tuple(
        PriceMoveCause(
            category=AttributionCategory(item["category"]),
            role=AttributionRole(item["role"]),
            permanence=Permanence(item["permanence"]),
            description=item["description"],
            relative_importance=item["relative_importance"],
            confidence=item["confidence"],
            supporting_evidence_ids=tuple(item["supporting_evidence_ids"]),
            counter_evidence_ids=tuple(item["counter_evidence_ids"]),
            alternative_explanations=tuple(item["alternative_explanations"]),
            next_validation_event=item["next_validation_event"],
        )
        for item in json.loads(payload)
    )


class SQLiteMispricingRepository:
    """Append-only Mispricing adapter sharing the V2 research database."""

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
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    market TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    schema_version INTEGER NOT NULL,
                    UNIQUE(market, symbol, asset_type)
                );
                CREATE TABLE IF NOT EXISTS thesis_exposures (
                    exposure_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id),
                    thesis_version_id TEXT NOT NULL REFERENCES thesis_versions(thesis_version_id),
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    exposure_strength REAL NOT NULL,
                    exposure_purity REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_exposure_asset_thesis
                    ON thesis_exposures(asset_id, thesis_id, as_of DESC);
                CREATE TABLE IF NOT EXISTS market_implied_views (
                    view_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    as_of TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    implied_expectations_json TEXT NOT NULL,
                    priced_positives_json TEXT NOT NULL,
                    overdiscounted_negatives_json TEXT NOT NULL,
                    unknowns_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS price_move_attributions (
                    attribution_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    causes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS permanence_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    overall TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    temporary_evidence_ids_json TEXT NOT NULL,
                    structural_evidence_ids_json TEXT NOT NULL,
                    unresolved_questions_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    as_of TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mispricing_opportunities (
                    opportunity_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id),
                    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
                    dedupe_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mispricing_opportunity_versions (
                    opportunity_version_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL REFERENCES mispricing_opportunities(opportunity_id),
                    version_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    thesis_version_id TEXT NOT NULL REFERENCES thesis_versions(thesis_version_id),
                    exposure_id TEXT NOT NULL REFERENCES thesis_exposures(exposure_id),
                    market_implied_view_id TEXT NOT NULL REFERENCES market_implied_views(view_id),
                    attribution_id TEXT NOT NULL REFERENCES price_move_attributions(attribution_id),
                    permanence_assessment_id TEXT NOT NULL REFERENCES permanence_assessments(assessment_id),
                    evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                    research_view TEXT NOT NULL,
                    variant_wedge TEXT NOT NULL,
                    why_now TEXT NOT NULL,
                    supporting_evidence_ids_json TEXT NOT NULL,
                    counter_evidence_ids_json TEXT NOT NULL,
                    alternative_explanations_json TEXT NOT NULL,
                    unknowns_json TEXT NOT NULL,
                    convergence_paths_json TEXT NOT NULL,
                    first_rejection_question TEXT NOT NULL,
                    kill_criteria_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    change_summary TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    next_review_at TEXT NOT NULL,
                    supersedes_version_id TEXT REFERENCES mispricing_opportunity_versions(opportunity_version_id),
                    schema_version INTEGER NOT NULL,
                    UNIQUE(opportunity_id, version_number)
                );
                CREATE INDEX IF NOT EXISTS idx_opportunity_versions_pit
                    ON mispricing_opportunity_versions(opportunity_id, effective_from DESC, version_number DESC);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (MISPRICING_SCHEMA_VERSION, datetime.now().astimezone().isoformat()),
            )

    def save_asset(self, asset: Asset) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO assets
                (asset_id, symbol, name, asset_type, market, currency, created_at, active, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset.asset_id,
                    asset.symbol,
                    asset.name,
                    asset.asset_type.value,
                    asset.market,
                    asset.currency,
                    asset.created_at.isoformat(),
                    int(asset.active),
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def get_asset(self, asset_id: str) -> Asset:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            raise KeyError(asset_id)
        return Asset(
            row["asset_id"],
            row["symbol"],
            row["name"],
            AssetType(row["asset_type"]),
            row["market"],
            row["currency"],
            datetime.fromisoformat(row["created_at"]),
            bool(row["active"]),
        )

    def save_exposure(self, exposure: ThesisExposure) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO thesis_exposures
                (exposure_id, asset_id, thesis_id, thesis_version_id, evidence_set_id,
                 exposure_strength, exposure_purity, rationale, as_of, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    exposure.exposure_id,
                    exposure.asset_id,
                    exposure.thesis_id,
                    exposure.thesis_version_id,
                    exposure.evidence_set_id,
                    exposure.exposure_strength,
                    exposure.exposure_purity,
                    exposure.rationale,
                    exposure.as_of.isoformat(),
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def get_exposure(self, exposure_id: str) -> ThesisExposure:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM thesis_exposures WHERE exposure_id = ?",
                (exposure_id,),
            ).fetchone()
        if row is None:
            raise KeyError(exposure_id)
        return ThesisExposure(
            row["exposure_id"],
            row["asset_id"],
            row["thesis_id"],
            row["thesis_version_id"],
            row["evidence_set_id"],
            row["exposure_strength"],
            row["exposure_purity"],
            row["rationale"],
            datetime.fromisoformat(row["as_of"]),
        )

    def save_market_implied_view(self, view: MarketImpliedView) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO market_implied_views
                (view_id, asset_id, evidence_set_id, as_of, narrative,
                 implied_expectations_json, priced_positives_json,
                 overdiscounted_negatives_json, unknowns_json, evidence_ids_json,
                 confidence, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    view.view_id,
                    view.asset_id,
                    view.evidence_set_id,
                    view.as_of.isoformat(),
                    view.narrative,
                    _dump(view.implied_expectations),
                    _dump(view.priced_positives),
                    _dump(view.possible_overdiscounted_negatives),
                    _dump(view.unknowns),
                    _dump(view.evidence_ids),
                    view.confidence,
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def get_market_implied_view(self, view_id: str) -> MarketImpliedView:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM market_implied_views WHERE view_id = ?",
                (view_id,),
            ).fetchone()
        if row is None:
            raise KeyError(view_id)
        return MarketImpliedView(
            row["view_id"],
            row["asset_id"],
            row["evidence_set_id"],
            datetime.fromisoformat(row["as_of"]),
            row["narrative"],
            _load(row["implied_expectations_json"]),
            _load(row["priced_positives_json"]),
            _load(row["overdiscounted_negatives_json"]),
            _load(row["unknowns_json"]),
            _load(row["evidence_ids_json"]),
            row["confidence"],
        )

    def save_attribution(self, attribution: PriceMoveAttribution) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO price_move_attributions
                (attribution_id, asset_id, evidence_set_id, window_start,
                 window_end, causes_json, created_at, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attribution.attribution_id,
                    attribution.asset_id,
                    attribution.evidence_set_id,
                    attribution.window_start.isoformat(),
                    attribution.window_end.isoformat(),
                    _dump_causes(attribution.causes),
                    attribution.created_at.isoformat(),
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def get_attribution(self, attribution_id: str) -> PriceMoveAttribution:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM price_move_attributions WHERE attribution_id = ?",
                (attribution_id,),
            ).fetchone()
        if row is None:
            raise KeyError(attribution_id)
        return PriceMoveAttribution(
            row["attribution_id"],
            row["asset_id"],
            row["evidence_set_id"],
            datetime.fromisoformat(row["window_start"]),
            datetime.fromisoformat(row["window_end"]),
            _load_causes(row["causes_json"]),
            datetime.fromisoformat(row["created_at"]),
        )

    def save_permanence_assessment(self, assessment: PermanenceAssessment) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO permanence_assessments
                (assessment_id, evidence_set_id, overall, rationale,
                 temporary_evidence_ids_json, structural_evidence_ids_json,
                 unresolved_questions_json, confidence, as_of, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    assessment.assessment_id,
                    assessment.evidence_set_id,
                    assessment.overall.value,
                    assessment.rationale,
                    _dump(assessment.temporary_evidence_ids),
                    _dump(assessment.structural_evidence_ids),
                    _dump(assessment.unresolved_questions),
                    assessment.confidence,
                    assessment.as_of.isoformat(),
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def get_permanence_assessment(self, assessment_id: str) -> PermanenceAssessment:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM permanence_assessments WHERE assessment_id = ?",
                (assessment_id,),
            ).fetchone()
        if row is None:
            raise KeyError(assessment_id)
        return PermanenceAssessment(
            row["assessment_id"],
            row["evidence_set_id"],
            Permanence(row["overall"]),
            row["rationale"],
            _load(row["temporary_evidence_ids_json"]),
            _load(row["structural_evidence_ids_json"]),
            _load(row["unresolved_questions_json"]),
            row["confidence"],
            datetime.fromisoformat(row["as_of"]),
        )

    def save_opportunity(self, opportunity: MispricingOpportunity) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO mispricing_opportunities
                (opportunity_id, thesis_id, asset_id, dedupe_key, created_at, schema_version)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    opportunity.opportunity_id,
                    opportunity.thesis_id,
                    opportunity.asset_id,
                    opportunity.dedupe_key,
                    opportunity.created_at.isoformat(),
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def get_opportunity_by_dedupe_key(self, dedupe_key: str) -> MispricingOpportunity:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mispricing_opportunities WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
        if row is None:
            raise KeyError(dedupe_key)
        return MispricingOpportunity(
            row["opportunity_id"],
            row["thesis_id"],
            row["asset_id"],
            row["dedupe_key"],
            datetime.fromisoformat(row["created_at"]),
        )

    def append_opportunity_version(self, version: MispricingOpportunityVersion) -> None:
        with self._connect() as connection:
            latest = connection.execute(
                """SELECT opportunity_version_id, version_number
                FROM mispricing_opportunity_versions WHERE opportunity_id = ?
                ORDER BY version_number DESC LIMIT 1""",
                (version.opportunity_id,),
            ).fetchone()
            expected = 1 if latest is None else latest["version_number"] + 1
            expected_parent = None if latest is None else latest["opportunity_version_id"]
            if version.version_number != expected:
                raise ValueError(f"opportunity version must be sequential; expected {expected}")
            if version.supersedes_version_id != expected_parent:
                raise ValueError("opportunity version must supersede the latest version")
            connection.execute(
                """INSERT INTO mispricing_opportunity_versions
                (opportunity_version_id, opportunity_id, version_number, status,
                 thesis_version_id, exposure_id, market_implied_view_id,
                 attribution_id, permanence_assessment_id, evidence_set_id,
                 research_view, variant_wedge, why_now,
                 supporting_evidence_ids_json, counter_evidence_ids_json,
                 alternative_explanations_json, unknowns_json,
                 convergence_paths_json, first_rejection_question,
                 kill_criteria_json, confidence, change_summary, effective_from,
                 next_review_at, supersedes_version_id, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version.opportunity_version_id,
                    version.opportunity_id,
                    version.version_number,
                    version.status.value,
                    version.thesis_version_id,
                    version.exposure_id,
                    version.market_implied_view_id,
                    version.attribution_id,
                    version.permanence_assessment_id,
                    version.evidence_set_id,
                    version.research_view,
                    version.variant_wedge,
                    version.why_now,
                    _dump(version.supporting_evidence_ids),
                    _dump(version.counter_evidence_ids),
                    _dump(version.alternative_explanations),
                    _dump(version.unknowns),
                    _dump(version.convergence_paths),
                    version.first_rejection_question,
                    _dump(version.kill_criteria),
                    version.confidence,
                    version.change_summary,
                    version.effective_from.isoformat(),
                    version.next_review_at.isoformat(),
                    version.supersedes_version_id,
                    MISPRICING_SCHEMA_VERSION,
                ),
            )

    def current_opportunity_version(self, opportunity_id: str, as_of: datetime) -> MispricingOpportunityVersion:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM mispricing_opportunity_versions
                WHERE opportunity_id = ? AND effective_from <= ?
                ORDER BY effective_from DESC, version_number DESC LIMIT 1""",
                (opportunity_id, as_of.isoformat()),
            ).fetchone()
        if row is None:
            raise KeyError(f"no opportunity version for {opportunity_id} as of {as_of.isoformat()}")
        return self._decode_opportunity_version(row)

    @staticmethod
    def _decode_opportunity_version(row: sqlite3.Row) -> MispricingOpportunityVersion:
        return MispricingOpportunityVersion(
            opportunity_version_id=row["opportunity_version_id"],
            opportunity_id=row["opportunity_id"],
            version_number=row["version_number"],
            status=OpportunityStatus(row["status"]),
            thesis_version_id=row["thesis_version_id"],
            exposure_id=row["exposure_id"],
            market_implied_view_id=row["market_implied_view_id"],
            attribution_id=row["attribution_id"],
            permanence_assessment_id=row["permanence_assessment_id"],
            evidence_set_id=row["evidence_set_id"],
            research_view=row["research_view"],
            variant_wedge=row["variant_wedge"],
            why_now=row["why_now"],
            supporting_evidence_ids=_load(row["supporting_evidence_ids_json"]),
            counter_evidence_ids=_load(row["counter_evidence_ids_json"]),
            alternative_explanations=_load(row["alternative_explanations_json"]),
            unknowns=_load(row["unknowns_json"]),
            convergence_paths=_load(row["convergence_paths_json"]),
            first_rejection_question=row["first_rejection_question"],
            kill_criteria=_load(row["kill_criteria_json"]),
            confidence=row["confidence"],
            change_summary=row["change_summary"],
            effective_from=datetime.fromisoformat(row["effective_from"]),
            next_review_at=datetime.fromisoformat(row["next_review_at"]),
            supersedes_version_id=row["supersedes_version_id"],
        )
