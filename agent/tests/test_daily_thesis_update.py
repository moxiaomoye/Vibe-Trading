from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.contracts import EvidenceDirection, ThesisStatus
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.intelligence.daily_thesis import DailyThesisMarkdownRenderer, DailyThesisUpdateService
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.thesis.models import ThesisVersion
from src.investment_research.thesis.seeds import import_thesis_identities, load_blueprint_manifest


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _repository(tmp_path) -> SQLiteResearchRepository:
    repository = SQLiteResearchRepository(tmp_path / "research.sqlite3")
    import_thesis_identities(repository, load_blueprint_manifest(), NOW)
    return repository


def test_shadow_report_refuses_to_invent_confidence_for_blueprints(tmp_path) -> None:
    repository = _repository(tmp_path)

    report = DailyThesisUpdateService(repository).generate("report-1", NOW, NOW + timedelta(minutes=1))
    rendered = DailyThesisMarkdownRenderer().render(report)

    assert report.initialized_count == 0
    assert report.uninitialized_count == 8
    assert all(item.confidence is None for item in report.snapshots)
    assert "no Research Candidate assessment was performed" in report.conclusion
    assert "evidence review pending" in rendered
    assert "not a trade instruction" in rendered


def test_shadow_report_contains_only_point_in_time_versions(tmp_path) -> None:
    repository = _repository(tmp_path)
    evidence = Evidence(
        "owner-reviewed-evidence",
        "fixture",
        "fixture://owner-reviewed-evidence",
        "Owner-reviewed primary-source fixture",
        "Fixture evidence for deterministic testing.",
        EvidenceDirection.SUPPORTING,
        NOW,
        NOW,
        NOW,
        "owner-reviewed-hash",
    )
    repository.save_evidence(evidence)
    repository.save_evidence_set(EvidenceSet("root-set", "ai-industry", NOW, (evidence.evidence_id,), NOW))
    repository.append_thesis_version(
        ThesisVersion(
            "root-v1",
            "ai-industry",
            1,
            ThesisStatus.DRAFT,
            "Owner review is required before activation.",
            0.55,
            "root-set",
            (evidence.evidence_id,),
            (),
            (),
            ("Evidence invalidated",),
            "Initial evidence-backed draft",
            NOW,
            NOW + timedelta(days=7),
        )
    )

    before = DailyThesisUpdateService(repository).generate("before", NOW - timedelta(seconds=1), NOW)
    after = DailyThesisUpdateService(repository).generate("after", NOW, NOW + timedelta(minutes=1))

    assert before.initialized_count == 0
    assert after.initialized_count == 1
    root = next(item for item in after.snapshots if item.thesis_id == "ai-industry")
    assert root.status == ThesisStatus.DRAFT
    assert root.version_id == "root-v1"


def test_daily_report_round_trip_is_auditable(tmp_path) -> None:
    repository = _repository(tmp_path)
    report = DailyThesisUpdateService(repository).generate("report-1", NOW, NOW + timedelta(minutes=1))

    repository.save_daily_thesis_report(report)
    restored = repository.get_daily_thesis_report(NOW.date())

    assert restored.to_dict() == report.to_dict()
    with pytest.raises(KeyError):
        repository.get_daily_thesis_report((NOW - timedelta(days=1)).date())


def test_daily_report_requires_timezone_aware_cutoff(tmp_path) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        DailyThesisUpdateService(repository).generate("report", NOW.replace(tzinfo=None), NOW)

