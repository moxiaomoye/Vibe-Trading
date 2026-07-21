from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import EvidenceDirection, MarketRegime
from src.investment_research.evidence.context import ContextEvidenceBundle, EvidenceSubjectType
from src.investment_research.evidence.models import Evidence
from src.investment_research.market.models import MarketState
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_context_evidence import SQLiteContextEvidenceRepository
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _evidence(available_at: datetime = NOW) -> Evidence:
    return Evidence(
        "market-evidence-1", "fixture", "fixture://market/2026-07-21", "Market breadth snapshot",
        "Ten percent of securities advanced.", EvidenceDirection.NEUTRAL,
        available_at - timedelta(minutes=1), available_at, available_at, "market-hash",
    )


def _bundle() -> ContextEvidenceBundle:
    return ContextEvidenceBundle(
        "market-bundle-1", EvidenceSubjectType.MARKET, "cn-equity-market", NOW,
        ("market-evidence-1",), NOW,
    )


def test_context_evidence_bundle_round_trip_and_point_in_time_guard(tmp_path) -> None:
    repository = SQLiteContextEvidenceRepository(tmp_path / "research.sqlite3")
    repository.save_bundle(_bundle(), (_evidence(),))
    assert repository.get_bundle("market-bundle-1") == (_bundle(), (_evidence(),))
    with pytest.raises(ValueError, match="unavailable"):
        _bundle().validate_point_in_time((_evidence(NOW + timedelta(minutes=1)),))
    with pytest.raises(ValueError, match="unknown"):
        _bundle().validate_point_in_time((replace(_evidence(), evidence_id="other"),))


def test_market_state_accepts_generic_context_evidence_bundle(tmp_path) -> None:
    path = tmp_path / "research.sqlite3"
    SQLiteContextEvidenceRepository(path).save_bundle(_bundle(), (_evidence(),))
    intelligence = SQLiteIntelligenceRepository(path)
    state = MarketState(
        "market-1", MarketRegime.PANIC, _bundle().evidence_bundle_id, ("breadth collapsed",), (), 0.9, NOW
    )
    intelligence.save_market_state(state)
    assert intelligence.get_market_state("market-1") == state


def test_legacy_market_state_foreign_key_is_removed_without_losing_rows(tmp_path) -> None:
    path = tmp_path / "research.sqlite3"
    research = SQLiteResearchRepository(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE market_states (
                market_state_id TEXT PRIMARY KEY,
                regime TEXT NOT NULL,
                evidence_set_id TEXT NOT NULL REFERENCES evidence_sets(evidence_set_id),
                drivers_json TEXT NOT NULL,
                data_gaps_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                as_of TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            )"""
        )
    SQLiteIntelligenceRepository(path)
    with sqlite3.connect(path) as connection:
        foreign_tables = {row[2] for row in connection.execute("PRAGMA foreign_key_list(market_states)")}
    assert "evidence_sets" not in foreign_tables
    assert research.list_theses() == []
