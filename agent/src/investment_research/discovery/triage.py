"""Hard-gated discovery triage that minimizes false-positive opportunities."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from ..assets.models import Asset, ThesisExposure
from ..contracts import ThesisStatus
from ..thesis.models import ThesisVersion
from .models import DiscoveryDisposition, FundamentalIntegrity, ResearchLead, ResearchSnapshot


class MispricingDiscoveryTriage:
    def evaluate(
        self,
        asset: Asset,
        thesis: ThesisVersion,
        exposure: ThesisExposure,
        snapshot: ResearchSnapshot,
    ) -> ResearchLead:
        self._validate_consistency(asset, thesis, exposure, snapshot)
        reasons: list[str] = []
        missing: list[str] = list(snapshot.data_gaps)
        disposition = DiscoveryDisposition.REJECTED
        question = "What evidence would overturn this rejection?"

        if not asset.active:
            reasons.append("asset is inactive")
        elif thesis.status in {ThesisStatus.INVALIDATED, ThesisStatus.ARCHIVED, ThesisStatus.DRAFT}:
            reasons.append(f"thesis is {thesis.status.value}, not investable research context")
        elif exposure.exposure_strength < 0.5 or exposure.exposure_purity < 0.4:
            reasons.append("asset exposure to the thesis is not sufficiently established")
        elif snapshot.severe_risk_flags:
            reasons.append("unresolved severe asset-specific risk exists")
            question = f"Have the severe risks been resolved: {', '.join(snapshot.severe_risk_flags)}?"
        elif not self._has_dislocation(snapshot):
            reasons.append("no material price/value dislocation has been observed")
            question = "Has price diverged materially from the relevant value and sector references?"
        elif snapshot.fundamental_integrity == FundamentalIntegrity.DETERIORATING:
            reasons.append("available evidence indicates possible structural fundamental deterioration")
            question = "Is the deterioration temporary, and what primary evidence proves that?"
        elif snapshot.fundamental_integrity == FundamentalIntegrity.UNKNOWN or not snapshot.fundamental_evidence_ids:
            disposition = DiscoveryDisposition.EVIDENCE_GAP
            reasons.append("price dislocation exists but fundamental integrity is not established")
            missing.append("fundamental_integrity_evidence")
            question = "What point-in-time evidence establishes that long-term value remains intact?"
        elif not snapshot.counter_evidence_ids:
            disposition = DiscoveryDisposition.EVIDENCE_GAP
            reasons.append("the candidate lacks an explicit counter-evidence case")
            missing.append("counter_evidence")
            question = "What is the strongest evidence that the market may be right?"
        elif not snapshot.attribution_evidence_ids:
            disposition = DiscoveryDisposition.ATTRIBUTION_REQUIRED
            reasons.append("dislocation and intact fundamentals are visible, but the sell-off cause is unproven")
            missing.append("price_move_attribution")
            question = "Why is the market selling, and is that cause temporary or structural?"
        else:
            disposition = DiscoveryDisposition.OPPORTUNITY_REVIEW
            reasons.extend(("material dislocation observed", "thesis exposure and fundamental integrity have evidence"))
            if thesis.status == ThesisStatus.WEAKENING:
                reasons.append("thesis is weakening, so the opportunity requires heightened review")
            question = "Does the attribution evidence prove temporary mispricing rather than permanent impairment?"

        lead_key = f"lead:{asset.asset_id}:{thesis.thesis_version_id}:{snapshot.snapshot_id}"
        return ResearchLead(
            str(uuid5(NAMESPACE_URL, lead_key)), asset.asset_id, thesis.thesis_version_id,
            snapshot.evidence_set_id, disposition, tuple(reasons), tuple(dict.fromkeys(missing)), question, snapshot.as_of,
        )

    @staticmethod
    def _has_dislocation(snapshot: ResearchSnapshot) -> bool:
        signals = (
            snapshot.drawdown_from_reference is not None and snapshot.drawdown_from_reference <= -0.2,
            snapshot.sector_excess_return is not None and snapshot.sector_excess_return <= -0.1,
            snapshot.valuation_percentile is not None and snapshot.valuation_percentile <= 0.3,
        )
        return sum(signals) >= 2

    @staticmethod
    def _validate_consistency(
        asset: Asset,
        thesis: ThesisVersion,
        exposure: ThesisExposure,
        snapshot: ResearchSnapshot,
    ) -> None:
        if exposure.asset_id != asset.asset_id or snapshot.asset_id != asset.asset_id:
            raise ValueError("discovery asset references are inconsistent")
        if exposure.thesis_version_id != thesis.thesis_version_id or snapshot.thesis_version_id != thesis.thesis_version_id:
            raise ValueError("discovery thesis-version references are inconsistent")
        if exposure.thesis_id != thesis.thesis_id:
            raise ValueError("discovery thesis identity is inconsistent")
        if exposure.as_of > snapshot.as_of or thesis.effective_from > snapshot.as_of:
            raise ValueError("discovery cannot use future thesis exposure or thesis versions")
