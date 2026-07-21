"""Strict, auditable creation of the first evidence-backed Thesis Version."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection, ReviewStatus, ThesisStatus
from ..evidence.associations import EvidenceAssociation, EvidenceSubjectType
from ..evidence.models import Evidence, EvidenceSet
from ..evidence.readiness import EvidenceSetReview, EvidenceSetReviewDecision
from ..thesis.models import ResearchReview, Thesis, ThesisInitializationAudit, ThesisVersion


@dataclass(frozen=True, slots=True)
class ThesisInitializationProposal:
    status: ThesisStatus
    core_claim: str
    confidence: float
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    catalysts: tuple[str, ...]
    kill_criteria: tuple[str, ...]
    change_summary: str
    next_review_at: datetime
    initializer: str
    approval_reference: str
    evidence_set_review_id: str


class InitializationRepository(Protocol):
    def list_thesis_versions(self, thesis_id: str) -> list[ThesisVersion]: ...

    def record_initialization(
        self, version: ThesisVersion, audit: ThesisInitializationAudit, next_review: ResearchReview
    ) -> None: ...


class ThesisInitializationService:
    def __init__(self, repository: InitializationRepository):
        self.repository = repository

    def initialize(
        self,
        thesis: Thesis,
        evidence_set: EvidenceSet,
        evidence: tuple[Evidence, ...],
        proposal: ThesisInitializationProposal,
        initialized_at: datetime,
        evidence_set_review: EvidenceSetReview,
        associations: tuple[EvidenceAssociation, ...],
    ) -> ThesisVersion:
        if initialized_at.tzinfo is None or initialized_at.utcoffset() is None:
            raise ValueError("initialized_at must be timezone-aware")
        if evidence_set.thesis_id != thesis.thesis_id:
            raise ValueError("initialization evidence set belongs to a different thesis")
        if evidence_set.as_of > initialized_at:
            raise ValueError("initialization cannot precede its evidence cutoff")
        evidence_set.validate_point_in_time(evidence)
        if proposal.status not in {ThesisStatus.ACTIVE, ThesisStatus.WEAKENING}:
            raise ValueError("an initialized thesis must be active or weakening")
        if not proposal.supporting_evidence_ids or not proposal.counter_evidence_ids:
            raise ValueError("initialization requires both supporting and counter evidence")
        if not proposal.catalysts or not proposal.kill_criteria:
            raise ValueError("initialization requires catalysts and kill criteria")
        if not proposal.initializer.strip() or not proposal.approval_reference.strip():
            raise ValueError("initialization requires an initializer and approval reference")
        if not proposal.evidence_set_review_id.strip():
            raise ValueError("initialization requires an Evidence Set Review id")
        if proposal.next_review_at <= initialized_at:
            raise ValueError("next review must be after initialization")
        referenced = set(proposal.supporting_evidence_ids) | set(proposal.counter_evidence_ids)
        unknown = referenced - set(evidence_set.evidence_ids)
        if unknown:
            raise ValueError(f"initialization references evidence outside the set: {sorted(unknown)}")
        direction_by_id: dict[str, EvidenceDirection] = {}
        for association in associations:
            if association.subject_type != EvidenceSubjectType.THESIS or association.subject_id != thesis.thesis_id:
                raise ValueError("initialization evidence association belongs to a different subject")
            if association.evidence_id not in evidence_set.evidence_ids:
                raise ValueError("initialization association references evidence outside the set")
            if association.assessed_at > evidence_set.as_of:
                raise ValueError("initialization association was assessed after the evidence cutoff")
            if association.evidence_id in direction_by_id:
                raise ValueError("initialization requires one current association per evidence item")
            direction_by_id[association.evidence_id] = association.direction
        missing_associations = referenced - set(direction_by_id)
        if missing_associations:
            raise ValueError(f"initialization evidence lacks contextual associations: {sorted(missing_associations)}")
        for evidence_id in proposal.supporting_evidence_ids:
            if direction_by_id[evidence_id] != EvidenceDirection.SUPPORTING:
                raise ValueError("supporting evidence must be explicitly classified as supporting")
        for evidence_id in proposal.counter_evidence_ids:
            if direction_by_id[evidence_id] != EvidenceDirection.COUNTER:
                raise ValueError("counter evidence must be explicitly classified as counter")
        association_ids = {association.association_id for association in associations}
        if evidence_set_review.review_id != proposal.evidence_set_review_id:
            raise ValueError("initialization proposal references a different Evidence Set Review")
        if evidence_set_review.decision != EvidenceSetReviewDecision.APPROVE:
            raise ValueError("initialization requires an approved Evidence Set Review")
        if evidence_set_review.thesis_id != thesis.thesis_id:
            raise ValueError("Evidence Set Review belongs to a different thesis")
        if evidence_set_review.information_cutoff != evidence_set.as_of:
            raise ValueError("Evidence Set Review cutoff does not match the evidence set")
        if evidence_set_review.reviewed_at > initialized_at:
            raise ValueError("initialization cannot precede Evidence Set Review approval")
        if set(evidence_set_review.association_ids) != association_ids:
            raise ValueError("Evidence Set Review does not cover the exact initialization associations")
        if evidence_set_review.approval_reference != proposal.approval_reference:
            raise ValueError("initialization approval reference does not match Evidence Set Review")
        counter_association_ids = {
            association.association_id
            for association in associations
            if association.direction == EvidenceDirection.COUNTER
        }
        if evidence_set_review.strongest_counter_association_id not in counter_association_ids:
            raise ValueError("Evidence Set Review strongest counter is not current counter evidence")
        quality_warnings = tuple(warning for item in evidence for warning in item.quality_warnings)
        if quality_warnings and not (evidence_set_review.quality_exception_rationale or "").strip():
            raise ValueError("initialization with quality warnings requires a reviewed exception rationale")

        identity_payload = asdict(proposal)
        identity_payload["status"] = proposal.status.value
        identity_payload["next_review_at"] = proposal.next_review_at.isoformat()
        digest = hashlib.sha256(
            json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        version_id = str(uuid5(NAMESPACE_URL, f"thesis-initialization:{thesis.thesis_id}:{evidence_set.evidence_set_id}:{digest}"))
        existing = self.repository.list_thesis_versions(thesis.thesis_id)
        if existing:
            if len(existing) == 1 and existing[0].thesis_version_id == version_id:
                return existing[0]
            raise ValueError("thesis already has an initialized version")
        version = ThesisVersion(
            version_id, thesis.thesis_id, 1, proposal.status, proposal.core_claim, proposal.confidence,
            evidence_set.evidence_set_id, proposal.supporting_evidence_ids, proposal.counter_evidence_ids,
            proposal.catalysts, proposal.kill_criteria, proposal.change_summary, initialized_at,
            proposal.next_review_at,
        )
        audit = ThesisInitializationAudit(
            version_id, proposal.initializer, proposal.approval_reference,
            proposal.evidence_set_review_id, initialized_at,
        )
        review = ResearchReview(
            str(uuid5(NAMESPACE_URL, f"thesis-review:{version_id}:{proposal.next_review_at.isoformat()}")),
            thesis.thesis_id, version_id, proposal.next_review_at, ReviewStatus.PENDING,
        )
        self.repository.record_initialization(version, audit, review)
        return version
