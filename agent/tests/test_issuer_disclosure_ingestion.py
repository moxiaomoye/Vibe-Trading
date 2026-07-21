from __future__ import annotations

from datetime import datetime, timezone

from src.investment_research.application.issuer_evidence_ingestion import IssuerEvidenceIngestionService
from src.investment_research.contracts import EvidenceDirection
from src.investment_research.evidence.inbox import EvidenceInboxStatus, EvidenceInboxSubjectType
from src.investment_research.evidence.issuer_disclosures import IssuerDisclosureSubscription
from src.investment_research.integrations.issuer_disclosures import SecEdgarDisclosureProvider
from src.investment_research.repositories.sqlite_evidence_inbox import SQLiteEvidenceInboxRepository


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


def _subscription() -> IssuerDisclosureSubscription:
    return IssuerDisclosureSubscription(
        "sub-aapl", "asset-us-aapl", "US", "AAPL", "0000320193", ("10-Q", "8-K"),
    )


def _payload(acceptance: str = "2026-07-20T20:31:45.000Z") -> dict:
    return {"filings": {"recent": {
        "form": ["10-Q", "10-K", "8-K"],
        "accessionNumber": ["0000320193-26-000001", "future", "0000320193-26-000002"],
        "filingDate": ["2026-07-20", "2026-07-22", "2026-07-20"],
        "acceptanceDateTime": [acceptance, "2026-07-22T10:00:00Z", ""],
        "reportDate": ["2026-06-30", "2026-06-30", ""],
        "primaryDocument": ["q2.htm", "future.htm", "event.htm"],
        "primaryDocDescription": ["Quarterly report", "Annual report", "Current report"],
    }}}


def test_sec_provider_uses_acceptance_time_filters_forms_and_future_rows() -> None:
    provider = SecEdgarDisclosureProvider(
        resolve_cik=lambda _: "should-not-be-called",
        load_submissions=lambda _: _payload(),
    )
    rows = provider.fetch(_subscription(), NOW)

    assert [row.form for row in rows] == ["10-Q", "8-K"]
    assert rows[0].available_at.isoformat() == "2026-07-20T20:31:45+00:00"
    assert rows[0].quality_warnings == ()
    assert rows[1].available_at.isoformat().startswith("2026-07-20T23:59:59.999999")
    assert rows[1].quality_warnings == (
        "availability_time_inferred_from_filing_date_end_of_day",
    )


def test_ingestion_is_pending_neutral_asset_only_and_idempotent(tmp_path) -> None:
    inbox = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    provider = SecEdgarDisclosureProvider(
        load_submissions=lambda _: _payload(), resolve_cik=lambda _: None,
    )
    service = IssuerEvidenceIngestionService(inbox)

    first = service.ingest(provider, _subscription(), NOW)
    second = service.ingest(provider, _subscription(), NOW)

    assert (first.fetched, first.ingested, first.deduplicated) == (2, 2, 0)
    assert (second.fetched, second.ingested, second.deduplicated) == (2, 0, 2)
    pending = inbox.list_items(EvidenceInboxStatus.PENDING)
    assert len(pending) == 2
    assert all(row.item.proposed_subject_type == EvidenceInboxSubjectType.ASSET for row in pending)
    assert all(row.item.proposed_direction == EvidenceDirection.NEUTRAL for row in pending)
    assert inbox.list_items(EvidenceInboxStatus.ACCEPTED) == []
    with inbox._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM evidence_associations").fetchone()[0] == 0


def test_future_disclosure_is_never_ingested(tmp_path) -> None:
    payload = _payload("2026-07-22T20:31:45Z")
    payload["filings"]["recent"]["form"] = ["10-Q"]
    for key in payload["filings"]["recent"]:
        payload["filings"]["recent"][key] = payload["filings"]["recent"][key][:1]
    provider = SecEdgarDisclosureProvider(load_submissions=lambda _: payload, resolve_cik=lambda _: None)
    inbox = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")

    result = IssuerEvidenceIngestionService(inbox).ingest(provider, _subscription(), NOW)

    assert result.fetched == result.ingested == 0
    assert inbox.list_items() == []
