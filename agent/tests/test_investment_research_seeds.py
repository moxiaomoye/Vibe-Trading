from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.investment_research.contracts import ThesisScope
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.thesis.models import Thesis
from src.investment_research.thesis.seeds import (
    ThesisBlueprintManifest,
    import_thesis_identities,
    load_blueprint_manifest,
    validate_blueprint_manifest,
)


NOW = datetime(2026, 7, 21, tzinfo=timezone.utc)


def test_ai_infrastructure_manifest_is_balanced_and_valid() -> None:
    manifest = load_blueprint_manifest()

    assert manifest.manifest_id == "ai-infrastructure"
    assert len(manifest.blueprints) == 8
    assert manifest.blueprints[0].thesis_id == "ai-industry"
    assert all(item.key_assumptions for item in manifest.blueprints)
    assert all(item.strongest_counter_questions for item in manifest.blueprints)
    assert all(item.draft_kill_criteria for item in manifest.blueprints)


def test_seed_import_is_idempotent(tmp_path) -> None:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    manifest = load_blueprint_manifest()

    first = import_thesis_identities(repository, manifest, NOW)
    second = import_thesis_identities(repository, manifest, NOW)

    assert len(first) == 8
    assert second == ()
    assert len(repository.list_theses()) == 8
    assert repository.get_thesis("hyperscaler-capex").scope == ThesisScope.VALUE_CHAIN


def test_seed_import_rejects_identity_conflict(tmp_path) -> None:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    repository.save_thesis(Thesis("ai-industry", "Conflicting Name", None, NOW))

    with pytest.raises(ValueError, match="conflicts with blueprint"):
        import_thesis_identities(repository, load_blueprint_manifest(), NOW)


def test_manifest_validation_rejects_cycles() -> None:
    manifest = load_blueprint_manifest()
    root = replace(manifest.blueprints[0], parent_thesis_id=manifest.blueprints[1].thesis_id)
    cyclic = ThesisBlueprintManifest(manifest.manifest_id, manifest.version, (root, *manifest.blueprints[1:]))

    with pytest.raises(ValueError, match="exactly one root|cycle"):
        validate_blueprint_manifest(cyclic)


def test_schema_migrates_v1_thesis_identity(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE theses (
                thesis_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_thesis_id TEXT,
                created_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO theses VALUES (?, ?, ?, ?, ?)",
            ("legacy", "Legacy Thesis", None, NOW.isoformat(), 1),
        )

    repository = SQLiteResearchRepository(path)

    assert repository.get_thesis("legacy").scope == ThesisScope.THEME

