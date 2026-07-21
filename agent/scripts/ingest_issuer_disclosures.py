"""Load configured official issuer disclosures into the pending Evidence Inbox."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.investment_research.application.issuer_evidence_ingestion import IssuerEvidenceIngestionService
from src.investment_research.evidence.issuer_disclosures import IssuerDisclosureSubscription
from src.investment_research.integrations.issuer_disclosures import SecEdgarDisclosureProvider
from src.investment_research.repositories.sqlite_evidence_inbox import SQLiteEvidenceInboxRepository


def load_subscriptions(path: Path) -> tuple[IssuerDisclosureSubscription, ...]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("manifest_version") != 1:
        raise ValueError("issuer disclosure manifest_version must be 1")
    rows = payload.get("subscriptions")
    if not isinstance(rows, list):
        raise ValueError("subscriptions must be an array")
    subscriptions: list[IssuerDisclosureSubscription] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each subscription must be an object")
        subscriptions.append(IssuerDisclosureSubscription(
            subscription_id=str(row["subscription_id"]),
            asset_id=str(row["asset_id"]),
            market=str(row["market"]),
            symbol=str(row["symbol"]),
            issuer_id=str(row["issuer_id"]) if row.get("issuer_id") else None,
            forms=tuple(str(value) for value in row.get("forms", ("10-K", "10-Q", "8-K"))),
            enabled=bool(row.get("enabled", True)),
        ))
    return tuple(subscriptions)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscriptions", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    observed_at = datetime.now(timezone.utc)
    service = IssuerEvidenceIngestionService(SQLiteEvidenceInboxRepository(args.database))
    provider = SecEdgarDisclosureProvider()
    failures = 0
    for subscription in load_subscriptions(args.subscriptions):
        try:
            result = service.ingest(provider, subscription, observed_at)
            print(json.dumps({
                "subscription_id": result.subscription_id,
                "fetched": result.fetched,
                "ingested": result.ingested,
                "deduplicated": result.deduplicated,
                "classification": "pending_neutral",
            }, ensure_ascii=False))
        except Exception as exc:  # one issuer failure must not suppress the others
            failures += 1
            print(json.dumps({
                "subscription_id": subscription.subscription_id,
                "error": str(exc),
            }, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
