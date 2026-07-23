from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.investment_research.application.panic_research_pipeline import (
    PanicMispricingResearchPipeline,
    ResearchCase,
    ResearchPipelinePolicy,
)
from src.investment_research.assets.models import Asset, ThesisExposure
from src.investment_research.contracts import (
    ActionLevel,
    AssetType,
    EvidenceDirection,
    MarketRegime,
    Permanence,
    ThesisStatus,
)
from src.investment_research.discovery.models import DiscoveryDisposition, ResearchLead
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.market.models import MarketState
from src.investment_research.mispricing.attribution import (
    AttributionPolicy,
    DateSafeAttributionEngine,
    PriceMoveContext,
)
from src.investment_research.mispricing.models import PermanenceAssessment
from src.investment_research.thesis.models import ThesisVersion
from src.investment_research.valuation import (
    AssumptionStatus,
    CompanyQualityEngine,
    FinancialObservation,
    ScenarioAssumption,
    ScenarioValuationEngine,
    ValuationAssumptions,
    ValuationMethod,
)


NOW = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)
EVIDENCE_SET_ID = "evidence-set-fixture"
ASSET_ID = "asset-fixture"


def _evidence(evidence_id, direction):
    """Point-in-time evidence fixture with stable hash and timestamps."""
    return Evidence(
        evidence_id=evidence_id,
        provider="fixture",
        source_locator=f"fixture://{evidence_id}",
        title=evidence_id,
        summary="fixture point-in-time evidence",
        direction=direction,
        published_at=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=1),
        observed_at=NOW,
        content_hash=f"hash-{evidence_id}",
    )


def _pipeline_inputs():
    """Complete set of point-in-time fixtures for a panic research pipeline run."""
    evidence = (
        _evidence("support", EvidenceDirection.SUPPORTING),
        _evidence("counter", EvidenceDirection.COUNTER),
        _evidence("market-price", EvidenceDirection.NEUTRAL),
    )
    evidence_set = EvidenceSet(
        EVIDENCE_SET_ID,
        "thesis-ai",
        NOW,
        tuple(item.evidence_id for item in evidence),
        NOW,
    )
    asset = Asset(ASSET_ID, "600522.SH", "fixture", AssetType.STOCK, "CN", "CNY", NOW)
    thesis = ThesisVersion(
        thesis_version_id="thesis-ai-v3",
        thesis_id="thesis-ai",
        version_number=3,
        status=ThesisStatus.ACTIVE,
        core_claim="fixture thesis remains intact",
        confidence=0.92,
        evidence_set_id=EVIDENCE_SET_ID,
        supporting_evidence_ids=("support",),
        counter_evidence_ids=("counter",),
        catalysts=("fixture catalyst",),
        kill_criteria=("fixture thesis invalidated",),
        change_summary="fixture",
        effective_from=NOW - timedelta(days=30),
        next_review_at=NOW + timedelta(days=30),
    )
    exposure = ThesisExposure(
        "exposure-1",
        ASSET_ID,
        "thesis-ai",
        thesis.thesis_version_id,
        EVIDENCE_SET_ID,
        0.9,
        0.8,
        "fixture exposure",
        NOW - timedelta(days=1),
    )
    market_state = MarketState(
        "market-state-1",
        MarketRegime.PANIC,
        EVIDENCE_SET_ID,
        ("fixture panic",),
        (),
        0.9,
        NOW,
    )
    lead = ResearchLead(
        "lead-1",
        ASSET_ID,
        thesis.thesis_version_id,
        EVIDENCE_SET_ID,
        DiscoveryDisposition.OPPORTUNITY_REVIEW,
        ("material dislocation",),
        (),
        "Could the market be correctly pricing structural impairment?",
        NOW,
    )
    observations = (
        FinancialObservation(
            ASSET_ID,
            date(2023, 12, 31),
            datetime(2024, 3, 31, tzinfo=timezone.utc),
            "fixture",
            Decimal("100"),
            Decimal("10"),
            Decimal("0.40"),
            Decimal("0.15"),
            Decimal("11"),
            Decimal("0.25"),
        ),
        FinancialObservation(
            ASSET_ID,
            date(2024, 12, 31),
            datetime(2025, 3, 31, tzinfo=timezone.utc),
            "fixture",
            Decimal("120"),
            Decimal("12"),
            Decimal("0.42"),
            Decimal("0.16"),
            Decimal("13"),
            Decimal("0.23"),
        ),
    )
    quality = CompanyQualityEngine().assess(
        asset_id=ASSET_ID,
        observations=observations,
        information_cutoff=NOW,
    )
    assumptions = ValuationAssumptions(
        ASSET_ID,
        Decimal("100"),
        Decimal("5"),
        2,
        ValuationMethod.FORWARD_PE,
        (
            ScenarioAssumption("bear", Decimal("-0.05"), Decimal("14")),
            ScenarioAssumption("base", Decimal("0.15"), Decimal("20")),
            ScenarioAssumption("bull", Decimal("0.25"), Decimal("26")),
        ),
        NOW.date(),
        NOW,
        "approved-fixture-v1",
        ("earnings assumption invalidated",),
        AssumptionStatus.APPROVED,
        "fixture-approval",
    )
    valuation = ScenarioValuationEngine().evaluate(
        asset_id=ASSET_ID,
        information_cutoff=NOW,
        assumptions=assumptions,
    )
    price_context = PriceMoveContext(
        ASSET_ID,
        "semiconductor",
        NOW - timedelta(days=2),
        NOW,
        -0.10,
        -0.09,
        -0.08,
        "market-price",
        "market-price",
        "market-price",
    )
    attribution = DateSafeAttributionEngine().evaluate(
        context=price_context,
        events=(),
        information_cutoff=NOW,
        policy=AttributionPolicy("attribution-v1", 0.02, 0.02, 0.65),
    )
    permanence = PermanenceAssessment(
        "permanence-1",
        EVIDENCE_SET_ID,
        Permanence.TEMPORARY,
        "fixture evidence supports a temporary dislocation",
        ("support",),
        (),
        (),
        0.90,
        NOW,
    )
    research_case = ResearchCase(
        research_view="market price may overdiscount a temporary slowdown",
        variant_wedge="long-term earnings evidence differs from the implied view",
        why_now="broad panic created a material valuation gap",
        implied_expectations=("persistent earnings decline",),
        priced_positives=("current balance-sheet resilience",),
        possible_overdiscounted_negatives=("temporary demand slowdown",),
        supporting_evidence_ids=("support", "market-price"),
        counter_evidence_ids=("counter",),
        alternative_explanations=("the slowdown may be structural",),
        unknowns=("next-quarter demand",),
        convergence_paths=("next primary filing",),
        catalysts=("demand stabilization",),
        invalidation_conditions=("structural earnings impairment",),
        first_rejection_question="Is the slowdown structural rather than temporary?",
        confidence=0.91,
        next_review_at=NOW + timedelta(days=14),
    )
    policy = ResearchPipelinePolicy("pipeline-v1", 0.10, 0.85, 0.5, 0.4, 0.49)
    return {
        "asset": asset,
        "thesis": thesis,
        "exposure": exposure,
        "market_state": market_state,
        "discovery_lead": lead,
        "evidence_set": evidence_set,
        "evidence": evidence,
        "quality": quality,
        "valuation": valuation,
        "attribution": attribution,
        "permanence": permanence,
        "research_case": research_case,
        "policy": policy,
        "evaluated_at": NOW,
    }


def test_complete_case_builds_existing_opportunity_candidate_and_action_assessment():
    result = PanicMispricingResearchPipeline().run(**_pipeline_inputs())
    assert result.candidate is not None
    assert result.assessment is not None
    assert result.assessment.action_level == ActionLevel.ACTION_CANDIDATE
    assert result.opportunity_version.status.value == "open"
    assert result.scenario_value_range is not None
    assert result.policy_version == "pipeline-v1"
    assert result.blocked_reasons == ()


def test_severe_quality_gap_caps_confidence_and_action_level():
    inputs = _pipeline_inputs()
    inputs["quality"] = CompanyQualityEngine().assess(
        asset_id=ASSET_ID,
        observations=(),
        information_cutoff=NOW,
    )
    result = PanicMispricingResearchPipeline().run(**inputs)
    assert result.assessment.action_level == ActionLevel.WATCH
    assert result.assessment.confidence <= inputs["policy"].severe_gap_confidence_cap
    assert "quality_unconfigured" in result.blocked_reasons


def test_structural_company_issue_prevents_active_opportunity():
    inputs = _pipeline_inputs()
    inputs["permanence"] = PermanenceAssessment(
        "permanence-structural",
        EVIDENCE_SET_ID,
        Permanence.STRUCTURAL,
        "fixture counter-evidence indicates permanent impairment",
        (),
        ("counter",),
        (),
        0.9,
        NOW,
    )
    result = PanicMispricingResearchPipeline().run(**inputs)
    assert result.opportunity_version.status.value == "hypothesis"
    assert result.assessment.action_level == ActionLevel.WATCH
    assert "temporary_cause_not_established" in result.blocked_reasons


def test_rejected_discovery_lead_creates_no_candidate():
    inputs = _pipeline_inputs()
    inputs["discovery_lead"] = replace(
        inputs["discovery_lead"],
        disposition=DiscoveryDisposition.REJECTED,
    )
    result = PanicMispricingResearchPipeline().run(**inputs)
    assert result.candidate is None
    assert result.assessment is None
    assert "discovery_rejected" in result.blocked_reasons


def test_weak_thesis_exposure_cannot_become_active_opportunity():
    inputs = _pipeline_inputs()
    inputs["exposure"] = replace(inputs["exposure"], exposure_strength=0.2)
    result = PanicMispricingResearchPipeline().run(**inputs)
    assert result.opportunity_version.status.value == "hypothesis"
    assert result.assessment.action_level == ActionLevel.WATCH
    assert "thesis_exposure_strength" in result.blocked_reasons


def test_future_evidence_is_rejected():
    inputs = _pipeline_inputs()
    future = replace(
        inputs["evidence"][0],
        available_at=NOW + timedelta(minutes=1),
        observed_at=NOW + timedelta(minutes=1),
    )
    inputs["evidence"] = (future, *inputs["evidence"][1:])
    with pytest.raises(ValueError, match="future|unavailable"):
        PanicMispricingResearchPipeline().run(**inputs)


def test_pipeline_is_deterministic():
    inputs = _pipeline_inputs()
    first = PanicMispricingResearchPipeline().run(**inputs)
    second = PanicMispricingResearchPipeline().run(**inputs)
    assert first == second
