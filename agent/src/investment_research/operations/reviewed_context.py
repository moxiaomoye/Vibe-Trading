"""Read an auditable, point-in-time Thesis context for daily research.

The loader is intentionally read-only.  A Thesis is eligible only when its
first version has a persisted initialization audit and the current version's
exact Evidence Set can be reconstructed at the requested information cutoff.
Missing or inconsistent records are returned as explicit gaps so the caller
can fall back to an uninitialized draft without breaking the daily report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..evidence.models import Evidence, EvidenceSet
from ..thesis.models import ThesisInitializationAudit, ThesisVersion


class ReviewedContextRepository(Protocol):
    def current_version(self, thesis_id: str, as_of: datetime) -> ThesisVersion: ...

    def list_thesis_versions(self, thesis_id: str) -> list[ThesisVersion]: ...

    def get_initialization_audit(
        self, thesis_version_id: str
    ) -> ThesisInitializationAudit: ...

    def get_evidence_set(self, evidence_set_id: str) -> EvidenceSet: ...

    def get_evidence(self, evidence_id: str) -> Evidence: ...


@dataclass(frozen=True, slots=True)
class ReviewedResearchContext:
    thesis: ThesisVersion
    evidence_set: EvidenceSet
    evidence: tuple[Evidence, ...]
    initialization_audit: ThesisInitializationAudit


@dataclass(frozen=True, slots=True)
class ReviewedResearchContextResolution:
    context: ReviewedResearchContext | None
    gaps: tuple[str, ...] = ()


class ReviewedResearchContextLoader:
    """Resolve the latest audited Thesis state without mutating persistence."""

    def __init__(self, repository: ReviewedContextRepository):
        self._repository = repository

    def load(
        self, *, thesis_id: str, information_cutoff: datetime
    ) -> ReviewedResearchContextResolution:
        if not thesis_id.strip():
            return ReviewedResearchContextResolution(
                None, ("watchlist asset has no Thesis binding",)
            )
        if (
            information_cutoff.tzinfo is None
            or information_cutoff.utcoffset() is None
        ):
            raise ValueError("information_cutoff must be timezone-aware")

        try:
            current = self._repository.current_version(
                thesis_id, information_cutoff
            )
            versions = self._repository.list_thesis_versions(thesis_id)
        except KeyError:
            return ReviewedResearchContextResolution(
                None,
                (
                    f"no initialized Thesis version is available for {thesis_id} "
                    "at the information cutoff",
                ),
            )
        eligible_versions = [
            item for item in versions if item.effective_from <= information_cutoff
        ]
        if not eligible_versions:
            return ReviewedResearchContextResolution(
                None, (f"no point-in-time Thesis history is available for {thesis_id}",)
            )
        first = min(eligible_versions, key=lambda item: item.version_number)
        try:
            audit = self._repository.get_initialization_audit(
                first.thesis_version_id
            )
        except KeyError:
            return ReviewedResearchContextResolution(
                None,
                (
                    f"Thesis {thesis_id} has no auditable evidence-backed "
                    "initialization record",
                ),
            )

        try:
            evidence_set = self._repository.get_evidence_set(
                current.evidence_set_id
            )
            evidence = tuple(
                self._repository.get_evidence(evidence_id)
                for evidence_id in evidence_set.evidence_ids
            )
        except KeyError as exc:
            return ReviewedResearchContextResolution(
                None,
                (f"reviewed Thesis context is incomplete: missing {exc.args[0]}",),
            )

        gaps = _validate_context(
            current=current,
            evidence_set=evidence_set,
            evidence=evidence,
            information_cutoff=information_cutoff,
        )
        if gaps:
            return ReviewedResearchContextResolution(None, gaps)
        return ReviewedResearchContextResolution(
            ReviewedResearchContext(current, evidence_set, evidence, audit)
        )


def _validate_context(
    *,
    current: ThesisVersion,
    evidence_set: EvidenceSet,
    evidence: tuple[Evidence, ...],
    information_cutoff: datetime,
) -> tuple[str, ...]:
    gaps: list[str] = []
    if evidence_set.thesis_id != current.thesis_id:
        gaps.append("current Thesis version references another Thesis Evidence Set")
    if evidence_set.as_of > information_cutoff:
        gaps.append("reviewed Evidence Set is newer than the information cutoff")
    evidence_ids = set(evidence_set.evidence_ids)
    cited = set(current.supporting_evidence_ids) | set(
        current.counter_evidence_ids
    )
    if cited - evidence_ids:
        gaps.append("current Thesis version cites evidence outside its Evidence Set")
    if not current.supporting_evidence_ids:
        gaps.append("current Thesis version has no reviewed supporting evidence")
    if not current.counter_evidence_ids:
        gaps.append("current Thesis version has no reviewed counter evidence")
    if any(item.available_at > information_cutoff for item in evidence):
        gaps.append("reviewed Thesis context contains future evidence")
    try:
        evidence_set.validate_point_in_time(evidence)
    except ValueError as exc:
        gaps.append(f"reviewed Evidence Set failed point-in-time validation: {exc}")
    return tuple(dict.fromkeys(gaps))
