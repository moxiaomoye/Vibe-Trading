"""Deterministic validation boundary for proposed Mispricing Opportunities."""

from __future__ import annotations

from dataclasses import dataclass

from ..assets.models import ThesisExposure
from ..contracts import AttributionCategory, OpportunityStatus, Permanence, ThesisStatus
from ..evidence.models import Evidence, EvidenceSet
from ..mispricing.models import (
    MarketImpliedView,
    MispricingOpportunityVersion,
    PermanenceAssessment,
    PriceMoveAttribution,
)
from ..thesis.models import ThesisVersion


@dataclass(frozen=True, slots=True)
class MispricingProposal:
    thesis_version: ThesisVersion
    exposure: ThesisExposure
    evidence_set: EvidenceSet
    evidence: tuple[Evidence, ...]
    market_implied_view: MarketImpliedView
    attribution: PriceMoveAttribution
    permanence: PermanenceAssessment
    opportunity_version: MispricingOpportunityVersion


class MispricingProposalValidator:
    """Reject inconsistent research proposals before persistence or candidate discovery."""

    def validate(self, proposal: MispricingProposal) -> None:
        proposal.evidence_set.validate_point_in_time(proposal.evidence)
        if proposal.thesis_version.status in {ThesisStatus.INVALIDATED, ThesisStatus.ARCHIVED}:
            raise ValueError("an invalidated or archived thesis cannot support a mispricing proposal")
        if proposal.exposure.thesis_id != proposal.thesis_version.thesis_id:
            raise ValueError("asset exposure does not reference the proposed thesis")
        if proposal.exposure.thesis_version_id != proposal.thesis_version.thesis_version_id:
            raise ValueError("asset exposure is stale relative to the proposed thesis version")
        if proposal.market_implied_view.asset_id != proposal.exposure.asset_id:
            raise ValueError("market-implied view and exposure refer to different assets")
        if proposal.attribution.asset_id != proposal.exposure.asset_id:
            raise ValueError("price attribution and exposure refer to different assets")

        expected_set = proposal.evidence_set.evidence_set_id
        evidence_set_refs = (
            proposal.exposure.evidence_set_id,
            proposal.market_implied_view.evidence_set_id,
            proposal.attribution.evidence_set_id,
            proposal.permanence.evidence_set_id,
            proposal.opportunity_version.evidence_set_id,
        )
        if any(reference != expected_set for reference in evidence_set_refs):
            raise ValueError("all proposal components must use the same point-in-time evidence set")

        known_ids = set(proposal.evidence_set.evidence_ids)
        cited_ids = set(proposal.market_implied_view.evidence_ids)
        cited_ids.update(proposal.permanence.temporary_evidence_ids)
        cited_ids.update(proposal.permanence.structural_evidence_ids)
        cited_ids.update(proposal.opportunity_version.supporting_evidence_ids)
        cited_ids.update(proposal.opportunity_version.counter_evidence_ids)
        for cause in proposal.attribution.causes:
            cited_ids.update(cause.supporting_evidence_ids)
            cited_ids.update(cause.counter_evidence_ids)
        unknown_ids = cited_ids - known_ids
        if unknown_ids:
            raise ValueError(f"mispricing proposal cites evidence outside its evidence set: {sorted(unknown_ids)}")

        if proposal.attribution.is_fully_unknown and proposal.opportunity_version.status != OpportunityStatus.HYPOTHESIS:
            raise ValueError("a fully unknown price move can only remain a hypothesis")
        if proposal.permanence.overall == Permanence.STRUCTURAL and proposal.opportunity_version.status in {
            OpportunityStatus.OPEN,
            OpportunityStatus.STRENGTHENING,
        }:
            raise ValueError("a structurally impaired case cannot be an active mispricing opportunity")
        if all(cause.category == AttributionCategory.UNKNOWN for cause in proposal.attribution.causes):
            if proposal.opportunity_version.confidence >= 0.85:
                raise ValueError("unknown attribution cannot carry very-high confidence")
