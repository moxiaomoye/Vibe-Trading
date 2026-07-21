from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.application.mispricing import MispricingProposal, MispricingProposalValidator
from src.investment_research.assets.models import Asset, ThesisExposure
from src.investment_research.contracts import (
    AttributionCategory,
    AttributionRole,
    EvidenceDirection,
    AssetType,
    OpportunityStatus,
    Permanence,
    ThesisStatus,
)
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.mispricing.models import (
    MarketImpliedView,
    MispricingOpportunity,
    MispricingOpportunityVersion,
    PermanenceAssessment,
    PriceMoveAttribution,
    PriceMoveCause,
)
from src.investment_research.thesis.models import ThesisVersion


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _evidence(evidence_id: str, direction: EvidenceDirection) -> Evidence:
    return Evidence(
        evidence_id,
        "fixture",
        f"fixture://{evidence_id}",
        evidence_id,
        "Deterministic test evidence.",
        direction,
        NOW,
        NOW,
        NOW,
        f"hash-{evidence_id}",
    )


def _proposal() -> MispricingProposal:
    evidence = (
        _evidence("support", EvidenceDirection.SUPPORTING),
        _evidence("counter", EvidenceDirection.COUNTER),
    )
    evidence_set = EvidenceSet("set", "thesis", NOW, ("support", "counter"), NOW)
    thesis_version = ThesisVersion(
        "thesis-v1",
        "thesis",
        1,
        ThesisStatus.ACTIVE,
        "Long-term infrastructure demand remains intact.",
        0.8,
        "set",
        ("support",),
        ("counter",),
        (),
        ("Demand impairment",),
        "Initial",
        NOW,
        NOW + timedelta(days=30),
    )
    exposure = ThesisExposure("exposure", "asset", "thesis", "thesis-v1", "set", 0.8, 0.7, "Material exposure", NOW)
    market_view = MarketImpliedView(
        "view",
        "asset",
        "set",
        NOW,
        "The market appears to price a durable demand slowdown.",
        ("lower long-term demand",),
        (),
        ("temporary valuation compression",),
        ("consensus is an imperfect proxy",),
        ("support",),
        0.7,
    )
    cause = PriceMoveCause(
        AttributionCategory.VALUATION,
        AttributionRole.TRIGGER,
        Permanence.TEMPORARY,
        "Broad valuation compression without matching fundamental evidence.",
        0.7,
        0.75,
        ("support",),
        ("counter",),
        ("expectations may have deteriorated",),
        "next primary-source financial update",
    )
    attribution = PriceMoveAttribution("attribution", "asset", "set", NOW - timedelta(days=5), NOW, (cause,), NOW)
    permanence = PermanenceAssessment(
        "permanence",
        "set",
        Permanence.TEMPORARY,
        "Current evidence points to a reversible valuation effect.",
        ("support",),
        (),
        ("whether expectations have structurally changed",),
        0.72,
        NOW,
    )
    opportunity = MispricingOpportunityVersion(
        "opportunity-v1",
        "opportunity",
        1,
        OpportunityStatus.OPEN,
        "thesis-v1",
        "exposure",
        "view",
        "attribution",
        "permanence",
        "set",
        "Long-term demand may be more durable than the price-implied view.",
        "The market discounts structural weakness while research evidence currently supports a temporary mechanism.",
        "A large price-expectation gap has emerged during broad compression.",
        ("support",),
        ("counter",),
        ("expectations may be deteriorating",),
        ("true market expectations remain estimated",),
        ("new primary-source evidence narrows the expectation gap",),
        "Is the apparent valuation compression actually an early fundamental signal?",
        ("Demand impairment",),
        0.76,
        "Initial hypothesis promoted after two-sided review.",
        NOW,
        NOW + timedelta(days=7),
    )
    return MispricingProposal(thesis_version, exposure, evidence_set, evidence, market_view, attribution, permanence, opportunity)


def test_complete_two_sided_mispricing_proposal_is_valid() -> None:
    MispricingProposalValidator().validate(_proposal())


def test_fully_unknown_attribution_must_remain_a_hypothesis() -> None:
    proposal = _proposal()
    unknown_cause = PriceMoveCause(
        AttributionCategory.UNKNOWN,
        AttributionRole.TRIGGER,
        Permanence.UNCERTAIN,
        "Public evidence does not explain the move.",
        1.0,
        0.4,
        (),
        (),
        ("undisclosed event",),
        "next company disclosure",
    )
    unknown_attribution = replace(proposal.attribution, causes=(unknown_cause,))

    with pytest.raises(ValueError, match="only remain a hypothesis"):
        MispricingProposalValidator().validate(replace(proposal, attribution=unknown_attribution))


def test_unknown_attribution_cannot_carry_very_high_confidence() -> None:
    proposal = _proposal()
    unknown_cause = PriceMoveCause(
        AttributionCategory.UNKNOWN,
        AttributionRole.TRIGGER,
        Permanence.UNCERTAIN,
        "Cause unknown.",
        1.0,
        0.3,
        (),
        (),
        (),
        "next disclosure",
    )
    unknown_attribution = replace(proposal.attribution, causes=(unknown_cause,))
    hypothesis = replace(proposal.opportunity_version, status=OpportunityStatus.HYPOTHESIS, confidence=0.9)

    with pytest.raises(ValueError, match="unknown attribution"):
        MispricingProposalValidator().validate(replace(proposal, attribution=unknown_attribution, opportunity_version=hypothesis))


def test_structural_impairment_cannot_be_an_active_opportunity() -> None:
    proposal = _proposal()
    structural = PermanenceAssessment(
        "structural",
        "set",
        Permanence.STRUCTURAL,
        "Evidence points to durable impairment.",
        (),
        ("counter",),
        (),
        0.8,
        NOW,
    )

    with pytest.raises(ValueError, match="structurally impaired"):
        MispricingProposalValidator().validate(replace(proposal, permanence=structural))


def test_proposal_rejects_evidence_outside_point_in_time_set() -> None:
    proposal = _proposal()
    market_view = replace(proposal.market_implied_view, evidence_ids=("invented",))

    with pytest.raises(ValueError, match="outside its evidence set"):
        MispricingProposalValidator().validate(replace(proposal, market_implied_view=market_view))


def test_invalidated_thesis_cannot_support_mispricing() -> None:
    proposal = _proposal()
    thesis = replace(proposal.thesis_version, status=ThesisStatus.INVALIDATED)

    with pytest.raises(ValueError, match="invalidated or archived"):
        MispricingProposalValidator().validate(replace(proposal, thesis_version=thesis))


def test_asset_and_exposure_boundaries() -> None:
    asset = Asset("asset", "TEST", "Test", AssetType.ETF, "US", "USD", NOW)
    exposure = _proposal().exposure
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(asset, created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="must not be empty"):
        replace(asset, symbol=" ")
    with pytest.raises(ValueError, match="identity and evidence"):
        replace(exposure, exposure_id="")
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(exposure, exposure_strength=1.1)
    with pytest.raises(ValueError, match="rationale"):
        replace(exposure, rationale=" ")


def test_market_view_and_attribution_boundaries() -> None:
    proposal = _proposal()
    view = proposal.market_implied_view
    cause = proposal.attribution.causes[0]
    attribution = proposal.attribution
    with pytest.raises(ValueError, match="identity and evidence"):
        replace(view, view_id="")
    with pytest.raises(ValueError, match="narrative"):
        replace(view, narrative="")
    with pytest.raises(ValueError, match="must cite evidence"):
        replace(view, evidence_ids=())
    with pytest.raises(ValueError, match="relative importance"):
        replace(cause, relative_importance=1.1)
    with pytest.raises(ValueError, match="description"):
        replace(cause, description="")
    with pytest.raises(ValueError, match="support and oppose"):
        replace(cause, counter_evidence_ids=("support",))
    with pytest.raises(ValueError, match="must cite supporting"):
        replace(cause, supporting_evidence_ids=())
    with pytest.raises(ValueError, match="must remain uncertain"):
        replace(cause, category=AttributionCategory.UNKNOWN, permanence=Permanence.TEMPORARY)
    with pytest.raises(ValueError, match="cannot precede"):
        replace(attribution, window_end=attribution.window_start - timedelta(seconds=1))
    with pytest.raises(ValueError, match="identity and evidence"):
        replace(attribution, attribution_id="")
    with pytest.raises(ValueError, match="at least one cause"):
        replace(attribution, causes=())
    with pytest.raises(ValueError, match="identify a trigger"):
        replace(attribution, causes=(replace(cause, role=AttributionRole.BACKGROUND),))


def test_permanence_and_opportunity_boundaries() -> None:
    proposal = _proposal()
    permanence = proposal.permanence
    version = proposal.opportunity_version
    identity = MispricingOpportunity("opportunity", "thesis", "asset", "dedupe", NOW)
    with pytest.raises(ValueError, match="identity and rationale"):
        replace(permanence, assessment_id="")
    with pytest.raises(ValueError, match="unresolved questions"):
        replace(permanence, overall=Permanence.UNCERTAIN, unresolved_questions=())
    with pytest.raises(ValueError, match="temporary evidence"):
        replace(permanence, temporary_evidence_ids=())
    with pytest.raises(ValueError, match="structural evidence"):
        replace(permanence, overall=Permanence.STRUCTURAL, temporary_evidence_ids=(), structural_evidence_ids=())
    with pytest.raises(ValueError, match="opportunity identity"):
        replace(identity, dedupe_key="")
    with pytest.raises(ValueError, match="positive"):
        replace(version, version_number=0)
    with pytest.raises(ValueError, match="references"):
        replace(version, exposure_id="")
    with pytest.raises(ValueError, match="cannot precede"):
        replace(version, next_review_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="support and oppose"):
        replace(version, counter_evidence_ids=("support",))
    with pytest.raises(ValueError, match="complete two-sided"):
        replace(version, variant_wedge="")


def test_proposal_components_must_share_identity_and_evidence_context() -> None:
    proposal = _proposal()
    validator = MispricingProposalValidator()
    with pytest.raises(ValueError, match="does not reference"):
        validator.validate(replace(proposal, exposure=replace(proposal.exposure, thesis_id="other")))
    with pytest.raises(ValueError, match="stale"):
        validator.validate(replace(proposal, exposure=replace(proposal.exposure, thesis_version_id="old")))
    with pytest.raises(ValueError, match="different assets"):
        validator.validate(replace(proposal, market_implied_view=replace(proposal.market_implied_view, asset_id="other")))
    with pytest.raises(ValueError, match="different assets"):
        validator.validate(replace(proposal, attribution=replace(proposal.attribution, asset_id="other")))
    with pytest.raises(ValueError, match="same point-in-time"):
        validator.validate(replace(proposal, permanence=replace(proposal.permanence, evidence_set_id="other")))
