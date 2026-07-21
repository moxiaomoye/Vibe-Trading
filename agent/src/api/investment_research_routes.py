"""Read-only HTTP surface for AI Investment Researcher V2."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query

from src.config.accessor import get_env_config
from src.config.paths import get_data_dir
from src.investment_research.discovery.models import DiscoveryDisposition
from src.investment_research.evidence.inbox import EvidenceInboxStatus
from src.investment_research.evidence.associations import EvidenceSubjectType
from src.investment_research.application.evidence_readiness import ThesisEvidenceReadinessService
from src.investment_research.repositories.sqlite import SCHEMA_VERSION, SQLiteResearchRepository
from src.investment_research.repositories.sqlite_discovery import SQLiteDiscoveryRepository
from src.investment_research.repositories.sqlite_evidence_inbox import (
    EVIDENCE_INBOX_SCHEMA_VERSION,
    SQLiteEvidenceInboxRepository,
)
from src.investment_research.repositories.sqlite_evidence_associations import (
    EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
    SQLiteEvidenceAssociationRepository,
)
from src.investment_research.repositories.sqlite_evidence_set_reviews import (
    EVIDENCE_SET_REVIEW_SCHEMA_VERSION,
    SQLiteEvidenceSetReviewRepository,
)
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from src.investment_research.thesis.models import Thesis, ThesisVersion


AuthDep = Callable[..., Awaitable[Any] | Any]
_repository: SQLiteResearchRepository | None = None
_intelligence_repository: SQLiteIntelligenceRepository | None = None
_discovery_repository: SQLiteDiscoveryRepository | None = None
_evidence_inbox_repository: SQLiteEvidenceInboxRepository | None = None
_evidence_association_repository: SQLiteEvidenceAssociationRepository | None = None
_evidence_set_review_repository: SQLiteEvidenceSetReviewRepository | None = None


def _database_path() -> Path:
    configured = get_env_config().paths.vibe_investment_research_db_path.strip()
    return Path(configured).expanduser() if configured else get_data_dir() / "investment_research_v2.sqlite3"


def get_investment_research_repository() -> SQLiteResearchRepository:
    global _repository
    if _repository is None:
        _repository = SQLiteResearchRepository(_database_path())
    return _repository


def get_intelligence_repository() -> SQLiteIntelligenceRepository:
    global _intelligence_repository
    if _intelligence_repository is None:
        _intelligence_repository = SQLiteIntelligenceRepository(_database_path())
    return _intelligence_repository


def get_discovery_repository() -> SQLiteDiscoveryRepository:
    global _discovery_repository
    if _discovery_repository is None:
        _discovery_repository = SQLiteDiscoveryRepository(_database_path())
    return _discovery_repository


def get_evidence_inbox_repository() -> SQLiteEvidenceInboxRepository:
    global _evidence_inbox_repository
    if _evidence_inbox_repository is None:
        _evidence_inbox_repository = SQLiteEvidenceInboxRepository(_database_path())
    return _evidence_inbox_repository


def get_evidence_association_repository() -> SQLiteEvidenceAssociationRepository:
    global _evidence_association_repository
    if _evidence_association_repository is None:
        _evidence_association_repository = SQLiteEvidenceAssociationRepository(_database_path())
    return _evidence_association_repository


def get_evidence_set_review_repository() -> SQLiteEvidenceSetReviewRepository:
    global _evidence_set_review_repository
    if _evidence_set_review_repository is None:
        _evidence_set_review_repository = SQLiteEvidenceSetReviewRepository(_database_path())
    return _evidence_set_review_repository


def reset_investment_research_repository() -> None:
    global _repository, _intelligence_repository, _discovery_repository
    global _evidence_inbox_repository, _evidence_association_repository, _evidence_set_review_repository
    _repository = None
    _intelligence_repository = None
    _discovery_repository = None
    _evidence_inbox_repository = None
    _evidence_association_repository = None
    _evidence_set_review_repository = None


def _as_of(value: datetime | None) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise HTTPException(status_code=422, detail="as_of must include a timezone offset")
    return resolved


def _thesis_payload(thesis: Thesis, version: ThesisVersion | None) -> dict[str, Any]:
    return {
        "thesis_id": thesis.thesis_id,
        "name": thesis.name,
        "parent_thesis_id": thesis.parent_thesis_id,
        "scope": thesis.scope.value,
        "created_at": thesis.created_at.isoformat(),
        "current_version": _version_payload(version) if version else None,
        "research_state": "versioned" if version else "uninitialized",
    }


def _version_payload(version: ThesisVersion) -> dict[str, Any]:
    return {
        "thesis_version_id": version.thesis_version_id,
        "thesis_id": version.thesis_id,
        "version_number": version.version_number,
        "status": version.status.value,
        "core_claim": version.core_claim,
        "confidence": version.confidence,
        "evidence_set_id": version.evidence_set_id,
        "supporting_evidence_ids": list(version.supporting_evidence_ids),
        "counter_evidence_ids": list(version.counter_evidence_ids),
        "catalysts": list(version.catalysts),
        "kill_criteria": list(version.kill_criteria),
        "change_summary": version.change_summary,
        "effective_from": version.effective_from.isoformat(),
        "next_review_at": version.next_review_at.isoformat(),
        "supersedes_version_id": version.supersedes_version_id,
    }


def _readiness_payload(readiness: Any) -> dict[str, Any]:
    return {
        "thesis_id": readiness.thesis_id,
        "as_of": readiness.as_of.isoformat(),
        "verdict": readiness.verdict.value,
        "supporting_association_ids": list(readiness.supporting_association_ids),
        "counter_association_ids": list(readiness.counter_association_ids),
        "neutral_association_ids": list(readiness.neutral_association_ids),
        "blocking_gaps": list(readiness.blocking_gaps),
        "quality_warnings": list(readiness.quality_warnings),
        "first_rejection_question": readiness.first_rejection_question,
        "approval_review_id": readiness.approval_review_id,
    }


def register_investment_research_routes(app: FastAPI, require_auth: AuthDep) -> None:
    dependencies = [Depends(require_auth)]

    @app.get("/investment-research/status", dependencies=dependencies)
    async def investment_research_status() -> dict[str, Any]:
        config = get_env_config()
        repository = get_investment_research_repository()
        theses = repository.list_theses()
        inbox_counts = get_evidence_inbox_repository().status_counts()
        issuer_counts = get_evidence_inbox_repository().provider_status_counts("sec_edgar")
        return {
            "enabled": config.agent_tuning.vibe_investment_research_enabled,
            "shadow_mode": config.agent_tuning.vibe_investment_research_shadow_mode,
            "schema_version": SCHEMA_VERSION,
            "schema_components": {
                "research_core": SCHEMA_VERSION,
                "evidence_inbox": EVIDENCE_INBOX_SCHEMA_VERSION,
                "evidence_association": EVIDENCE_ASSOCIATION_SCHEMA_VERSION,
                "evidence_set_review": EVIDENCE_SET_REVIEW_SCHEMA_VERSION,
            },
            "thesis_count": len(theses),
            "evidence_inbox": {status.value: count for status, count in inbox_counts.items()},
            "issuer_disclosures": {
                "enabled": config.agent_tuning.vibe_investment_research_issuer_disclosures_enabled,
                "provider": "sec_edgar",
                "review_state": {status.value: count for status, count in issuer_counts.items()},
                "automatic_classification": False,
            },
            "positioning": "AI Investment Researcher",
            "output_contract": "Research Candidate, not a trade instruction",
        }

    @app.get("/investment-research/theses", dependencies=dependencies)
    async def investment_research_theses(as_of: datetime | None = Query(default=None)) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        cutoff = _as_of(as_of)
        payloads: list[dict[str, Any]] = []
        for thesis in repository.list_theses():
            try:
                version = repository.current_version(thesis.thesis_id, cutoff)
            except KeyError:
                version = None
            payloads.append(_thesis_payload(thesis, version))
        return payloads

    @app.get("/investment-research/theses/{thesis_id}", dependencies=dependencies)
    async def investment_research_thesis(
        thesis_id: str,
        as_of: datetime | None = Query(default=None),
    ) -> dict[str, Any]:
        repository = get_investment_research_repository()
        try:
            thesis = repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        try:
            version = repository.current_version(thesis_id, _as_of(as_of))
        except KeyError:
            version = None
        return _thesis_payload(thesis, version)

    @app.get("/investment-research/theses/{thesis_id}/versions", dependencies=dependencies)
    async def investment_research_thesis_versions(thesis_id: str) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        return [_version_payload(version) for version in repository.list_thesis_versions(thesis_id)]

    @app.get("/investment-research/theses/{thesis_id}/initialization", dependencies=dependencies)
    async def investment_research_thesis_initialization(thesis_id: str) -> dict[str, Any]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        versions = repository.list_thesis_versions(thesis_id)
        if not versions:
            return {"thesis_id": thesis_id, "initialized": False, "research_state": "uninitialized"}
        first = versions[0]
        try:
            audit = repository.get_initialization_audit(first.thesis_version_id)
        except KeyError:
            return {
                "thesis_id": thesis_id,
                "initialized": True,
                "research_state": "legacy_version_without_initialization_audit",
                "thesis_version_id": first.thesis_version_id,
            }
        return {
            "thesis_id": thesis_id,
            "initialized": True,
            "research_state": "evidence_backed",
            "thesis_version_id": first.thesis_version_id,
            "initializer": audit.initializer,
            "approval_reference": audit.approval_reference,
            "evidence_set_review_id": audit.evidence_set_review_id,
            "initialized_at": audit.initialized_at.isoformat(),
        }

    @app.get("/investment-research/evidence-inbox", dependencies=dependencies)
    async def investment_research_evidence_inbox(
        status: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        try:
            status_filter = EvidenceInboxStatus(status) if status else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown evidence inbox status") from exc
        rows = get_evidence_inbox_repository().list_items(status_filter, limit)
        return [
            {
                "inbox_item_id": row.item.inbox_item_id,
                "status": row.status.value,
                "provider": row.item.provider,
                "source_locator": row.item.source_locator,
                "title": row.item.title,
                "summary": row.item.summary,
                "published_at": row.item.published_at.isoformat(),
                "available_at": row.item.available_at.isoformat(),
                "observed_at": row.item.observed_at.isoformat(),
                "ingested_at": row.item.ingested_at.isoformat(),
                "quality_warnings": list(row.item.quality_warnings),
                "proposed_subject_type": row.item.proposed_subject_type.value,
                "proposed_subject_id": row.item.proposed_subject_id,
                "proposed_direction": row.item.proposed_direction.value,
                "review": None if row.review is None else {
                    "review_id": row.review.review_id,
                    "decision": row.review.decision.value,
                    "rationale": row.review.rationale,
                    "reviewer": row.review.reviewer,
                    "reviewed_at": row.review.reviewed_at.isoformat(),
                    "final_subject_type": (
                        row.review.final_subject_type.value if row.review.final_subject_type else None
                    ),
                    "final_subject_id": row.review.final_subject_id,
                    "final_direction": row.review.final_direction.value if row.review.final_direction else None,
                },
            }
            for row in rows
        ]

    @app.get("/investment-research/evidence-associations", dependencies=dependencies)
    async def investment_research_evidence_associations(
        subject_type: str = Query(...),
        subject_id: str = Query(..., min_length=1),
        as_of: datetime | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        try:
            resolved_type = EvidenceSubjectType(subject_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown evidence subject type") from exc
        associations = get_evidence_association_repository().list_for_subject(
            resolved_type, subject_id, _as_of(as_of)
        )
        return [
            {
                "association_id": association.association_id,
                "evidence_id": association.evidence_id,
                "subject_type": association.subject_type.value,
                "subject_id": association.subject_id,
                "direction": association.direction.value,
                "assessed_at": association.assessed_at.isoformat(),
                "assessor": association.assessor,
                "rationale": association.rationale,
                "supersedes_association_id": association.supersedes_association_id,
            }
            for association in associations
        ]

    @app.get("/investment-research/evidence-readiness", dependencies=dependencies)
    async def investment_research_evidence_readiness(
        as_of: datetime | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        cutoff = _as_of(as_of)
        service = ThesisEvidenceReadinessService(
            get_evidence_association_repository(), repository, get_evidence_set_review_repository()
        )
        payloads: list[dict[str, Any]] = []
        for thesis in repository.list_theses():
            try:
                repository.current_version(thesis.thesis_id, cutoff)
            except KeyError:
                payloads.append(_readiness_payload(service.assess(thesis.thesis_id, cutoff)))
        return payloads

    @app.get(
        "/investment-research/theses/{thesis_id}/evidence-readiness",
        dependencies=dependencies,
    )
    async def investment_research_thesis_evidence_readiness(
        thesis_id: str,
        as_of: datetime | None = Query(default=None),
    ) -> dict[str, Any]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        cutoff = _as_of(as_of)
        service = ThesisEvidenceReadinessService(
            get_evidence_association_repository(), repository, get_evidence_set_review_repository()
        )
        return _readiness_payload(service.assess(thesis_id, cutoff))

    @app.get(
        "/investment-research/theses/{thesis_id}/evidence-set-reviews",
        dependencies=dependencies,
    )
    async def investment_research_thesis_evidence_set_reviews(
        thesis_id: str,
        as_of: datetime | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        repository = get_investment_research_repository()
        try:
            repository.get_thesis(thesis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="thesis not found") from exc
        reviews = get_evidence_set_review_repository().list_for_thesis(
            thesis_id, _as_of(as_of)
        )
        return [
            {
                "review_id": review.review_id,
                "thesis_id": review.thesis_id,
                "association_ids": list(review.association_ids),
                "information_cutoff": review.information_cutoff.isoformat(),
                "decision": review.decision.value,
                "reviewer": review.reviewer,
                "rationale": review.rationale,
                "reviewed_at": review.reviewed_at.isoformat(),
                "strongest_counter_association_id": review.strongest_counter_association_id,
                "missing_evidence": list(review.missing_evidence),
                "quality_exception_rationale": review.quality_exception_rationale,
                "approval_reference": review.approval_reference,
            }
            for review in reviews
        ]

    @app.get("/investment-research/reviews", dependencies=dependencies)
    async def investment_research_reviews(as_of: datetime | None = Query(default=None)) -> list[dict[str, Any]]:
        reviews = get_investment_research_repository().due_reviews(_as_of(as_of))
        return [
            {
                "review_id": review.review_id,
                "thesis_id": review.thesis_id,
                "base_version_id": review.base_version_id,
                "scheduled_for": review.scheduled_for.isoformat(),
                "status": review.status.value,
            }
            for review in reviews
        ]

    @app.get("/investment-research/daily/{report_date}", dependencies=dependencies)
    async def investment_research_daily(report_date: date, mode: str = Query(default="shadow")) -> dict[str, Any]:
        try:
            return get_investment_research_repository().get_daily_thesis_report(report_date, mode).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="daily thesis report not found") from exc

    @app.get("/investment-research/daily-research/{report_date}", dependencies=dependencies)
    async def investment_research_full_daily(
        report_date: date, mode: str = Query(default="shadow")
    ) -> dict[str, Any]:
        try:
            return get_intelligence_repository().get_daily_research_report(report_date, mode).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="daily research report not found") from exc

    @app.get("/investment-research/discovery-leads", dependencies=dependencies)
    async def investment_research_discovery_leads(
        as_of: datetime | None = Query(default=None),
        disposition: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        try:
            disposition_filter = DiscoveryDisposition(disposition) if disposition else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown discovery disposition") from exc
        leads = get_discovery_repository().list_leads(_as_of(as_of), disposition_filter)
        return [
            {
                "lead_id": lead.lead_id,
                "asset_id": lead.asset_id,
                "thesis_version_id": lead.thesis_version_id,
                "evidence_set_id": lead.evidence_set_id,
                "disposition": lead.disposition.value,
                "reasons": list(lead.reasons),
                "missing_evidence": list(lead.missing_evidence),
                "first_rejection_question": lead.first_rejection_question,
                "as_of": lead.as_of.isoformat(),
            }
            for lead in leads
        ]
