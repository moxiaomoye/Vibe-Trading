from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.investment_research.contracts import EvidenceDirection, ThesisScope
from src.investment_research.evidence.associations import EvidenceAssociation, EvidenceSubjectType
from src.investment_research.evidence.models import Evidence
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_evidence_associations import SQLiteEvidenceAssociationRepository
from src.investment_research.repositories.sqlite_evidence_set_reviews import SQLiteEvidenceSetReviewRepository
from src.investment_research.thesis.models import Thesis


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_evidence_set.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("review_evidence_set_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_controlled_cli_records_approval_without_initializing_thesis(tmp_path) -> None:
    path = tmp_path / "research.sqlite3"
    research = SQLiteResearchRepository(path)
    research.save_thesis(Thesis("thesis-a", "Thesis A", None, NOW, ThesisScope.THEME))
    associations = SQLiteEvidenceAssociationRepository(path)
    association_ids = []
    for evidence_id, direction in (
        ("support", EvidenceDirection.SUPPORTING),
        ("counter", EvidenceDirection.COUNTER),
    ):
        research.save_evidence(
            Evidence(
                evidence_id, "fixture", f"fixture://{evidence_id}", evidence_id, evidence_id,
                EvidenceDirection.NEUTRAL, NOW - timedelta(hours=2), NOW - timedelta(hours=1),
                NOW, f"hash-{evidence_id}",
            )
        )
        association_ids.append(
            associations.append(
                EvidenceAssociation.create(
                    evidence_id, EvidenceSubjectType.THESIS, "thesis-a", direction, NOW,
                    "analyst", f"{direction.value} context",
                )
            ).association_id
        )
    args = argparse.Namespace(
        thesis_id="thesis-a",
        association_id=association_ids,
        information_cutoff=NOW,
        decision="approve",
        reviewer="chief-analyst",
        rationale="The claim survives the strongest known counter evidence.",
        reviewed_at=NOW + timedelta(minutes=5),
        strongest_counter_association_id=association_ids[1],
        missing_evidence=[],
        quality_exception_rationale=None,
        approval_reference="committee-1",
        database=path,
    )

    review = _load_script().record_from_args(args)

    assert SQLiteEvidenceSetReviewRepository(path).get(review.review_id) == review
    assert research.list_thesis_versions("thesis-a") == []
