"""Ingest factual issuer disclosures into the human-reviewed Evidence Inbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection
from ..evidence.inbox import EvidenceInboxItem, EvidenceInboxSubjectType
from ..evidence.issuer_disclosures import IssuerDisclosureSubscription
from ..integrations.issuer_disclosures import IssuerDisclosureProvider
from ..repositories.sqlite_evidence_inbox import SQLiteEvidenceInboxRepository


@dataclass(frozen=True, slots=True)
class IssuerIngestionResult:
    subscription_id: str
    fetched: int
    ingested: int
    deduplicated: int


class IssuerEvidenceIngestionService:
    def __init__(self, inbox: SQLiteEvidenceInboxRepository) -> None:
        self.inbox = inbox

    def ingest(
        self,
        provider: IssuerDisclosureProvider,
        subscription: IssuerDisclosureSubscription,
        observed_at: datetime,
    ) -> IssuerIngestionResult:
        disclosures = provider.fetch(subscription, observed_at)
        inserted = 0
        deduplicated = 0
        for disclosure in disclosures:
            identity = str(uuid5(
                NAMESPACE_URL,
                f"issuer-disclosure:{disclosure.provider}:{disclosure.filing_id}:{disclosure.asset_id}",
            ))
            item = EvidenceInboxItem(
                identity, disclosure.provider, disclosure.source_locator, disclosure.title,
                disclosure.summary, disclosure.published_at, disclosure.available_at,
                disclosure.observed_at, disclosure.content_hash, disclosure.quality_warnings,
                observed_at, EvidenceInboxSubjectType.ASSET, disclosure.asset_id,
                EvidenceDirection.NEUTRAL,
            )
            before = self.inbox.has_identity(item)
            self.inbox.ingest(item)
            if before:
                deduplicated += 1
            else:
                inserted += 1
        return IssuerIngestionResult(subscription.subscription_id, len(disclosures), inserted, deduplicated)
