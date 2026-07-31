from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.investment_research.contracts import EvidenceDirection, ThesisStatus
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.operations.reviewed_context import (
    ReviewedResearchContextLoader,
)
from src.investment_research.thesis.models import (
    ThesisInitializationAudit,
    ThesisVersion,
)


NOW = datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)


def _context():
    support = Evidence(
        "support-1", "exchange", "https://example.test/support", "Support",
        "Reviewed primary support.", EvidenceDirection.NEUTRAL,
        NOW - timedelta(days=3), NOW - timedelta(days=3), NOW - timedelta(days=3),
        "hash-support",
    )
    counter = Evidence(
        "counter-1", "exchange", "https://example.test/counter", "Counter",
        "Reviewed primary counter.", EvidenceDirection.NEUTRAL,
        NOW - timedelta(days=2), NOW - timedelta(days=2), NOW - timedelta(days=2),
        "hash-counter",
    )
    evidence_set = EvidenceSet(
        "set-1", "thesis:600522.SH", NOW - timedelta(days=1),
        ("support-1", "counter-1"), NOW - timedelta(days=1),
    )
    version = ThesisVersion(
        "version-1", "thesis:600522.SH", 1, ThesisStatus.ACTIVE,
        "The issuer Thesis remains intact.", 0.82, "set-1",
        ("support-1",), ("counter-1",), ("next filing",),
        ("cash-flow deterioration",), "Approved initialization.", NOW - timedelta(days=1),
        NOW + timedelta(days=30),
    )
    audit = ThesisInitializationAudit(
        "version-1", "chief-analyst", "approval://review/1", "review-1",
        NOW - timedelta(days=1),
    )
    return version, evidence_set, (support, counter), audit


class _Repository:
    def __init__(self, *, include_audit: bool = True, future: bool = False):
        version, evidence_set, evidence, audit = _context()
        if future:
            evidence = (
                replace(evidence[0], available_at=NOW + timedelta(minutes=1),
                        observed_at=NOW + timedelta(minutes=1)),
                evidence[1],
            )
        self.version = version
        self.evidence_set = evidence_set
        self.evidence = {item.evidence_id: item for item in evidence}
        self.audit = audit if include_audit else None

    def current_version(self, thesis_id, as_of):
        if thesis_id != self.version.thesis_id or self.version.effective_from > as_of:
            raise KeyError(thesis_id)
        return self.version

    def list_thesis_versions(self, thesis_id):
        return [self.version] if thesis_id == self.version.thesis_id else []

    def get_initialization_audit(self, thesis_version_id):
        if self.audit is None:
            raise KeyError(thesis_version_id)
        return self.audit

    def get_evidence_set(self, evidence_set_id):
        if evidence_set_id != self.evidence_set.evidence_set_id:
            raise KeyError(evidence_set_id)
        return self.evidence_set

    def get_evidence(self, evidence_id):
        try:
            return self.evidence[evidence_id]
        except KeyError:
            raise KeyError(evidence_id) from None


def test_loader_returns_exact_audited_point_in_time_context():
    result = ReviewedResearchContextLoader(_Repository()).load(
        thesis_id="thesis:600522.SH", information_cutoff=NOW
    )

    assert result.gaps == ()
    assert result.context is not None
    assert result.context.thesis.status == ThesisStatus.ACTIVE
    assert result.context.evidence_set.evidence_ids == ("support-1", "counter-1")
    assert result.context.initialization_audit.approval_reference == "approval://review/1"


def test_loader_fails_closed_for_legacy_or_future_context():
    legacy = ReviewedResearchContextLoader(
        _Repository(include_audit=False)
    ).load(thesis_id="thesis:600522.SH", information_cutoff=NOW)
    future = ReviewedResearchContextLoader(
        _Repository(future=True)
    ).load(thesis_id="thesis:600522.SH", information_cutoff=NOW)

    assert legacy.context is None
    assert "no auditable" in legacy.gaps[0]
    assert future.context is None
    assert any("future evidence" in gap for gap in future.gaps)
