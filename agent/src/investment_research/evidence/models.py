"""Point-in-time evidence models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import EvidenceDirection


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    provider: str
    source_locator: str
    title: str
    summary: str
    direction: EvidenceDirection
    published_at: datetime
    available_at: datetime
    observed_at: datetime
    content_hash: str
    quality_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "provider", "source_locator", "title", "content_hash"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        for field_name in ("published_at", "available_at", "observed_at"):
            _require_aware(getattr(self, field_name), field_name)
        if self.available_at < self.published_at:
            raise ValueError("available_at cannot be earlier than published_at")
        if self.observed_at < self.available_at:
            raise ValueError("observed_at cannot be earlier than available_at")

    def is_available(self, as_of: datetime) -> bool:
        _require_aware(as_of, "as_of")
        return self.available_at <= as_of


@dataclass(frozen=True, slots=True)
class EvidenceSet:
    evidence_set_id: str
    thesis_id: str
    as_of: datetime
    evidence_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        _require_aware(self.created_at, "created_at")
        if not self.evidence_set_id or not self.thesis_id:
            raise ValueError("evidence_set_id and thesis_id are required")
        if not self.evidence_ids:
            raise ValueError("an evidence set must contain at least one evidence item")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")

    def validate_point_in_time(self, evidence: tuple[Evidence, ...]) -> None:
        by_id = {item.evidence_id: item for item in evidence}
        unknown = set(self.evidence_ids) - set(by_id)
        if unknown:
            raise ValueError(f"unknown evidence ids: {sorted(unknown)}")
        future = [item.evidence_id for item in evidence if item.evidence_id in self.evidence_ids and not item.is_available(self.as_of)]
        if future:
            raise ValueError(f"evidence unavailable as of {self.as_of.isoformat()}: {future}")

