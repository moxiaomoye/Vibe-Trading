"""In-memory panic/mispricing research pipeline; no persistence or delivery."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from ..assets.models import Asset, ThesisExposure
from ..candidates.models import ActionAssessment, ResearchCandidate
from ..contracts import (
    ActionLevel,
    AssessmentVerdict,
    MarketRegime,
    OpportunityStatus,
    Permanence,
    ResearchPriority,
    ThesisStatus,
)
from ..discovery.models import DiscoveryDisposition, ResearchLead
from ..evidence.models import Evidence, EvidenceSet
from ..integrations.value_hunter_market import ValueHunterDiscoveryFacts
from ..market.models import MarketState
from ..mispricing.attribution import AttributionEvaluation, AttributionScope
from ..mispricing.models import (
    MarketImpliedView,
    MispricingOpportunity,
    MispricingOpportunityVersion,
    PermanenceAssessment,
)
from ..thesis.models import ThesisVersion
from ..valuation.models import EvaluationStatus, QualityAssessment, ScenarioValuationResult
from .mispricing import MispricingProposal, MispricingProposalValidator


@dataclass(frozen=True, slots=True)
class ResearchCase:
    research_view: str
    variant_wedge: str
    why_now: str
    implied_expectations: tuple[str, ...]
    priced_positives: tuple[str, ...]
    possible_overdiscounted_negatives: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    unknowns: tuple[str, ...]
    convergence_paths: tuple[str, ...]
    catalysts: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    first_rejection_question: str
    confidence: float
    next_review_at: datetime

    def __post_init__(self) -> None:
        _aware(self.next_review_at, "next_review_at")
        if not 0 <= self.confidence <= 1:
            raise ValueError("research-case confidence must be between 0 and 1")
        required_text = (
            self.research_view,
            self.variant_wedge,
            self.why_now,
            self.first_rejection_question,
        )
        if not all(value.strip() for value in required_text):
            raise ValueError("research case requires a complete narrative and rejection question")
        if not self.supporting_evidence_ids or not self.counter_evidence_ids:
            raise ValueError("research case requires supporting and counter evidence")
        if not self.convergence_paths or not self.invalidation_conditions:
            raise ValueError("research case requires convergence and invalidation conditions")


@dataclass(frozen=True, slots=True)
class ResearchPipelinePolicy:
    version: str
    minimum_base_upside: float
    action_candidate_confidence: float
    minimum_exposure_strength: float
    minimum_exposure_purity: float
    severe_gap_confidence_cap: float

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("pipeline policy version is required")
        for name in (
            "minimum_base_upside",
            "action_candidate_confidence",
            "minimum_exposure_strength",
            "minimum_exposure_purity",
            "severe_gap_confidence_cap",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ResearchCandidatePipelineResult:
    opportunity: MispricingOpportunity
    opportunity_version: MispricingOpportunityVersion
    candidate: ResearchCandidate | None
    assessment: ActionAssessment | None
    market_implied_view: MarketImpliedView
    attribution: AttributionEvaluation
    permanence: PermanenceAssessment
    quality: QualityAssessment
    valuation: ScenarioValuationResult
    screening_facts: ValueHunterDiscoveryFacts | None
    catalysts: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    scenario_value_range: tuple[str, str] | None
    data_coverage: tuple[str, ...]
    data_gaps: tuple[str, ...]
    policy_version: str
    blocked_reasons: tuple[str, ...]


class PanicMispricingResearchPipeline:
    def run(
        self,
        *,
        asset: Asset,
        thesis: ThesisVersion,
        exposure: ThesisExposure,
        market_state: MarketState,
        discovery_lead: ResearchLead,
        evidence_set: EvidenceSet,
        evidence: tuple[Evidence, ...],
        quality: QualityAssessment,
        valuation: ScenarioValuationResult,
        attribution: AttributionEvaluation,
        permanence: PermanenceAssessment,
        research_case: ResearchCase,
        policy: ResearchPipelinePolicy,
        evaluated_at: datetime,
        screening_facts: ValueHunterDiscoveryFacts | None = None,
    ) -> ResearchCandidatePipelineResult:
        _aware(evaluated_at, "evaluated_at")
        self._validate_inputs(
            asset,
            thesis,
            exposure,
            market_state,
            discovery_lead,
            evidence_set,
            evidence,
            quality,
            valuation,
            attribution,
            permanence,
            research_case,
            evaluated_at,
        )
        evidence_ids = set(evidence_set.evidence_ids)
        case_ids = set(research_case.supporting_evidence_ids) | set(research_case.counter_evidence_ids)
        if case_ids - evidence_ids:
            raise ValueError("research case cites evidence outside the evidence set")

        identity = (
            f"{asset.asset_id}:{thesis.thesis_version_id}:{evaluated_at.isoformat()}:"
            f"{policy.version}:{valuation.assumption_version or 'unconfigured'}:"
            f"{attribution.policy_version}"
        )
        market_view = MarketImpliedView(
            view_id=_id("market-view", identity),
            asset_id=asset.asset_id,
            evidence_set_id=evidence_set.evidence_set_id,
            as_of=evaluated_at,
            narrative=research_case.research_view,
            implied_expectations=research_case.implied_expectations,
            priced_positives=research_case.priced_positives,
            possible_overdiscounted_negatives=research_case.possible_overdiscounted_negatives,
            unknowns=research_case.unknowns,
            evidence_ids=tuple(dict.fromkeys((*research_case.supporting_evidence_ids, *research_case.counter_evidence_ids))),
            confidence=research_case.confidence,
        )
        aligned_attribution = replace(
            attribution.attribution,
            evidence_set_id=evidence_set.evidence_set_id,
        )
        gaps = _gaps(quality, valuation, attribution, screening_facts)
        severe_gaps = _severe_gaps(quality, valuation, attribution, gaps)
        evidence_complete = not severe_gaps and bool(
            research_case.supporting_evidence_ids and research_case.counter_evidence_ids
        )
        exposure_sufficient = (
            exposure.exposure_strength >= policy.minimum_exposure_strength
            and exposure.exposure_purity >= policy.minimum_exposure_purity
        )
        base_upside = _base_upside(valuation)
        mispricing_significant = (
            base_upside is not None
            and base_upside >= policy.minimum_base_upside
            and quality.status != EvaluationStatus.UNCONFIGURED
            and attribution.scope != AttributionScope.INSUFFICIENT_DATA
        )
        confidence = min(thesis.confidence, research_case.confidence, permanence.confidence)
        if severe_gaps:
            confidence = min(confidence, policy.severe_gap_confidence_cap)
        status = (
            OpportunityStatus.OPEN
            if evidence_complete
            and mispricing_significant
            and exposure_sufficient
            and permanence.overall == Permanence.TEMPORARY
            and thesis.status in {ThesisStatus.ACTIVE, ThesisStatus.WEAKENING}
            else OpportunityStatus.HYPOTHESIS
        )
        opportunity = MispricingOpportunity(
            opportunity_id=_id("opportunity", identity),
            thesis_id=thesis.thesis_id,
            asset_id=asset.asset_id,
            dedupe_key=f"{asset.asset_id}:{thesis.thesis_id}",
            created_at=evaluated_at,
        )
        opportunity_version = MispricingOpportunityVersion(
            opportunity_version_id=_id("opportunity-version", identity),
            opportunity_id=opportunity.opportunity_id,
            version_number=1,
            status=status,
            thesis_version_id=thesis.thesis_version_id,
            exposure_id=exposure.exposure_id,
            market_implied_view_id=market_view.view_id,
            attribution_id=aligned_attribution.attribution_id,
            permanence_assessment_id=permanence.assessment_id,
            evidence_set_id=evidence_set.evidence_set_id,
            research_view=research_case.research_view,
            variant_wedge=research_case.variant_wedge,
            why_now=research_case.why_now,
            supporting_evidence_ids=research_case.supporting_evidence_ids,
            counter_evidence_ids=research_case.counter_evidence_ids,
            alternative_explanations=research_case.alternative_explanations,
            unknowns=tuple(dict.fromkeys((*research_case.unknowns, *attribution.unknowns))),
            convergence_paths=research_case.convergence_paths,
            first_rejection_question=research_case.first_rejection_question,
            kill_criteria=research_case.invalidation_conditions,
            confidence=confidence,
            change_summary="initial deterministic panic/mispricing research assessment",
            effective_from=evaluated_at,
            next_review_at=research_case.next_review_at,
        )
        proposal = MispricingProposal(
            thesis,
            exposure,
            evidence_set,
            evidence,
            market_view,
            aligned_attribution,
            permanence,
            opportunity_version,
        )
        MispricingProposalValidator().validate(proposal)

        blocked = _blocked_reasons(
            discovery_lead,
            severe_gaps,
            evidence_complete,
            mispricing_significant,
            permanence,
            exposure,
            policy,
        )
        candidate = None
        assessment = None
        if discovery_lead.disposition != DiscoveryDisposition.REJECTED:
            candidate = ResearchCandidate(
                candidate_id=_id("candidate", identity),
                opportunity_id=opportunity.opportunity_id,
                asset_id=asset.asset_id,
                created_at=evaluated_at,
            )
            action_level = _action_level(
                status,
                evidence_complete,
                mispricing_significant,
                permanence,
                market_state,
                confidence,
                policy,
            )
            assessment = ActionAssessment(
                assessment_id=_id("assessment", identity),
                candidate_id=candidate.candidate_id,
                version_number=1,
                opportunity_version_id=opportunity_version.opportunity_version_id,
                thesis_version_id=thesis.thesis_version_id,
                evidence_set_id=evidence_set.evidence_set_id,
                market_state_id=market_state.market_state_id,
                action_level=action_level,
                research_priority=_priority(action_level),
                thesis_integrity=_thesis_verdict(thesis.status),
                mispricing_strength=_bool_verdict(mispricing_significant),
                fundamental_integrity=_quality_verdict(quality.status),
                evidence_completeness=_bool_verdict(evidence_complete),
                market_context_fit=_market_verdict(market_state.regime),
                asset_expression_quality=_exposure_verdict(exposure, policy),
                thesis_status_snapshot=thesis.status,
                opportunity_status_snapshot=status,
                permanence_snapshot=permanence.overall,
                market_regime_snapshot=market_state.regime,
                evidence_complete=evidence_complete,
                mispricing_significant=mispricing_significant,
                confidence=confidence,
                rationale="; ".join(blocked) if blocked else "all configured research gates passed",
                strongest_counter_case=(
                    research_case.alternative_explanations[0]
                    if research_case.alternative_explanations
                    else research_case.first_rejection_question
                ),
                unknowns=tuple(dict.fromkeys((*research_case.unknowns, *gaps))),
                first_rejection_question=research_case.first_rejection_question,
                effective_from=evaluated_at,
                next_review_at=research_case.next_review_at,
            )

        return ResearchCandidatePipelineResult(
            opportunity=opportunity,
            opportunity_version=opportunity_version,
            candidate=candidate,
            assessment=assessment,
            market_implied_view=market_view,
            attribution=replace(attribution, attribution=aligned_attribution),
            permanence=permanence,
            quality=quality,
            valuation=valuation,
            screening_facts=screening_facts,
            catalysts=research_case.catalysts,
            invalidation_conditions=research_case.invalidation_conditions,
            scenario_value_range=_scenario_range(valuation),
            data_coverage=_coverage(quality, valuation, attribution),
            data_gaps=gaps,
            policy_version=policy.version,
            blocked_reasons=blocked,
        )

    @staticmethod
    def _validate_inputs(
        asset: Asset,
        thesis: ThesisVersion,
        exposure: ThesisExposure,
        market_state: MarketState,
        lead: ResearchLead,
        evidence_set: EvidenceSet,
        evidence: tuple[Evidence, ...],
        quality: QualityAssessment,
        valuation: ScenarioValuationResult,
        attribution: AttributionEvaluation,
        permanence: PermanenceAssessment,
        research_case: ResearchCase,
        evaluated_at: datetime,
    ) -> None:
        evidence_set.validate_point_in_time(evidence)
        if any(item.available_at > evaluated_at for item in evidence):
            raise ValueError("future evidence cannot enter the research pipeline")
        if not all(
            value == asset.asset_id
            for value in (
                exposure.asset_id,
                lead.asset_id,
                quality.asset_id,
                valuation.asset_id,
                attribution.attribution.asset_id,
            )
        ):
            raise ValueError("pipeline asset references are inconsistent")
        if exposure.thesis_version_id != thesis.thesis_version_id or lead.thesis_version_id != thesis.thesis_version_id:
            raise ValueError("pipeline thesis-version references are inconsistent")
        if exposure.thesis_id != thesis.thesis_id:
            raise ValueError("pipeline thesis identity is inconsistent")
        if any(
            value > evaluated_at
            for value in (
                thesis.effective_from,
                exposure.as_of,
                market_state.as_of,
                lead.as_of,
                quality.information_cutoff,
                valuation.information_cutoff,
                attribution.attribution.created_at,
                permanence.as_of,
            )
        ):
            raise ValueError("future domain state cannot enter the research pipeline")
        if research_case.next_review_at < evaluated_at:
            raise ValueError("next review cannot precede pipeline evaluation")
        expected_set = evidence_set.evidence_set_id
        if exposure.evidence_set_id != expected_set or permanence.evidence_set_id != expected_set:
            raise ValueError("pipeline components must share the point-in-time evidence set")
        if market_state.regime == MarketRegime.UNKNOWN and not market_state.data_gaps:
            raise ValueError("unknown market state requires explicit data gaps")


def _gaps(quality, valuation, attribution, screening_facts) -> tuple[str, ...]:
    values = [*quality.data_gaps, *valuation.data_gaps, *attribution.data_gaps]
    if screening_facts is not None:
        values.extend(screening_facts.data_gaps)
    return tuple(dict.fromkeys(value for value in values if value))


def _severe_gaps(quality, valuation, attribution, gaps) -> tuple[str, ...]:
    severe = []
    if quality.status == EvaluationStatus.UNCONFIGURED:
        severe.append("quality_unconfigured")
    if valuation.status == EvaluationStatus.UNCONFIGURED:
        severe.append("valuation_unconfigured")
    if attribution.scope == AttributionScope.INSUFFICIENT_DATA:
        severe.append("attribution_insufficient")
    if gaps and not severe:
        severe.extend(value for value in gaps if "future" in value or "point_in_time" in value)
    return tuple(dict.fromkeys(severe))


def _base_upside(valuation: ScenarioValuationResult) -> float | None:
    for scenario in valuation.scenarios:
        if scenario.name == "base":
            return float(scenario.upside)
    return None


def _blocked_reasons(lead, severe, complete, significant, permanence, exposure, policy):
    reasons = list(severe)
    if lead.disposition == DiscoveryDisposition.REJECTED:
        reasons.append("discovery_rejected")
    if not complete:
        reasons.append("evidence_incomplete")
    if not significant:
        reasons.append("mispricing_not_established")
    if permanence.overall != Permanence.TEMPORARY:
        reasons.append("temporary_cause_not_established")
    if exposure.exposure_strength < policy.minimum_exposure_strength:
        reasons.append("thesis_exposure_strength")
    if exposure.exposure_purity < policy.minimum_exposure_purity:
        reasons.append("thesis_exposure_purity")
    return tuple(dict.fromkeys(reasons))


def _action_level(status, complete, significant, permanence, market, confidence, policy):
    if status != OpportunityStatus.OPEN or not complete or not significant:
        return ActionLevel.WATCH
    if permanence.overall != Permanence.TEMPORARY:
        return ActionLevel.RESEARCH
    if market.regime not in {MarketRegime.PANIC, MarketRegime.SYSTEMIC_STRESS}:
        return ActionLevel.PREPARE
    if confidence < policy.action_candidate_confidence:
        return ActionLevel.PREPARE
    return ActionLevel.ACTION_CANDIDATE


def _priority(level):
    return {
        ActionLevel.WATCH: ResearchPriority.LOW,
        ActionLevel.RESEARCH: ResearchPriority.NORMAL,
        ActionLevel.PREPARE: ResearchPriority.HIGH,
        ActionLevel.ACTION_CANDIDATE: ResearchPriority.IMMEDIATE,
    }[level]


def _thesis_verdict(status):
    if status == ThesisStatus.ACTIVE:
        return AssessmentVerdict.STRONG
    if status == ThesisStatus.WEAKENING:
        return AssessmentVerdict.ADEQUATE
    return AssessmentVerdict.WEAK


def _bool_verdict(value):
    return AssessmentVerdict.STRONG if value else AssessmentVerdict.UNKNOWN


def _quality_verdict(status):
    return {
        EvaluationStatus.CONFIGURED: AssessmentVerdict.STRONG,
        EvaluationStatus.PARTIAL: AssessmentVerdict.ADEQUATE,
        EvaluationStatus.PROVISIONAL: AssessmentVerdict.ADEQUATE,
        EvaluationStatus.UNCONFIGURED: AssessmentVerdict.UNKNOWN,
    }[status]


def _market_verdict(regime):
    if regime in {MarketRegime.PANIC, MarketRegime.SYSTEMIC_STRESS}:
        return AssessmentVerdict.STRONG
    if regime == MarketRegime.CORRECTION:
        return AssessmentVerdict.ADEQUATE
    return AssessmentVerdict.WEAK if regime == MarketRegime.NORMAL else AssessmentVerdict.UNKNOWN


def _exposure_verdict(exposure, policy):
    if (
        exposure.exposure_strength >= policy.minimum_exposure_strength
        and exposure.exposure_purity >= policy.minimum_exposure_purity
    ):
        return AssessmentVerdict.STRONG
    return AssessmentVerdict.WEAK


def _scenario_range(valuation):
    if not valuation.scenarios:
        return None
    values = [item.indicated_value for item in valuation.scenarios]
    return str(min(values)), str(max(values))


def _coverage(quality, valuation, attribution):
    return (
        f"quality:{quality.status.value}",
        f"valuation:{valuation.status.value}",
        f"attribution:{attribution.scope.value}",
    )


def _id(kind: str, identity: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{kind}:{identity}"))


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
