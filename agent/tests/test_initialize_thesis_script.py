from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.initialize_thesis import initialize_manifest
from src.investment_research.application.initialization_manifest import ThesisInitializationManifest
from src.investment_research.contracts import EvidenceDirection, ThesisScope
from src.investment_research.evidence.associations import EvidenceSubjectType
from src.investment_research.evidence.associations import EvidenceAssociation
from src.investment_research.evidence.models import Evidence
from src.investment_research.evidence.readiness import EvidenceSetReview, EvidenceSetReviewDecision
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_evidence_associations import SQLiteEvidenceAssociationRepository
from src.investment_research.repositories.sqlite_evidence_set_reviews import SQLiteEvidenceSetReviewRepository
from src.investment_research.thesis.models import Thesis


def _manifest_payload() -> dict:
    payload = {
        "manifest_version": 3,
        "thesis_id": "ai-infrastructure",
        "information_cutoff": "2026-07-21T09:30:00+00:00",
        "initialized_at": "2026-07-21T10:00:00+00:00",
        "evidence": [
            {
                "evidence_id": "support-1", "provider": "fixture",
                "source_locator": "fixture://support", "title": "Support", "summary": "Supports Thesis.",
                "published_at": "2026-07-20T08:00:00+00:00",
                "available_at": "2026-07-20T09:00:00+00:00",
                "observed_at": "2026-07-21T08:00:00+00:00",
            },
            {
                "evidence_id": "counter-1", "provider": "fixture",
                "source_locator": "fixture://counter", "title": "Counter", "summary": "Opposes Thesis.",
                "published_at": "2026-07-20T08:00:00+00:00",
                "available_at": "2026-07-20T09:00:00+00:00",
                "observed_at": "2026-07-21T08:00:00+00:00",
            },
        ],
        "associations": [
            {
                "evidence_id": "support-1", "direction": "supporting",
                "assessed_at": "2026-07-21T09:30:00+00:00", "assessor": "analyst-1",
                "rationale": "Supports this specific Thesis.",
            },
            {
                "evidence_id": "counter-1", "direction": "counter",
                "assessed_at": "2026-07-21T09:30:00+00:00", "assessor": "analyst-1",
                "rationale": "Opposes this specific Thesis.",
            },
        ],
        "proposal": {
            "status": "active", "core_claim": "Durable AI infrastructure demand.", "confidence": 0.7,
            "supporting_evidence_ids": ["support-1"], "counter_evidence_ids": ["counter-1"],
            "catalysts": ["CapEx acceleration"], "kill_criteria": ["Multi-quarter CapEx contraction"],
            "change_summary": "Initial evidence-backed version.",
            "next_review_at": "2026-08-20T10:00:00+00:00", "initializer": "research-committee",
            "approval_reference": "approval://fixture/1",
            "evidence_set_review_id": "review-1",
        },
    }
    for item in payload["associations"]:
        association = EvidenceAssociation.create(
            item["evidence_id"], EvidenceSubjectType.THESIS, payload["thesis_id"],
            EvidenceDirection(item["direction"]), datetime.fromisoformat(item["assessed_at"]),
            item["assessor"], item["rationale"],
        )
        item["association_id"] = association.association_id
    return payload


def test_initialize_script_service_persists_manifest_v3_idempotently(tmp_path: Path) -> None:
    database_path = tmp_path / "research.sqlite3"
    repository = SQLiteResearchRepository(database_path)
    repository.save_thesis(
        Thesis(
            "ai-infrastructure", "AI Infrastructure", None,
            datetime(2026, 7, 21, tzinfo=timezone.utc), ThesisScope.THEME,
        )
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
    manifest = ThesisInitializationManifest.load(manifest_path)
    association_repository = SQLiteEvidenceAssociationRepository(database_path)
    for evidence in manifest.evidence:
        repository.save_evidence(evidence)
    for association in manifest.associations:
        association_repository.append(association)
    review = EvidenceSetReview(
        "review-1", manifest.thesis_id,
        tuple(item.association_id for item in manifest.associations),
        manifest.evidence_set.as_of, EvidenceSetReviewDecision.APPROVE,
        "chief-analyst", "The Thesis survives the strongest known counter evidence.",
        datetime(2026, 7, 21, 9, 45, tzinfo=timezone.utc),
        manifest.associations[1].association_id, (), None, "approval://fixture/1",
    )
    SQLiteEvidenceSetReviewRepository(database_path).record(review)

    first = initialize_manifest(manifest, database_path)
    second = initialize_manifest(manifest, database_path)

    assert second == first
    assert repository.get_evidence("support-1").direction == EvidenceDirection.NEUTRAL
    association = SQLiteEvidenceAssociationRepository(database_path).current(
        "support-1", EvidenceSubjectType.THESIS, "ai-infrastructure",
        datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc),
    )
    assert association.direction == EvidenceDirection.SUPPORTING
    assert repository.get_initialization_audit(first.thesis_version_id).approval_reference == "approval://fixture/1"
    assert repository.get_initialization_audit(first.thesis_version_id).evidence_set_review_id == "review-1"


def test_initialize_script_rejects_unrecorded_evidence_set_review(tmp_path: Path) -> None:
    database_path = tmp_path / "research.sqlite3"
    repository = SQLiteResearchRepository(database_path)
    repository.save_thesis(
        Thesis(
            "ai-infrastructure", "AI Infrastructure", None,
            datetime(2026, 7, 21, tzinfo=timezone.utc), ThesisScope.THEME,
        )
    )
    manifest = ThesisInitializationManifest.from_dict(_manifest_payload())

    with pytest.raises(ValueError, match="not recorded"):
        initialize_manifest(manifest, database_path)

    assert repository.list_thesis_versions("ai-infrastructure") == []


def test_initialize_script_rejects_approval_made_stale_by_new_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "research.sqlite3"
    repository = SQLiteResearchRepository(database_path)
    repository.save_thesis(
        Thesis(
            "ai-infrastructure", "AI Infrastructure", None,
            datetime(2026, 7, 21, tzinfo=timezone.utc), ThesisScope.THEME,
        )
    )
    manifest = ThesisInitializationManifest.from_dict(_manifest_payload())
    association_repository = SQLiteEvidenceAssociationRepository(database_path)
    for evidence in manifest.evidence:
        repository.save_evidence(evidence)
    for association in manifest.associations:
        association_repository.append(association)
    review = EvidenceSetReview(
        "review-1", manifest.thesis_id,
        tuple(item.association_id for item in manifest.associations),
        manifest.evidence_set.as_of, EvidenceSetReviewDecision.APPROVE,
        "chief-analyst", "The Thesis survives the strongest known counter evidence.",
        datetime(2026, 7, 21, 9, 45, tzinfo=timezone.utc),
        manifest.associations[1].association_id, (), None, "approval://fixture/1",
    )
    SQLiteEvidenceSetReviewRepository(database_path).record(review)
    repository.save_evidence(
        Evidence(
            "late-evidence", "fixture", "fixture://late", "Late evidence",
            "A material fact appeared after approval.", EvidenceDirection.NEUTRAL,
            datetime(2026, 7, 21, 9, 35, tzinfo=timezone.utc),
            datetime(2026, 7, 21, 9, 40, tzinfo=timezone.utc),
            datetime(2026, 7, 21, 9, 45, tzinfo=timezone.utc), "hash-late",
        )
    )
    association_repository.append(
        EvidenceAssociation.create(
            "late-evidence", EvidenceSubjectType.THESIS, manifest.thesis_id,
            EvidenceDirection.NEUTRAL, manifest.initialized_at - timedelta(minutes=10),
            "analyst-2", "New context requires the evidence set to be reviewed again.",
        )
    )

    with pytest.raises(ValueError, match="stale"):
        initialize_manifest(manifest, database_path)

    assert repository.list_thesis_versions("ai-infrastructure") == []
