"""Versioned investment-thesis domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import ReviewStatus, ThesisScope, ThesisStatus, confidence_band


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Thesis:
    thesis_id: str
    name: str
    parent_thesis_id: str | None
    created_at: datetime
    scope: ThesisScope = ThesisScope.THEME

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if not self.thesis_id or not self.name.strip():
            raise ValueError("thesis_id and name are required")
        if self.parent_thesis_id == self.thesis_id:
            raise ValueError("a thesis cannot be its own parent")


@dataclass(frozen=True, slots=True)
class ThesisVersion:
    thesis_version_id: str
    thesis_id: str
    version_number: int
    status: ThesisStatus
    core_claim: str
    confidence: float
    evidence_set_id: str
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    catalysts: tuple[str, ...]
    kill_criteria: tuple[str, ...]
    change_summary: str
    effective_from: datetime
    next_review_at: datetime
    supersedes_version_id: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.effective_from, "effective_from")
        _require_aware(self.next_review_at, "next_review_at")
        if self.version_number < 1:
            raise ValueError("version_number must be positive")
        if not self.thesis_version_id or not self.thesis_id or not self.core_claim.strip():
            raise ValueError("version id, thesis id, and core claim are required")
        confidence_band(self.confidence)
        if self.next_review_at < self.effective_from:
            raise ValueError("next_review_at cannot precede effective_from")
        if set(self.supporting_evidence_ids) & set(self.counter_evidence_ids):
            raise ValueError("the same evidence cannot support and oppose a thesis version")
        if not self.kill_criteria:
            raise ValueError("a thesis version must define kill criteria")


@dataclass(frozen=True, slots=True)
class ResearchReview:
    review_id: str
    thesis_id: str
    base_version_id: str
    scheduled_for: datetime
    status: ReviewStatus = ReviewStatus.PENDING
    completed_at: datetime | None = None
    resulting_version_id: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.scheduled_for, "scheduled_for")
        if self.completed_at is not None:
            _require_aware(self.completed_at, "completed_at")
        if self.status == ReviewStatus.COMPLETED and self.completed_at is None:
            raise ValueError("a completed review requires completed_at")
        if self.status == ReviewStatus.FAILED and not self.failure_reason:
            raise ValueError("a failed review requires failure_reason")


@dataclass(frozen=True, slots=True)
class ThesisInitializationAudit:
    thesis_version_id: str
    initializer: str
    approval_reference: str
    evidence_set_review_id: str
    initialized_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.initialized_at, "initialized_at")
        if (
            not self.thesis_version_id
            or not self.initializer.strip()
            or not self.approval_reference.strip()
            or not self.evidence_set_review_id.strip()
        ):
            raise ValueError(
                "initialization version, initializer, approval reference, and Evidence Set Review are required"
            )
