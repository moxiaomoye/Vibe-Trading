"""Initialize Thesis Version 1 from a reviewed, point-in-time JSON manifest."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from src.config.accessor import get_env_config
from src.config.paths import get_data_dir
from src.investment_research.application.initialization import ThesisInitializationService
from src.investment_research.application.initialization_manifest import ThesisInitializationManifest
from src.investment_research.application.evidence_readiness import ThesisEvidenceReadinessService
from src.investment_research.evidence.readiness import EvidenceSetReadiness
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_evidence_associations import SQLiteEvidenceAssociationRepository
from src.investment_research.repositories.sqlite_evidence_set_reviews import SQLiteEvidenceSetReviewRepository
from src.investment_research.thesis.models import ThesisVersion


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


def initialize_manifest(
    manifest: ThesisInitializationManifest, database_path: Path,
) -> ThesisVersion:
    repository = SQLiteResearchRepository(database_path)
    association_repository = SQLiteEvidenceAssociationRepository(database_path)
    review_repository = SQLiteEvidenceSetReviewRepository(database_path)
    thesis = repository.get_thesis(manifest.thesis_id)
    try:
        evidence_set_review = review_repository.get(manifest.proposal.evidence_set_review_id)
    except KeyError as exc:
        raise ValueError("initialization references an Evidence Set Review that is not recorded") from exc
    for evidence in manifest.evidence:
        try:
            repository.save_evidence(evidence)
        except sqlite3.IntegrityError:
            if repository.get_evidence(evidence.evidence_id) != evidence:
                raise ValueError(f"evidence {evidence.evidence_id} already exists with different content") from None
    try:
        repository.save_evidence_set(manifest.evidence_set)
    except sqlite3.IntegrityError:
        if repository.get_evidence_set(manifest.evidence_set.evidence_set_id) != manifest.evidence_set:
            raise ValueError("evidence set identity already exists with different content") from None
    for association in manifest.associations:
        association_repository.append(association)
    readiness = ThesisEvidenceReadinessService(
        association_repository, repository, review_repository
    ).assess(manifest.thesis_id, manifest.initialized_at)
    if (
        readiness.verdict != EvidenceSetReadiness.APPROVED_FOR_INITIALIZATION
        or readiness.approval_review_id != evidence_set_review.review_id
    ):
        raise ValueError(
            "Evidence Set Review is stale, rejected, incomplete, or does not cover the current evidence set"
        )
    version = ThesisInitializationService(repository).initialize(
        thesis, manifest.evidence_set, manifest.evidence, manifest.proposal, manifest.initialized_at,
        evidence_set_review, manifest.associations,
    )
    return version


def main() -> int:
    args = _arguments()
    manifest = ThesisInitializationManifest.load(args.manifest)
    config = get_env_config()
    configured = config.paths.vibe_investment_research_db_path.strip()
    database_path = Path(configured).expanduser() if configured else get_data_dir() / "investment_research_v2.sqlite3"
    version = initialize_manifest(manifest, database_path)
    thesis = SQLiteResearchRepository(database_path).get_thesis(manifest.thesis_id)
    print(f"Database: {database_path}")
    print(f"Initialized Thesis: {thesis.thesis_id}")
    print(f"Version: {version.thesis_version_id}")
    print(f"Next review: {version.next_review_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
