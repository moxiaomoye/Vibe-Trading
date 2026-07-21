from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import investment_research_routes as routes
from src.config.accessor import reset_env_config
from src.investment_research.intelligence.daily_thesis import DailyThesisUpdateService
from src.investment_research.intelligence.daily_research import DailyResearchReportBuilder
from src.investment_research.contracts import EvidenceDirection
from src.investment_research.application.initialization import (
    ThesisInitializationProposal,
    ThesisInitializationService,
)
from src.investment_research.contracts import ThesisStatus
from src.investment_research.evidence.associations import EvidenceAssociation, EvidenceSubjectType
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.evidence.readiness import EvidenceSetReview, EvidenceSetReviewDecision
from src.investment_research.evidence.inbox import (
    EvidenceInboxDecision,
    EvidenceInboxItem,
    EvidenceInboxReview,
    EvidenceInboxSubjectType,
)
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.thesis.seeds import import_thesis_identities, load_blueprint_manifest


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _client(tmp_path, monkeypatch) -> tuple[TestClient, SQLiteResearchRepository]:
    monkeypatch.delenv("VIBE_INVESTMENT_RESEARCH_ENABLED", raising=False)
    monkeypatch.delenv("VIBE_INVESTMENT_RESEARCH_SHADOW_MODE", raising=False)
    database_path = tmp_path / "research.sqlite3"
    monkeypatch.setenv("VIBE_INVESTMENT_RESEARCH_DB_PATH", str(database_path))
    reset_env_config()
    routes.reset_investment_research_repository()
    repository = SQLiteResearchRepository(database_path)
    import_thesis_identities(repository, load_blueprint_manifest(), NOW)
    monkeypatch.setattr(routes, "_repository", repository)
    app = FastAPI()

    async def allow() -> None:
        return None

    routes.register_investment_research_routes(app, allow)
    return TestClient(app), repository


def test_status_preserves_disabled_shadow_defaults(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    response = client.get("/investment-research/status")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["shadow_mode"] is True
    assert response.json()["thesis_count"] == 8
    assert response.json()["schema_components"]["research_core"] == 3
    assert response.json()["schema_components"]["evidence_association"] == 10
    assert response.json()["schema_components"]["evidence_set_review"] == 11
    assert response.json()["evidence_inbox"] == {"pending": 0, "accepted": 0, "rejected": 0}
    assert response.json()["output_contract"] == "Research Candidate, not a trade instruction"


def test_thesis_routes_expose_research_state_without_action_language(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    listing = client.get("/investment-research/theses", params={"as_of": NOW.isoformat()})
    detail = client.get("/investment-research/theses/ai-infrastructure", params={"as_of": NOW.isoformat()})
    versions = client.get("/investment-research/theses/ai-infrastructure/versions")

    assert listing.status_code == 200
    assert len(listing.json()) == 8
    assert all(item["research_state"] == "uninitialized" for item in listing.json())
    assert detail.json()["current_version"] is None
    assert versions.json() == []
    assert client.get("/investment-research/theses/ai-infrastructure/initialization").json() == {
        "thesis_id": "ai-infrastructure",
        "initialized": False,
        "research_state": "uninitialized",
    }


def test_read_routes_validate_missing_records_and_timezone(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    assert client.get("/investment-research/theses/missing").status_code == 404
    assert client.get("/investment-research/theses/missing/versions").status_code == 404
    assert client.get("/investment-research/theses/missing/initialization").status_code == 404
    naive = client.get("/investment-research/theses", params={"as_of": "2026-07-21T10:00:00"})
    assert naive.status_code == 422


def test_daily_report_route_round_trip(tmp_path, monkeypatch) -> None:
    client, repository = _client(tmp_path, monkeypatch)
    report = DailyThesisUpdateService(repository).generate("daily", NOW, NOW + timedelta(minutes=1))
    repository.save_daily_thesis_report(report)

    response = client.get(f"/investment-research/daily/{NOW.date().isoformat()}")

    assert response.status_code == 200
    assert response.json()["report_id"] == "daily"
    assert client.get("/investment-research/daily/2026-07-20").status_code == 404


def test_full_daily_research_and_empty_discovery_routes(tmp_path, monkeypatch) -> None:
    client, repository = _client(tmp_path, monkeypatch)
    thesis_report = DailyThesisUpdateService(repository).generate("thesis-daily", NOW, NOW + timedelta(minutes=1))
    report = DailyResearchReportBuilder().build(
        "research-daily", NOW, NOW + timedelta(minutes=2), thesis_report, None
    )
    routes.get_intelligence_repository().save_daily_research_report(report)

    response = client.get(f"/investment-research/daily-research/{NOW.date().isoformat()}")
    assert response.status_code == 200
    assert response.json()["report_id"] == "research-daily"
    assert response.json()["conclusion"].startswith("No new high-quality")
    assert client.get("/investment-research/discovery-leads", params={"as_of": NOW.isoformat()}).json() == []
    assert client.get("/investment-research/discovery-leads?disposition=invalid").status_code == 422


def test_evidence_inbox_route_is_read_only_and_exposes_pending_research_inputs(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    routes.get_evidence_inbox_repository().ingest(
        EvidenceInboxItem(
            "inbox-1", "fixture", "fixture://capex", "CapEx evidence", "CapEx remains durable.",
            NOW - timedelta(hours=3), NOW - timedelta(hours=2), NOW - timedelta(hours=1),
            "hash-1", (), NOW, EvidenceInboxSubjectType.THESIS, "ai-infrastructure",
            EvidenceDirection.SUPPORTING,
        )
    )

    response = client.get("/investment-research/evidence-inbox?status=pending")
    assert response.status_code == 200
    assert response.json()[0]["status"] == "pending"
    assert response.json()[0]["review"] is None
    assert client.get("/investment-research/evidence-inbox?status=unknown").status_code == 422


def test_contextual_evidence_association_route_exposes_review_audit(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    inbox = routes.get_evidence_inbox_repository()
    inbox.ingest(
        EvidenceInboxItem(
            "inbox-1", "fixture", "fixture://capex", "CapEx evidence", "CapEx remains durable.",
            NOW - timedelta(hours=3), NOW - timedelta(hours=2), NOW - timedelta(hours=1),
            "hash-1", (), NOW, EvidenceInboxSubjectType.THESIS, "ai-infrastructure",
            EvidenceDirection.SUPPORTING,
        )
    )
    inbox.accept(
        EvidenceInboxReview(
            "review-1", "inbox-1", EvidenceInboxDecision.ACCEPT, "Supports this Thesis.",
            "analyst-1", NOW + timedelta(minutes=1), EvidenceInboxSubjectType.THESIS,
            "ai-infrastructure", EvidenceDirection.SUPPORTING,
        )
    )

    response = client.get(
        "/investment-research/evidence-associations",
        params={"subject_type": "thesis", "subject_id": "ai-infrastructure", "as_of": (NOW + timedelta(minutes=2)).isoformat()},
    )
    assert response.status_code == 200
    assert response.json()[0]["direction"] == "supporting"
    assert response.json()[0]["assessor"] == "analyst-1"
    assert client.get(
        "/investment-research/evidence-associations",
        params={"subject_type": "unknown", "subject_id": "ai-infrastructure"},
    ).status_code == 422


def test_evidence_readiness_routes_expose_rejection_question_not_a_score(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)

    listing = client.get(
        "/investment-research/evidence-readiness", params={"as_of": NOW.isoformat()}
    )
    detail = client.get(
        "/investment-research/theses/ai-infrastructure/evidence-readiness",
        params={"as_of": NOW.isoformat()},
    )

    assert listing.status_code == 200
    assert len(listing.json()) == 8
    assert detail.status_code == 200
    assert detail.json()["verdict"] == "not_ready"
    assert detail.json()["first_rejection_question"]
    assert "score" not in detail.json()
    assert client.get("/investment-research/theses/missing/evidence-readiness").status_code == 404
    assert client.get("/investment-research/theses/missing/evidence-set-reviews").status_code == 404


def test_initialization_route_exposes_bound_evidence_set_review(tmp_path, monkeypatch) -> None:
    client, repository = _client(tmp_path, monkeypatch)
    thesis = repository.get_thesis("ai-infrastructure")
    evidence = (
        Evidence(
            "support-route", "fixture", "fixture://support-route", "Support", "Support fact.",
            EvidenceDirection.NEUTRAL, NOW - timedelta(hours=2), NOW - timedelta(hours=1), NOW,
            "hash-support-route",
        ),
        Evidence(
            "counter-route", "fixture", "fixture://counter-route", "Counter", "Counter fact.",
            EvidenceDirection.NEUTRAL, NOW - timedelta(hours=2), NOW - timedelta(hours=1), NOW,
            "hash-counter-route",
        ),
    )
    for item in evidence:
        repository.save_evidence(item)
    evidence_set = EvidenceSet(
        "route-set", thesis.thesis_id, NOW,
        tuple(item.evidence_id for item in evidence), NOW,
    )
    repository.save_evidence_set(evidence_set)
    associations = (
        EvidenceAssociation.create(
            "support-route", EvidenceSubjectType.THESIS, thesis.thesis_id,
            EvidenceDirection.SUPPORTING, NOW, "analyst", "Supports this Thesis.",
        ),
        EvidenceAssociation.create(
            "counter-route", EvidenceSubjectType.THESIS, thesis.thesis_id,
            EvidenceDirection.COUNTER, NOW, "analyst", "Counters this Thesis.",
        ),
    )
    for association in associations:
        routes.get_evidence_association_repository().append(association)
    review = EvidenceSetReview(
        "route-review", thesis.thesis_id,
        tuple(item.association_id for item in associations), NOW,
        EvidenceSetReviewDecision.APPROVE, "chief-analyst", "Reviewed both sides.", NOW,
        associations[1].association_id, (), None, "route-approval",
    )
    routes.get_evidence_set_review_repository().record(review)
    proposal = ThesisInitializationProposal(
        ThesisStatus.ACTIVE, "A falsifiable route-test claim.", 0.7,
        ("support-route",), ("counter-route",), ("Catalyst",), ("Kill criterion",),
        "Initial reviewed version.", NOW + timedelta(days=30), "initializer",
        "route-approval", "route-review",
    )
    version = ThesisInitializationService(repository).initialize(
        thesis, evidence_set, evidence, proposal, NOW + timedelta(minutes=1), review, associations,
    )

    response = client.get(f"/investment-research/theses/{thesis.thesis_id}/initialization")

    assert response.status_code == 200
    assert response.json()["thesis_version_id"] == version.thesis_version_id
    assert response.json()["evidence_set_review_id"] == "route-review"
