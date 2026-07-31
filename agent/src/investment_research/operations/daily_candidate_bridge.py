"""Map a daily watchlist snapshot into the canonical research-candidate pipeline.

The bridge is deliberately conservative.  Automatically collected observations
may create a draft research case, but they do not initialize an active Thesis or
prove that a temporary mispricing exists.  Missing primary evidence therefore
keeps the formal Action Level at ``watch``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from ..application.panic_research_pipeline import (
    PanicMispricingResearchPipeline,
    ResearchCase,
    ResearchPipelinePolicy,
)
from ..assets.models import Asset, ThesisExposure
from ..contracts import (
    AssetType,
    EvidenceDirection,
    MarketRegime,
    Permanence,
    ThesisStatus,
)
from ..discovery.models import DiscoveryDisposition, ResearchLead
from ..evidence.models import Evidence, EvidenceSet
from ..market.models import MarketState
from ..mispricing.attribution import (
    AttributionPolicy,
    AttributionScope,
    DateSafeAttributionEngine,
    PriceMoveContext,
)
from ..mispricing.models import PermanenceAssessment
from ..thesis.models import ThesisVersion
from ..valuation import (
    AssumptionStatus,
    CompanyQualityEngine,
    FinancialObservation,
    ScenarioAssumption,
    ScenarioValuationEngine,
    ValuationAssumptions,
    ValuationMethod,
)
from .reviewed_context import ReviewedResearchContextResolution


BRIDGE_VERSION = "daily-candidate-bridge-v1"
PIPELINE_POLICY = ResearchPipelinePolicy(
    "pipeline-v1",
    minimum_base_upside=0.10,
    action_candidate_confidence=0.85,
    minimum_exposure_strength=0.50,
    minimum_exposure_purity=0.40,
    severe_gap_confidence_cap=0.49,
)
ATTRIBUTION_POLICY = AttributionPolicy("attribution-v1", 0.02, 0.02, 0.65)


def evaluate_daily_candidate(
    *,
    definition: dict[str, Any],
    asset_report: dict[str, Any],
    market_report: dict[str, Any],
    report_date: date,
    reviewed_context: ReviewedResearchContextResolution | None = None,
) -> dict[str, Any]:
    """Return the JSON-safe canonical Candidate decision for one daily asset."""
    cutoff = _market_close(report_date)
    symbol = str(definition["symbol"])
    asset_id = f"asset:{symbol}"
    thesis_id = str(definition.get("thesis_id") or f"thesis:{symbol}")
    thesis_version_id = f"{thesis_id}:draft-v1"
    payload_hash = _hash(
        {
            "symbol": symbol,
            "report_date": report_date.isoformat(),
            "asset": asset_report,
            "market": market_report,
            "bridge_version": BRIDGE_VERSION,
        }
    )
    evidence_set_id = _id("daily-evidence-set", payload_hash)
    price_evidence_id = _id("daily-price-evidence", payload_hash)
    governance_evidence_id = _id("daily-governance-evidence", payload_hash)

    price_evidence = Evidence(
        evidence_id=price_evidence_id,
        provider=str(asset_report.get("data_source") or "vibe_market_loader_auto"),
        source_locator=f"vibe://daily-opportunity/{report_date.isoformat()}/{symbol}",
        title=f"{symbol} point-in-time price and market observation",
        summary=_evidence_summary(asset_report, market_report),
        direction=EvidenceDirection.SUPPORTING,
        published_at=cutoff,
        available_at=cutoff,
        observed_at=cutoff,
        content_hash=_hash({"kind": "price", "payload_hash": payload_hash}),
        quality_warnings=tuple(_asset_gaps(asset_report)),
    )
    governance_evidence = Evidence(
        evidence_id=governance_evidence_id,
        provider="investment-research-governance",
        source_locator="policy://automatic-evidence-requires-human-review",
        title="Automatic observations have not initialized an approved Thesis",
        summary=(
            "The daily snapshot is automatically collected and remains unreviewed. "
            "It may prioritize research but cannot establish Thesis integrity, "
            "temporary impairment, or a formal mispricing conclusion."
        ),
        direction=EvidenceDirection.COUNTER,
        published_at=cutoff,
        available_at=cutoff,
        observed_at=cutoff,
        content_hash=_hash({"kind": "governance", "version": BRIDGE_VERSION}),
        quality_warnings=("human Thesis review required",),
    )
    asset = Asset(
        asset_id,
        symbol,
        str(definition["name"]),
        AssetType(str(definition["asset_type"])),
        "CN",
        "CNY",
        cutoff,
    )
    resolved = reviewed_context.context if reviewed_context else None
    context_gaps = list(reviewed_context.gaps) if reviewed_context else []
    if resolved is None:
        evidence = (price_evidence, governance_evidence)
        evidence_set = EvidenceSet(
            evidence_set_id,
            thesis_id,
            cutoff,
            tuple(item.evidence_id for item in evidence),
            cutoff,
        )
        thesis = ThesisVersion(
            thesis_version_id=thesis_version_id,
            thesis_id=thesis_id,
            version_number=1,
            status=ThesisStatus.DRAFT,
            core_claim=f"{definition['name']} may express a durable investment Thesis",
            confidence=0.35,
            evidence_set_id=evidence_set_id,
            supporting_evidence_ids=(price_evidence_id,),
            counter_evidence_ids=(governance_evidence_id,),
            catalysts=("human review of primary filings and Thesis evidence",),
            kill_criteria=("primary evidence shows structural Thesis impairment",),
            change_summary="automatic daily observation; Thesis remains uninitialized",
            effective_from=cutoff,
            next_review_at=cutoff + timedelta(days=7),
        )
        thesis_initialized = False
    else:
        thesis = resolved.thesis
        thesis_id = thesis.thesis_id
        thesis_version_id = thesis.thesis_version_id
        evidence_set = resolved.evidence_set
        evidence_set_id = evidence_set.evidence_set_id
        evidence = resolved.evidence
        thesis_initialized = True
    exposure = ThesisExposure(
        _id("daily-exposure", payload_hash),
        asset_id,
        thesis_id,
        thesis_version_id,
        evidence_set_id,
        0.50,
        0.40,
        (
            "watchlist-to-Thesis mapping; asset exposure still requires a "
            "separate reviewed exposure record"
            if thesis_initialized
            else "provisional watchlist-to-Thesis mapping pending human evidence review"
        ),
        cutoff,
    )
    market_state = _market_state(market_report, evidence_set_id, cutoff, payload_hash)
    discovery = ResearchLead(
        _id("daily-lead", payload_hash),
        asset_id,
        thesis_version_id,
        evidence_set_id,
        (
            DiscoveryDisposition.ATTRIBUTION_REQUIRED
            if asset_report.get("panic")
            else DiscoveryDisposition.EVIDENCE_GAP
        ),
        (
            ("panic or dislocation observation requires formal attribution",)
            if asset_report.get("panic")
            else ("no configured panic condition; retain on the research watchlist",)
        ),
        (
            ("reviewed asset-to-Thesis exposure", "reviewed price-move attribution")
            if thesis_initialized
            else ("accepted primary issuer evidence", "reviewed Thesis version")
        ),
        "Is the observed weakness explained by structural impairment rather than temporary dislocation?",
        cutoff,
    )

    quality = CompanyQualityEngine().assess(
        asset_id=asset_id,
        observations=_financial_observations(asset_id, asset_report, cutoff),
        information_cutoff=cutoff,
    )
    valuation = ScenarioValuationEngine().evaluate(
        asset_id=asset_id,
        information_cutoff=cutoff,
        assumptions=_valuation_assumptions(asset_id, definition, asset_report, cutoff),
    )
    attribution = DateSafeAttributionEngine().evaluate(
        context=PriceMoveContext(
            asset_id=asset_id,
            sector=_primary_sector(asset_report),
            window_start=cutoff - timedelta(days=90),
            window_end=cutoff,
            asset_return=_ratio(asset_report.get("return_60d_pct")),
            market_return=_ratio(market_report.get("shanghai_60d_return_pct")),
            sector_return=None,
            asset_evidence_id=price_evidence_id,
            market_evidence_id=price_evidence_id,
            sector_evidence_id=None,
            data_gaps=("point-in-time sector return unavailable",),
        ),
        events=(),
        information_cutoff=cutoff,
        policy=ATTRIBUTION_POLICY,
    )
    permanence = PermanenceAssessment(
        _id("daily-permanence", payload_hash),
        evidence_set_id,
        Permanence.UNCERTAIN,
        "Automatic price observations do not prove whether the impairment is temporary or structural.",
        (),
        (),
        ("review primary issuer disclosures", "verify company-specific adverse events"),
        0.35,
        cutoff,
    )
    research_case = ResearchCase(
        research_view="The observed price dislocation may warrant research, but mispricing is not established.",
        variant_wedge="Price weakness is observable; long-term value and permanence remain unverified.",
        why_now="The configured watchlist or panic rules surfaced this asset for triage.",
        implied_expectations=("the market may be discounting weaker future fundamentals",),
        priced_positives=(
            ("reviewed Thesis evidence is available; asset-specific attribution remains separate",)
            if thesis_initialized
            else ("no positive is treated as established without reviewed evidence",)
        ),
        possible_overdiscounted_negatives=("broad panic or temporary risk aversion",),
        supporting_evidence_ids=thesis.supporting_evidence_ids,
        counter_evidence_ids=thesis.counter_evidence_ids,
        alternative_explanations=("the decline may reflect structural company or industry impairment",),
        unknowns=("primary filing evidence", "company-specific event attribution"),
        convergence_paths=("human review of primary filings and official announcements",),
        catalysts=thesis.catalysts,
        invalidation_conditions=thesis.kill_criteria,
        first_rejection_question=discovery.first_rejection_question,
        confidence=thesis.confidence if thesis_initialized else 0.35,
        next_review_at=cutoff + timedelta(days=7),
    )

    result = PanicMispricingResearchPipeline().run(
        asset=asset,
        thesis=thesis,
        exposure=exposure,
        market_state=market_state,
        discovery_lead=discovery,
        evidence_set=evidence_set,
        evidence=evidence,
        quality=quality,
        valuation=valuation,
        attribution=attribution,
        permanence=permanence,
        research_case=research_case,
        policy=PIPELINE_POLICY,
        evaluated_at=cutoff,
    )
    assessment = result.assessment
    return {
        "bridge_version": BRIDGE_VERSION,
        "candidate_id": result.candidate.candidate_id if result.candidate else None,
        "opportunity_status": result.opportunity_version.status.value,
        "action_level": assessment.action_level.value if assessment else "watch",
        "research_priority": assessment.research_priority.value if assessment else "low",
        "confidence": assessment.confidence if assessment else 0.0,
        "thesis_status": thesis.status.value,
        "thesis_initialized": thesis_initialized,
        "thesis_version_id": thesis.thesis_version_id,
        "thesis_core_claim": thesis.core_claim,
        "thesis_confidence": thesis.confidence,
        "evidence_complete": assessment.evidence_complete if assessment else False,
        "mispricing_significant": assessment.mispricing_significant if assessment else False,
        "attribution_scope": result.attribution.scope.value,
        "permanence": result.permanence.overall.value,
        "quality_status": result.quality.status.value,
        "valuation_status": result.valuation.status.value,
        "scenario_value_range": result.scenario_value_range,
        "blocked_reasons": list(result.blocked_reasons),
        "data_coverage": list(result.data_coverage),
        "data_gaps": list(dict.fromkeys([*result.data_gaps, *context_gaps])),
        "policy_version": result.policy_version,
        "first_rejection_question": (
            assessment.first_rejection_question if assessment else discovery.first_rejection_question
        ),
        "next_review_at": research_case.next_review_at.isoformat(),
        "supporting_evidence": [
            _serialize_evidence(item, EvidenceDirection.SUPPORTING)
            for item in evidence
            if item.evidence_id in set(thesis.supporting_evidence_ids)
        ],
        "counter_evidence": [
            _serialize_evidence(item, EvidenceDirection.COUNTER)
            for item in evidence
            if item.evidence_id in set(thesis.counter_evidence_ids)
        ],
        "automatic_observation": _serialize_evidence(price_evidence),
        "invalidation_conditions": list(result.invalidation_conditions),
        "decision_source": "PanicMispricingResearchPipeline",
    }


def _market_state(
    market: dict[str, Any],
    evidence_set_id: str,
    cutoff: datetime,
    payload_hash: str,
) -> MarketState:
    triggers = tuple(str(item.get("label") or item.get("code")) for item in market.get("panic_triggers", ()))
    gaps: list[str] = []
    if triggers:
        regime = MarketRegime.PANIC
        drivers = triggers
        confidence = 0.70
    elif market.get("shanghai_20d_return_pct") is None:
        regime = MarketRegime.UNKNOWN
        drivers = ()
        gaps.append("Shanghai 20-day return unavailable")
        confidence = 0.0
    elif float(market["shanghai_20d_return_pct"]) <= -5.0:
        regime = MarketRegime.CORRECTION
        drivers = ("Shanghai Composite 20-day return is below -5%",)
        confidence = 0.60
    else:
        regime = MarketRegime.NORMAL
        drivers = ("configured panic conditions are not met",)
        confidence = 0.60
    return MarketState(
        _id("daily-market-state", payload_hash),
        regime,
        evidence_set_id,
        drivers,
        tuple(gaps),
        confidence,
        cutoff,
    )


def _financial_observations(
    asset_id: str,
    asset_report: dict[str, Any],
    cutoff: datetime,
) -> tuple[FinancialObservation, ...]:
    financials = asset_report.get("fundamentals")
    if not isinstance(financials, dict):
        return ()
    period_end = _date(financials.get("period_end"))
    if period_end is None or period_end > cutoff.date():
        return ()
    available_date = _date(financials.get("notice_date")) or cutoff.date()
    if available_date > cutoff.date():
        return ()
    available_at = datetime.combine(available_date, time(16), ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
    return (
        FinancialObservation(
            asset_id=asset_id,
            period_end=period_end,
            available_at=available_at,
            source=str(financials.get("source") or "vibe_financial_tool"),
            revenue=_decimal(financials.get("revenue_cny")),
            net_profit=_decimal(financials.get("net_profit_cny")),
            gross_margin=_percent_decimal(financials.get("gross_margin_pct")),
            roe=_percent_decimal(financials.get("roe_pct")),
            operating_cash_flow=None,
            debt_ratio=_percent_decimal(financials.get("debt_ratio_pct")),
        ),
    )


def _valuation_assumptions(
    asset_id: str,
    definition: dict[str, Any],
    asset_report: dict[str, Any],
    cutoff: datetime,
) -> ValuationAssumptions | None:
    configured = definition.get("valuation")
    financials = asset_report.get("fundamentals")
    price = _decimal(asset_report.get("latest_close"))
    eps = _decimal(financials.get("eps")) if isinstance(financials, dict) else None
    if not isinstance(configured, dict) or price is None or eps is None or price <= 0 or eps <= 0:
        return None
    return ValuationAssumptions(
        asset_id=asset_id,
        current_price=price,
        current_eps=eps,
        horizon_years=1,
        method=ValuationMethod.FORWARD_PE,
        scenarios=(
            ScenarioAssumption("bear", Decimal("0"), Decimal(str(configured["bear_pe"]))),
            ScenarioAssumption("base", Decimal("0"), Decimal(str(configured["base_pe"]))),
            ScenarioAssumption("bull", Decimal("0"), Decimal(str(configured["bull_pe"]))),
        ),
        assumption_date=cutoff.date(),
        available_at=cutoff,
        assumption_version=f"{BRIDGE_VERSION}:{definition['symbol']}:provisional-static-pe",
        invalidation_conditions=("EPS or approved scenario assumptions materially change",),
        status=AssumptionStatus.PROVISIONAL,
    )


def _serialize_evidence(
    item: Evidence, direction: EvidenceDirection | None = None
) -> dict[str, Any]:
    return {
        "evidence_id": item.evidence_id,
        "provider": item.provider,
        "source_locator": item.source_locator,
        "title": item.title,
        "summary": item.summary,
        "direction": (direction or item.direction).value,
        "published_at": item.published_at.isoformat(),
        "available_at": item.available_at.isoformat(),
        "quality_warnings": list(item.quality_warnings),
    }


def _evidence_summary(asset: dict[str, Any], market: dict[str, Any]) -> str:
    return json.dumps(
        {
            "symbol": asset.get("symbol"),
            "effective_trade_date": asset.get("effective_trade_date"),
            "latest_close": asset.get("latest_close"),
            "return_60d_pct": asset.get("return_60d_pct"),
            "panic_triggers": asset.get("panic_triggers", []),
            "market_regime": market.get("regime"),
            "shanghai_60d_return_pct": market.get("shanghai_60d_return_pct"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _asset_gaps(asset: dict[str, Any]) -> list[str]:
    gaps = []
    if asset.get("fundamentals") is None:
        gaps.append("primary issuer financial evidence unavailable")
    if not asset.get("news"):
        gaps.append("company event evidence unavailable")
    if not asset.get("sectors"):
        gaps.append("sector membership or return evidence unavailable")
    return gaps


def _primary_sector(asset: dict[str, Any]) -> str | None:
    sectors = asset.get("sectors")
    if not isinstance(sectors, list) or not sectors:
        return None
    name = sectors[0].get("name") if isinstance(sectors[0], dict) else None
    return str(name) if name else None


def _market_close(value: date) -> datetime:
    return datetime.combine(value, time(16), ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)


def _ratio(value: Any) -> float | None:
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _percent_decimal(value: Any) -> Decimal | None:
    parsed = _decimal(value)
    return parsed / Decimal("100") if parsed is not None else None


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _id(kind: str, identity: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{kind}:{identity}"))
