"""Record an explicit, append-only human review of a Thesis evidence set."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from src.config.accessor import get_env_config  # noqa: E402
from src.config.paths import get_data_dir  # noqa: E402
from src.investment_research.evidence.readiness import (  # noqa: E402
    EvidenceSetReview,
    EvidenceSetReviewDecision,
)
from src.investment_research.repositories.sqlite_evidence_set_reviews import (  # noqa: E402
    SQLiteEvidenceSetReviewRepository,
)


def _database_path() -> Path:
    configured = get_env_config().paths.vibe_investment_research_db_path.strip()
    return Path(configured).expanduser() if configured else get_data_dir() / "investment_research_v2.sqlite3"


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone offset")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record a human Evidence Set Review. This does not initialize a Thesis."
    )
    parser.add_argument("--thesis-id", required=True)
    parser.add_argument("--association-id", action="append", required=True)
    parser.add_argument("--information-cutoff", type=_aware_datetime, required=True)
    parser.add_argument("--decision", choices=[item.value for item in EvidenceSetReviewDecision], required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--reviewed-at", type=_aware_datetime, required=True)
    parser.add_argument("--strongest-counter-association-id")
    parser.add_argument("--missing-evidence", action="append", default=[])
    parser.add_argument("--quality-exception-rationale")
    parser.add_argument("--approval-reference")
    parser.add_argument("--database", type=Path)
    return parser


def record_from_args(args: argparse.Namespace) -> EvidenceSetReview:
    review = EvidenceSetReview.create(
        args.thesis_id,
        tuple(args.association_id),
        args.information_cutoff,
        EvidenceSetReviewDecision(args.decision),
        args.reviewer,
        args.rationale,
        args.reviewed_at,
        args.strongest_counter_association_id,
        tuple(args.missing_evidence),
        args.quality_exception_rationale,
        args.approval_reference,
    )
    return SQLiteEvidenceSetReviewRepository(args.database or _database_path()).record(review)


def main() -> int:
    review = record_from_args(build_parser().parse_args())
    print(
        json.dumps(
            {
                "review_id": review.review_id,
                "thesis_id": review.thesis_id,
                "decision": review.decision.value,
                "information_cutoff": review.information_cutoff.isoformat(),
                "reviewed_at": review.reviewed_at.isoformat(),
                "message": "Evidence Set Review recorded; no Thesis Version was created.",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
