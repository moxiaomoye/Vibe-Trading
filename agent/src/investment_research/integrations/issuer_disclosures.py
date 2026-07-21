"""Official issuer-disclosure providers with conservative point-in-time semantics."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Protocol

from ..evidence.issuer_disclosures import IssuerDisclosure, IssuerDisclosureSubscription

_DOC_BASE = "https://www.sec.gov/Archives/edgar/data"


class IssuerDisclosureProvider(Protocol):
    def fetch(
        self, subscription: IssuerDisclosureSubscription, observed_at: datetime,
    ) -> tuple[IssuerDisclosure, ...]: ...


class SecEdgarDisclosureProvider:
    """Read the SEC submissions index; it does not interpret filing content."""

    name = "sec_edgar"

    def __init__(
        self,
        resolve_cik: Callable[[str], str | None] | None = None,
        load_submissions: Callable[[str], dict[str, Any]] | None = None,
        limit: int = 40,
    ) -> None:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if resolve_cik is None or load_submissions is None:
            from backtest.loaders.sec_edgar_client import cik_for, get_submissions

            resolve_cik = resolve_cik or cik_for
            load_submissions = load_submissions or get_submissions
        self.resolve_cik = resolve_cik
        self.load_submissions = load_submissions
        self.limit = limit

    def fetch(
        self, subscription: IssuerDisclosureSubscription, observed_at: datetime,
    ) -> tuple[IssuerDisclosure, ...]:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not subscription.enabled:
            return ()
        cik = subscription.issuer_id or self.resolve_cik(subscription.symbol)
        if not cik:
            raise ValueError(f"SEC CIK not found for {subscription.symbol}")
        padded_cik = "".join(ch for ch in str(cik) if ch.isdigit()).zfill(10)
        payload = self.load_submissions(padded_cik)
        recent = ((payload.get("filings") or {}).get("recent") or {})
        if not isinstance(recent, dict):
            raise ValueError("SEC submissions payload has no filings.recent object")
        allowed = {form.upper() for form in subscription.forms}
        result: list[IssuerDisclosure] = []
        forms = recent.get("form") or []
        for index, raw_form in enumerate(forms):
            form = str(raw_form or "").strip().upper()
            if form not in allowed:
                continue
            accession = _at(recent, "accessionNumber", index)
            filing_date = _at(recent, "filingDate", index)
            primary_document = _at(recent, "primaryDocument", index)
            if not accession or not filing_date:
                continue
            published_at, warnings = _availability_time(
                _at(recent, "acceptanceDateTime", index), filing_date,
            )
            if published_at > observed_at:
                continue
            source = _document_url(padded_cik, accession, primary_document)
            if source is None:
                source = f"https://www.sec.gov/Archives/edgar/data/{int(padded_cik)}/{accession.replace('-', '')}"
                warnings = (*warnings, "primary_document_url_missing")
            description = _at(recent, "primaryDocDescription", index)
            report_date = _at(recent, "reportDate", index) or None
            title = description or f"{subscription.symbol.upper()} {form} filing"
            summary = f"{subscription.symbol.upper()} filed {form} with the SEC"
            if report_date:
                summary += f" for reporting period {report_date}"
            summary += f"; accession {accession}."
            digest_payload = {
                "accession": accession,
                "form": form,
                "source": source,
                "report_date": report_date,
                "published_at": published_at.isoformat(),
            }
            digest = hashlib.sha256(
                json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            result.append(IssuerDisclosure(
                self.name, subscription.asset_id, padded_cik, accession, form, title,
                source, summary, published_at, published_at, observed_at, digest,
                tuple(warnings), report_date,
            ))
            if len(result) >= self.limit:
                break
        return tuple(result)


def _at(block: dict[str, Any], key: str, index: int) -> str:
    values = block.get(key) or []
    if not isinstance(values, list) or index >= len(values) or values[index] is None:
        return ""
    return str(values[index]).strip()


def _availability_time(raw_acceptance: str, raw_filing_date: str) -> tuple[datetime, tuple[str, ...]]:
    if raw_acceptance:
        normalized = raw_acceptance.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed, ("acceptance_timezone_assumed_utc",)
        return parsed.astimezone(timezone.utc), ()
    filing_day = date.fromisoformat(raw_filing_date)
    return (
        datetime.combine(filing_day, time(23, 59, 59, 999999), timezone.utc),
        ("availability_time_inferred_from_filing_date_end_of_day",),
    )


def _document_url(cik: str, accession: str, primary_document: str) -> str | None:
    if not primary_document:
        return None
    return f"{_DOC_BASE}/{int(cik)}/{accession.replace('-', '')}/{primary_document}"
