"""Ingest normalized macro observations into the existing Evidence Inbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..macro.fred_provider import FredMacroEvidenceProvider
from ..macro.models import MacroEvidenceBatch
from ..repositories.sqlite_evidence_inbox import SQLiteEvidenceInboxRepository


@dataclass(frozen=True, slots=True)
class MacroEvidenceIngestionResult:
    batch: MacroEvidenceBatch
    ingested: int
    deduplicated: int


class MacroEvidenceIngestionService:
    def __init__(self, inbox: SQLiteEvidenceInboxRepository) -> None:
        self.inbox = inbox

    def ingest_fred(
        self,
        provider: FredMacroEvidenceProvider,
        *,
        as_of: date,
        ingested_at: datetime,
    ) -> MacroEvidenceIngestionResult:
        batch = provider.load(as_of=as_of)
        effective_ingested_at = max(ingested_at, batch.retrieved_at)
        inserted = 0
        deduplicated = 0
        for observation in batch.observations:
            item = observation.to_inbox_item(effective_ingested_at)
            existed = self.inbox.has_identity(item)
            if existed:
                deduplicated += 1
                continue
            self.inbox.ingest(item)
            inserted += 1
        return MacroEvidenceIngestionResult(batch, inserted, deduplicated)
