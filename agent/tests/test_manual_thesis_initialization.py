from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.application.manual_thesis_initialization import (
    ManualEvidenceDraft,
    ManualThesisInitializationCommand,
    ManualThesisInitializationService,
)
from src.investment_research.operations.reviewed_context import (
    ReviewedResearchContextLoader,
)
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_evidence_associations import (
    SQLiteEvidenceAssociationRepository,
)
from src.investment_research.repositories.sqlite_evidence_set_reviews import (
    SQLiteEvidenceSetReviewRepository,
)


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _service(tmp_path) -> tuple[
    ManualThesisInitializationService,
    SQLiteResearchRepository,
]:
    path = tmp_path / "research.sqlite3"
    research = SQLiteResearchRepository(path)
    return (
        ManualThesisInitializationService(
            research,
            SQLiteEvidenceAssociationRepository(path),
            SQLiteEvidenceSetReviewRepository(path),
        ),
        research,
    )


def _command(**overrides) -> ManualThesisInitializationCommand:
    values = {
        "thesis_id": "thesis:600522.SH",
        "core_claim": "Core businesses remain competitive while price may be dislocated.",
        "confidence": 0.62,
        "supporting_evidence": (
            ManualEvidenceDraft(
                "company_announcement",
                "https://example.test/support",
                "Operating cash flow remained positive",
                "The reviewed annual filing reports positive operating cash flow.",
                NOW - timedelta(days=2),
            ),
        ),
        "counter_evidence": (
            ManualEvidenceDraft(
                "company_announcement",
                "https://example.test/counter",
                "Gross margin remains below the prior cycle",
                "The reviewed filing shows that gross margin has not recovered.",
                NOW - timedelta(days=1),
            ),
        ),
        "catalysts": ("Higher-margin business mix improves",),
        "kill_criteria": ("Cash conversion deteriorates structurally",),
        "next_review_at": NOW + timedelta(days=30),
        "reviewer": "local-owner",
        "review_rationale": "I reviewed the cited support and counter evidence.",
        "confirmed": True,
    }
    values.update(overrides)
    return ManualThesisInitializationCommand(**values)


def test_manual_initialization_creates_audited_point_in_time_context(tmp_path) -> None:
    service, research = _service(tmp_path)

    result = service.initialize(_command(), initialized_at=NOW)

    assert result.created is True
    assert result.initialized is True
    assert result.evidence_count == 2
    loaded = ReviewedResearchContextLoader(research).load(
        thesis_id="thesis:600522.SH",
        information_cutoff=NOW + timedelta(minutes=1),
    )
    assert loaded.context is not None
    assert loaded.context.thesis.core_claim.startswith("Core businesses")
    assert len(loaded.context.thesis.supporting_evidence_ids) == 1
    assert len(loaded.context.thesis.counter_evidence_ids) == 1
    assert loaded.context.initialization_audit.approval_reference.startswith(
        "local-ui://thesis-review/"
    )


def test_manual_initialization_is_idempotent_after_success(tmp_path) -> None:
    service, _ = _service(tmp_path)
    first = service.initialize(_command(), initialized_at=NOW)

    repeated = service.initialize(
        _command(core_claim="A later form submission must not overwrite Version 1."),
        initialized_at=NOW + timedelta(minutes=5),
    )

    assert repeated.created is False
    assert repeated.thesis_version_id == first.thesis_version_id


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"confirmed": False}, "explicit human confirmation"),
        (
            {
                "supporting_evidence": (
                    ManualEvidenceDraft(
                        "fixture",
                        "fixture://future",
                        "Future fact",
                        "Not available at review time.",
                        NOW + timedelta(days=1),
                    ),
                )
            },
            "future evidence",
        ),
        ({"counter_evidence": ()}, "supporting and counter evidence"),
    ],
)
def test_manual_initialization_fails_closed(
    tmp_path, override: dict, message: str
) -> None:
    service, research = _service(tmp_path)

    with pytest.raises(ValueError, match=message):
        service.initialize(_command(**override), initialized_at=NOW)

    assert research.list_thesis_versions("thesis:600522.SH") == []


def test_status_is_limited_to_the_two_focused_assets(tmp_path) -> None:
    service, _ = _service(tmp_path)

    status = service.status()

    assert [item["symbol"] for item in status] == ["600522.SH", "588000.SH"]
    assert all(item["initialized"] is False for item in status)
