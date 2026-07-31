"""Human-approved initialization for the focused daily research watchlist.

This module only orchestrates the existing evidence, review, and Thesis
initialization domain services.  It does not infer evidence from price action,
change Candidate rules, or create a parallel research store.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection, ThesisScope, ThesisStatus
from ..evidence.associations import EvidenceAssociation, EvidenceSubjectType
from ..evidence.models import Evidence, EvidenceSet
from ..evidence.readiness import EvidenceSetReview, EvidenceSetReviewDecision
from ..thesis.models import Thesis, ThesisVersion
from .initialization import ThesisInitializationProposal, ThesisInitializationService


@dataclass(frozen=True, slots=True)
class ThesisStarter:
    thesis_id: str
    symbol: str
    name: str
    scope: ThesisScope
    proposed_core_claim: str
    proposed_catalysts: tuple[str, ...]
    proposed_kill_criteria: tuple[str, ...]


THESIS_STARTERS: tuple[ThesisStarter, ...] = (
    ThesisStarter(
        thesis_id="thesis:600522.SH",
        symbol="600522.SH",
        name="中天科技长期价值逻辑",
        scope=ThesisScope.COMPANY,
        proposed_core_claim=(
            "中天科技的光通信、海缆与电网业务能够维持长期竞争力，"
            "当前价格波动可能阶段性偏离其可持续经营价值。"
        ),
        proposed_catalysts=(
            "高毛利光通信或海缆业务占比和盈利能力改善",
            "经营现金流与订单质量持续验证盈利增长",
        ),
        proposed_kill_criteria=(
            "核心业务竞争力或订单质量出现结构性恶化",
            "毛利率、现金流与资产负债表连续恶化且缺乏可信修复路径",
        ),
    ),
    ThesisStarter(
        thesis_id="thesis:588000.SH",
        symbol="588000.SH",
        name="科创50ETF长期价值逻辑",
        scope=ThesisScope.THEME,
        proposed_core_claim=(
            "科创50代表的中国硬科技核心资产长期产业逻辑仍然成立，"
            "系统性恐慌可能使指数价格阶段性偏离长期价值。"
        ),
        proposed_catalysts=(
            "核心成分股盈利预期和研发商业化进度改善",
            "科技板块估值与风险偏好完成再平衡",
        ),
        proposed_kill_criteria=(
            "核心成分股盈利与产业逻辑出现广泛且持续的结构性下修",
            "指数估值仍显著透支长期增长且缺乏盈利兑现",
        ),
    ),
)

_STARTERS_BY_ID = {item.thesis_id: item for item in THESIS_STARTERS}


@dataclass(frozen=True, slots=True)
class ManualEvidenceDraft:
    provider: str
    source_locator: str
    title: str
    summary: str
    published_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("provider", "source_locator", "title", "summary"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ManualThesisInitializationCommand:
    thesis_id: str
    core_claim: str
    confidence: float
    supporting_evidence: tuple[ManualEvidenceDraft, ...]
    counter_evidence: tuple[ManualEvidenceDraft, ...]
    catalysts: tuple[str, ...]
    kill_criteria: tuple[str, ...]
    next_review_at: datetime
    reviewer: str
    review_rationale: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class ManualThesisInitializationResult:
    thesis_id: str
    thesis_version_id: str
    initialized: bool
    created: bool
    evidence_count: int
    next_review_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "thesis_id": self.thesis_id,
            "thesis_version_id": self.thesis_version_id,
            "initialized": self.initialized,
            "created": self.created,
            "evidence_count": self.evidence_count,
            "next_review_at": self.next_review_at.isoformat(),
            "scheduler_started": False,
            "notification_sent": False,
            "trading_executed": False,
        }


class ResearchRepository(Protocol):
    def save_thesis(self, thesis: Thesis) -> None: ...
    def get_thesis(self, thesis_id: str) -> Thesis: ...
    def list_thesis_versions(self, thesis_id: str) -> list[ThesisVersion]: ...
    def save_evidence(self, evidence: Evidence) -> None: ...
    def get_evidence(self, evidence_id: str) -> Evidence: ...
    def save_evidence_set(self, evidence_set: EvidenceSet) -> None: ...
    def get_evidence_set(self, evidence_set_id: str) -> EvidenceSet: ...
    def record_initialization(self, version, audit, next_review) -> None: ...


class AssociationRepository(Protocol):
    def append(self, association: EvidenceAssociation) -> EvidenceAssociation: ...
    def list_for_subject(
        self, subject_type: EvidenceSubjectType, subject_id: str, as_of: datetime
    ) -> list[EvidenceAssociation]: ...


class EvidenceSetReviewRepository(Protocol):
    def record(self, review: EvidenceSetReview) -> EvidenceSetReview: ...


class ManualThesisInitializationService:
    """Create the first Thesis Version after one explicit human review."""

    def __init__(
        self,
        research: ResearchRepository,
        associations: AssociationRepository,
        reviews: EvidenceSetReviewRepository,
    ) -> None:
        self.research = research
        self.associations = associations
        self.reviews = reviews

    def status(self) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for starter in THESIS_STARTERS:
            try:
                versions = self.research.list_thesis_versions(starter.thesis_id)
            except KeyError:
                versions = []
            payload.append(
                {
                    "thesis_id": starter.thesis_id,
                    "symbol": starter.symbol,
                    "name": starter.name,
                    "scope": starter.scope.value,
                    "initialized": bool(versions),
                    "thesis_version_id": (
                        versions[0].thesis_version_id if versions else None
                    ),
                    "proposed_core_claim": starter.proposed_core_claim,
                    "proposed_catalysts": list(starter.proposed_catalysts),
                    "proposed_kill_criteria": list(
                        starter.proposed_kill_criteria
                    ),
                }
            )
        return payload

    def initialize(
        self,
        command: ManualThesisInitializationCommand,
        *,
        initialized_at: datetime,
    ) -> ManualThesisInitializationResult:
        starter = _STARTERS_BY_ID.get(command.thesis_id)
        if starter is None:
            raise ValueError("manual initialization is limited to the focused watchlist")
        if initialized_at.tzinfo is None or initialized_at.utcoffset() is None:
            raise ValueError("initialized_at must be timezone-aware")
        existing_versions = self.research.list_thesis_versions(command.thesis_id)
        if existing_versions:
            current = existing_versions[0]
            return ManualThesisInitializationResult(
                command.thesis_id,
                current.thesis_version_id,
                True,
                False,
                len(current.supporting_evidence_ids)
                + len(current.counter_evidence_ids),
                current.next_review_at,
            )
        self._validate(command, initialized_at)

        thesis = self._ensure_thesis(starter, initialized_at)
        support = tuple(
            self._build_evidence(command.thesis_id, item, "supporting", initialized_at)
            for item in command.supporting_evidence
        )
        counter = tuple(
            self._build_evidence(command.thesis_id, item, "counter", initialized_at)
            for item in command.counter_evidence
        )
        evidence = support + counter
        support_associations = tuple(
            EvidenceAssociation.create(
                item.evidence_id,
                EvidenceSubjectType.THESIS,
                command.thesis_id,
                EvidenceDirection.SUPPORTING,
                initialized_at,
                command.reviewer,
                command.review_rationale,
            )
            for item in support
        )
        counter_associations = tuple(
            EvidenceAssociation.create(
                item.evidence_id,
                EvidenceSubjectType.THESIS,
                command.thesis_id,
                EvidenceDirection.COUNTER,
                initialized_at,
                command.reviewer,
                command.review_rationale,
            )
            for item in counter
        )
        associations = support_associations + counter_associations

        current_associations = self.associations.list_for_subject(
            EvidenceSubjectType.THESIS,
            command.thesis_id,
            initialized_at,
        )
        proposed_association_ids = {item.association_id for item in associations}
        unexpected = {
            item.association_id for item in current_associations
        } - proposed_association_ids
        if unexpected:
            raise ValueError(
                "the Thesis already has different contextual evidence; "
                "review it through the full evidence workflow"
            )

        for item in evidence:
            self._save_evidence_idempotently(item)
        for association in associations:
            self.associations.append(association)

        evidence_ids = tuple(item.evidence_id for item in evidence)
        evidence_set = EvidenceSet(
            str(
                uuid5(
                    NAMESPACE_URL,
                    "manual-evidence-set:"
                    + command.thesis_id
                    + ":"
                    + ",".join(evidence_ids),
                )
            ),
            command.thesis_id,
            initialized_at,
            evidence_ids,
            initialized_at,
        )
        self._save_evidence_set_idempotently(evidence_set)

        association_ids = tuple(item.association_id for item in associations)
        strongest_counter = next(
            item.association_id
            for item in associations
            if item.direction == EvidenceDirection.COUNTER
        )
        approval_reference = (
            f"local-ui://thesis-review/{command.thesis_id}/"
            f"{evidence_set.evidence_set_id}"
        )
        review = EvidenceSetReview.create(
            thesis_id=command.thesis_id,
            association_ids=association_ids,
            information_cutoff=initialized_at,
            decision=EvidenceSetReviewDecision.APPROVE,
            reviewer=command.reviewer,
            rationale=command.review_rationale,
            reviewed_at=initialized_at,
            strongest_counter_association_id=strongest_counter,
            approval_reference=approval_reference,
        )
        self.reviews.record(review)

        proposal = ThesisInitializationProposal(
            status=ThesisStatus.ACTIVE,
            core_claim=command.core_claim.strip(),
            confidence=command.confidence,
            supporting_evidence_ids=tuple(item.evidence_id for item in support),
            counter_evidence_ids=tuple(item.evidence_id for item in counter),
            catalysts=_clean_lines(command.catalysts),
            kill_criteria=_clean_lines(command.kill_criteria),
            change_summary="Owner-approved initial Thesis version.",
            next_review_at=command.next_review_at,
            initializer=command.reviewer.strip(),
            approval_reference=approval_reference,
            evidence_set_review_id=review.review_id,
        )
        version = ThesisInitializationService(self.research).initialize(
            thesis,
            evidence_set,
            evidence,
            proposal,
            initialized_at,
            review,
            associations,
        )
        return ManualThesisInitializationResult(
            command.thesis_id,
            version.thesis_version_id,
            True,
            True,
            len(evidence),
            version.next_review_at,
        )

    @staticmethod
    def _validate(
        command: ManualThesisInitializationCommand,
        initialized_at: datetime,
    ) -> None:
        if not command.confirmed:
            raise ValueError("explicit human confirmation is required")
        if not command.core_claim.strip():
            raise ValueError("core_claim must not be empty")
        if not 0.0 <= command.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        if not command.supporting_evidence or not command.counter_evidence:
            raise ValueError("supporting and counter evidence are both required")
        if not _clean_lines(command.catalysts) or not _clean_lines(command.kill_criteria):
            raise ValueError("catalysts and kill criteria are both required")
        if not command.reviewer.strip() or not command.review_rationale.strip():
            raise ValueError("reviewer and review rationale are required")
        if command.next_review_at <= initialized_at:
            raise ValueError("next review must be after initialization")
        for item in command.supporting_evidence + command.counter_evidence:
            if item.published_at > initialized_at:
                raise ValueError("future evidence cannot initialize a Thesis")
        support_keys = {
            (item.provider.strip(), item.source_locator.strip(), item.title.strip())
            for item in command.supporting_evidence
        }
        counter_keys = {
            (item.provider.strip(), item.source_locator.strip(), item.title.strip())
            for item in command.counter_evidence
        }
        if support_keys & counter_keys:
            raise ValueError(
                "the same source item cannot be both supporting and counter evidence"
            )

    def _ensure_thesis(
        self, starter: ThesisStarter, created_at: datetime
    ) -> Thesis:
        try:
            existing = self.research.get_thesis(starter.thesis_id)
        except KeyError:
            thesis = Thesis(
                starter.thesis_id,
                starter.name,
                None,
                created_at,
                starter.scope,
            )
            self.research.save_thesis(thesis)
            return thesis
        if existing.name != starter.name or existing.scope != starter.scope:
            raise ValueError("existing Thesis identity conflicts with the watchlist definition")
        return existing

    @staticmethod
    def _build_evidence(
        thesis_id: str,
        draft: ManualEvidenceDraft,
        contextual_direction: str,
        observed_at: datetime,
    ) -> Evidence:
        payload = {
            "thesis_id": thesis_id,
            "provider": draft.provider.strip(),
            "source_locator": draft.source_locator.strip(),
            "title": draft.title.strip(),
            "summary": draft.summary.strip(),
            "published_at": draft.published_at.isoformat(),
            "contextual_direction": contextual_direction,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        return Evidence(
            evidence_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"manual-thesis-evidence:{thesis_id}:{content_hash}",
                )
            ),
            provider=draft.provider.strip(),
            source_locator=draft.source_locator.strip(),
            title=draft.title.strip(),
            summary=draft.summary.strip(),
            direction=EvidenceDirection.NEUTRAL,
            published_at=draft.published_at,
            available_at=draft.published_at,
            observed_at=observed_at,
            content_hash=content_hash,
        )

    def _save_evidence_idempotently(self, evidence: Evidence) -> None:
        try:
            existing = self.research.get_evidence(evidence.evidence_id)
        except KeyError:
            self.research.save_evidence(evidence)
            return
        if existing != evidence:
            raise ValueError("evidence identity conflicts with existing canonical evidence")

    def _save_evidence_set_idempotently(self, evidence_set: EvidenceSet) -> None:
        try:
            existing = self.research.get_evidence_set(evidence_set.evidence_set_id)
        except KeyError:
            self.research.save_evidence_set(evidence_set)
            return
        if (
            existing.thesis_id != evidence_set.thesis_id
            or existing.evidence_ids != evidence_set.evidence_ids
        ):
            raise ValueError("evidence set identity conflicts with existing research")


def _clean_lines(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in values if item.strip()))
