"""Auditable daily Thesis update for V2 shadow mode."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Protocol

from ..contracts import ConfidenceBand, ThesisScope, ThesisStatus, confidence_band
from ..thesis.models import ResearchReview, Thesis, ThesisVersion


@dataclass(frozen=True, slots=True)
class DailyThesisSnapshot:
    thesis_id: str
    name: str
    parent_thesis_id: str | None
    scope: ThesisScope
    research_state: str
    version_id: str | None
    version_number: int | None
    status: ThesisStatus | None
    confidence: float | None
    confidence_band: ConfidenceBand | None
    evidence_set_id: str | None
    supporting_evidence_count: int
    counter_evidence_count: int
    next_review_at: datetime | None
    latest_change: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scope"] = self.scope.value
        payload["status"] = self.status.value if self.status else None
        payload["confidence_band"] = self.confidence_band.value if self.confidence_band else None
        payload["next_review_at"] = self.next_review_at.isoformat() if self.next_review_at else None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DailyThesisSnapshot":
        return cls(
            thesis_id=payload["thesis_id"],
            name=payload["name"],
            parent_thesis_id=payload["parent_thesis_id"],
            scope=ThesisScope(payload["scope"]),
            research_state=payload["research_state"],
            version_id=payload["version_id"],
            version_number=payload["version_number"],
            status=ThesisStatus(payload["status"]) if payload["status"] else None,
            confidence=payload["confidence"],
            confidence_band=ConfidenceBand(payload["confidence_band"]) if payload["confidence_band"] else None,
            evidence_set_id=payload["evidence_set_id"],
            supporting_evidence_count=payload["supporting_evidence_count"],
            counter_evidence_count=payload["counter_evidence_count"],
            next_review_at=datetime.fromisoformat(payload["next_review_at"]) if payload["next_review_at"] else None,
            latest_change=payload["latest_change"],
        )


@dataclass(frozen=True, slots=True)
class DailyThesisReport:
    report_id: str
    report_date: date
    information_cutoff: datetime
    generated_at: datetime
    mode: str
    snapshots: tuple[DailyThesisSnapshot, ...]
    due_review_count: int
    warnings: tuple[str, ...]
    conclusion: str

    @property
    def initialized_count(self) -> int:
        return sum(item.research_state == "versioned" for item in self.snapshots)

    @property
    def uninitialized_count(self) -> int:
        return len(self.snapshots) - self.initialized_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_date": self.report_date.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "mode": self.mode,
            "snapshots": [item.to_dict() for item in self.snapshots],
            "initialized_count": self.initialized_count,
            "uninitialized_count": self.uninitialized_count,
            "due_review_count": self.due_review_count,
            "warnings": list(self.warnings),
            "conclusion": self.conclusion,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DailyThesisReport":
        return cls(
            report_id=payload["report_id"],
            report_date=date.fromisoformat(payload["report_date"]),
            information_cutoff=datetime.fromisoformat(payload["information_cutoff"]),
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            mode=payload["mode"],
            snapshots=tuple(DailyThesisSnapshot.from_dict(item) for item in payload["snapshots"]),
            due_review_count=payload["due_review_count"],
            warnings=tuple(payload["warnings"]),
            conclusion=payload["conclusion"],
        )


class DailyThesisReadRepository(Protocol):
    def list_theses(self) -> list[Thesis]: ...

    def current_version(self, thesis_id: str, as_of: datetime) -> ThesisVersion: ...

    def due_reviews(self, as_of: datetime) -> list[ResearchReview]: ...


class DailyThesisUpdateService:
    def __init__(self, repository: DailyThesisReadRepository):
        self.repository = repository

    def generate(
        self,
        report_id: str,
        information_cutoff: datetime,
        generated_at: datetime,
        mode: str = "shadow",
        report_date: date | None = None,
    ) -> DailyThesisReport:
        if information_cutoff.tzinfo is None or generated_at.tzinfo is None:
            raise ValueError("report timestamps must be timezone-aware")
        snapshots: list[DailyThesisSnapshot] = []
        for thesis in self.repository.list_theses():
            try:
                version = self.repository.current_version(thesis.thesis_id, information_cutoff)
            except KeyError:
                snapshots.append(self._uninitialized_snapshot(thesis))
            else:
                snapshots.append(self._versioned_snapshot(thesis, version))
        uninitialized = sum(item.research_state == "uninitialized" for item in snapshots)
        warnings = (
            (f"{uninitialized} thesis blueprints have no evidence-backed version; no confidence is shown.",)
            if uninitialized
            else ()
        )
        conclusion = (
            "Thesis initialization remains incomplete. Continue evidence collection and research review; "
            "no Research Candidate assessment was performed."
            if uninitialized
            else "All tracked theses have point-in-time versions. No Research Candidate assessment was performed."
        )
        return DailyThesisReport(
            report_id=report_id,
            report_date=report_date or information_cutoff.date(),
            information_cutoff=information_cutoff,
            generated_at=generated_at,
            mode=mode,
            snapshots=tuple(snapshots),
            due_review_count=len(self.repository.due_reviews(information_cutoff)),
            warnings=warnings,
            conclusion=conclusion,
        )

    @staticmethod
    def _uninitialized_snapshot(thesis: Thesis) -> DailyThesisSnapshot:
        return DailyThesisSnapshot(
            thesis.thesis_id,
            thesis.name,
            thesis.parent_thesis_id,
            thesis.scope,
            "uninitialized",
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            0,
            None,
            None,
        )

    @staticmethod
    def _versioned_snapshot(thesis: Thesis, version: ThesisVersion) -> DailyThesisSnapshot:
        return DailyThesisSnapshot(
            thesis.thesis_id,
            thesis.name,
            thesis.parent_thesis_id,
            thesis.scope,
            "versioned",
            version.thesis_version_id,
            version.version_number,
            version.status,
            version.confidence,
            confidence_band(version.confidence),
            version.evidence_set_id,
            len(version.supporting_evidence_ids),
            len(version.counter_evidence_ids),
            version.next_review_at,
            version.change_summary,
        )


class DailyThesisMarkdownRenderer:
    def render(self, report: DailyThesisReport) -> str:
        lines = [
            "# AI Investment Research Daily — Thesis Update",
            "",
            f"Date: {report.report_date.isoformat()}",
            f"Mode: {report.mode}",
            f"Information cutoff: {report.information_cutoff.isoformat()}",
            "",
            "## Research coverage",
            "",
            f"- Versioned theses: {report.initialized_count}",
            f"- Uninitialized blueprints: {report.uninitialized_count}",
            f"- Reviews due: {report.due_review_count}",
            "",
            "## Thesis tree",
            "",
        ]
        for item in report.snapshots:
            if item.research_state == "uninitialized":
                lines.append(f"- {item.name} (`{item.thesis_id}`): evidence review pending")
                continue
            lines.append(
                f"- {item.name} (`{item.thesis_id}`): {item.status.value}, "
                f"confidence {item.confidence_band.value}, version {item.version_number}"
            )
        if report.warnings:
            lines.extend(("", "## Data-quality warnings", ""))
            lines.extend(f"- {warning}" for warning in report.warnings)
        lines.extend(("", "## Today's conclusion", "", report.conclusion, "", "_Research output, not a trade instruction._"))
        return "\n".join(lines)
