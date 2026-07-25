"""Adapter that bridges Phase B provider contracts into the research pipeline.

Each piece of research data carries a provenance tag so the Shadow Report
can distinguish real data from fixture, unavailable, permission-denied,
or blocked-by-documentation sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Sequence

from ..financials.models import FinancialProviderResult, FinancialProviderStatus
from ..financials.protocol import FinancialProviderProtocol
from ..events.models import EventProviderResult, EventProviderStatus
from ..events.protocol import EventProviderProtocol
from ..identity.models import IdentityResult, IdentityProviderStatus
from ..identity.protocol import IdentityProviderProtocol
from ..sectors.models import SectorMembershipResult, SectorProviderStatus
from ..sectors.protocol import SectorMembershipProviderProtocol
from ..valuation.models import FinancialObservation


class Provenance(StrEnum):
    REAL = "real"
    FIXTURE = "fixture"
    UNAVAILABLE = "unavailable"
    PERMISSION_DENIED = "permission_denied"
    BLOCKED_BY_DOCUMENTATION = "blocked_by_documentation"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class ProvenanceLabel:
    category: Provenance
    provider_name: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ResearchProviderContext:
    financial_observations: tuple[FinancialObservation, ...]
    financial_provenance: ProvenanceLabel | None
    event_provenance: ProvenanceLabel | None
    identity_provenance: ProvenanceLabel | None
    sector_provenance: ProvenanceLabel | None
    data_gaps: tuple[str, ...] = field(default_factory=tuple)
    ambiguity_warnings: tuple[str, ...] = field(default_factory=tuple)


def _provenance_from_financial(result: FinancialProviderResult) -> ProvenanceLabel:
    mapping = {
        FinancialProviderStatus.FIXTURE: Provenance.FIXTURE,
        FinancialProviderStatus.UNCONFIGURED: Provenance.UNAVAILABLE,
        FinancialProviderStatus.PERMISSION_DENIED: Provenance.PERMISSION_DENIED,
        FinancialProviderStatus.UPSTREAM_UNAVAILABLE: Provenance.UNAVAILABLE,
        FinancialProviderStatus.MALFORMED_RESPONSE: Provenance.INSUFFICIENT_DATA,
        FinancialProviderStatus.CONFIGURED: Provenance.REAL,
    }
    return ProvenanceLabel(
        category=mapping.get(result.status, Provenance.UNAVAILABLE),
        provider_name="financial",
        detail=result.status.value,
    )


def _provenance_from_event(result: EventProviderResult) -> ProvenanceLabel:
    mapping = {
        EventProviderStatus.FIXTURE: Provenance.FIXTURE,
        EventProviderStatus.UNCONFIGURED: Provenance.UNAVAILABLE,
        EventProviderStatus.PERMISSION_DENIED: Provenance.PERMISSION_DENIED,
        EventProviderStatus.UPSTREAM_UNAVAILABLE: Provenance.UNAVAILABLE,
        EventProviderStatus.MALFORMED_RESPONSE: Provenance.INSUFFICIENT_DATA,
        EventProviderStatus.CONFIGURED: Provenance.REAL,
    }
    return ProvenanceLabel(
        category=mapping.get(result.status, Provenance.UNAVAILABLE),
        provider_name="event",
        detail=result.status.value,
    )


def _provenance_from_identity(result: IdentityResult) -> ProvenanceLabel:
    mapping = {
        IdentityProviderStatus.FIXTURE: Provenance.FIXTURE,
        IdentityProviderStatus.UNCONFIGURED: Provenance.UNAVAILABLE,
        IdentityProviderStatus.PERMISSION_DENIED: Provenance.PERMISSION_DENIED,
        IdentityProviderStatus.UPSTREAM_UNAVAILABLE: Provenance.UNAVAILABLE,
        IdentityProviderStatus.CONFIGURED: Provenance.REAL,
    }
    return ProvenanceLabel(
        category=mapping.get(result.status, Provenance.UNAVAILABLE),
        provider_name="identity",
        detail=result.status.value,
    )


def _provenance_from_sector(result: SectorMembershipResult) -> ProvenanceLabel:
    mapping = {
        SectorProviderStatus.FIXTURE: Provenance.FIXTURE,
        SectorProviderStatus.UNCONFIGURED: Provenance.UNAVAILABLE,
        SectorProviderStatus.UPSTREAM_UNAVAILABLE: Provenance.UNAVAILABLE,
        SectorProviderStatus.MALFORMED_RESPONSE: Provenance.INSUFFICIENT_DATA,
        SectorProviderStatus.CONFIGURED: Provenance.REAL,
    }
    return ProvenanceLabel(
        category=mapping.get(result.status, Provenance.UNAVAILABLE),
        provider_name="sector",
        detail=result.status.value,
    )


class ResearchProviderAdapter:
    """Bridges B1-B4 provider contracts into ResearchProviderContext.

    Does NOT modify any existing FinancialObservation, Candidate threshold,
    quality score, valuation formula, attribution policy, or action level.
    """

    def __init__(
        self,
        financial_provider: FinancialProviderProtocol | None = None,
        event_provider: EventProviderProtocol | None = None,
        identity_provider: IdentityProviderProtocol | None = None,
        sector_provider: SectorMembershipProviderProtocol | None = None,
    ) -> None:
        self._financial = financial_provider
        self._event = event_provider
        self._identity = identity_provider
        self._sector = sector_provider

    def load_context(self, *, as_of: date) -> ResearchProviderContext:
        observations: list[FinancialObservation] = []
        gaps: list[str] = []
        ambiguity: list[str] = []

        financial_prov = None
        event_prov = None
        identity_prov = None
        sector_prov = None

        if self._financial is not None:
            fin_result = self._financial.load(as_of=as_of)
            financial_prov = _provenance_from_financial(fin_result)
            for rec in fin_result.records:
                observations.append(
                    FinancialObservation(
                        asset_id=rec.issuer_id,
                        period_end=rec.report_period,
                        available_at=rec.available_at,
                        source=rec.source,
                        revenue=rec.revenue,
                        net_profit=rec.net_profit,
                        gross_margin=rec.gross_margin,
                        roe=rec.roe,
                        operating_cash_flow=rec.operating_cash_flow,
                        debt_ratio=rec.debt_ratio,
                    )
                )
            gaps.extend(fin_result.data_gaps)
        else:
            financial_prov = ProvenanceLabel(Provenance.UNAVAILABLE, "financial", "no_provider_configured")
            gaps.append("financial_provider_not_configured")

        if self._identity is not None:
            id_result = self._identity.load(as_of=as_of)
            identity_prov = _provenance_from_identity(id_result)
            gaps.extend(id_result.data_gaps)
            ambiguity.extend(id_result.ambiguity_warnings)
        else:
            identity_prov = ProvenanceLabel(Provenance.UNAVAILABLE, "identity", "no_provider_configured")
            gaps.append("identity_provider_not_configured")

        if self._sector is not None:
            sec_result = self._sector.load(as_of=as_of)
            sector_prov = _provenance_from_sector(sec_result)
            gaps.extend(sec_result.data_gaps)
        else:
            sector_prov = ProvenanceLabel(Provenance.UNAVAILABLE, "sector", "no_provider_configured")
            gaps.append("sector_provider_not_configured")

        if self._event is not None:
            ev_result = self._event.load(as_of=as_of)
            event_prov = _provenance_from_event(ev_result)
            gaps.extend(ev_result.data_gaps)
        else:
            event_prov = ProvenanceLabel(Provenance.UNAVAILABLE, "event", "no_provider_configured")
            gaps.append("event_provider_not_configured")

        return ResearchProviderContext(
            financial_observations=tuple(observations),
            financial_provenance=financial_prov,
            event_provenance=event_prov,
            identity_provenance=identity_prov,
            sector_provenance=sector_prov,
            data_gaps=tuple(dict.fromkeys(gaps)),
            ambiguity_warnings=tuple(ambiguity),
        )
