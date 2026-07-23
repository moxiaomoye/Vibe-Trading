"""Cohesive, deterministic backend shadow run for panic research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..assets.models import Asset, ThesisExposure
from ..contracts import MarketRegime
from ..evidence.models import Evidence, EvidenceSet
from ..integrations.value_hunter_market import PanicScanResearchAdapter, ResearchBinding
from ..mispricing.attribution import AttributionEvaluation
from ..mispricing.models import PermanenceAssessment
from ..operations.notification_decision import (
    CandidateNotificationPolicy,
    InMemoryNotificationHistory,
    NotificationDecision,
)
from ..operations.scheduling import TradingDaySchedule
from ..thesis.models import ThesisVersion
from ..valuation.models import QualityAssessment, ScenarioValuationResult
from ...value_hunter.panic_scan import PanicScanResult, run_panic_scan
from .panic_orchestration import (
    InMemoryOrchestrationState,
    OrchestrationRequest,
    OrchestrationResult,
    PanicResearchOrchestrator,
    PanicRuntimeFlags,
)
from .panic_research_pipeline import (
    PanicMispricingResearchPipeline,
    ResearchCase,
    ResearchCandidatePipelineResult,
    ResearchPipelinePolicy,
)


@dataclass(frozen=True, slots=True)
class ShadowCandidateInput:
    symbol: str
    asset: Asset
    thesis: ThesisVersion
    exposure: ThesisExposure
    evidence_set: EvidenceSet
    evidence: tuple[Evidence, ...]
    quality: QualityAssessment
    valuation: ScenarioValuationResult
    attribution: AttributionEvaluation
    permanence: PermanenceAssessment
    research_case: ResearchCase
    policy: ResearchPipelinePolicy

    def __post_init__(self) -> None:
        if not self.symbol.strip() or self.asset.asset_id != self.exposure.asset_id:
            raise ValueError("shadow candidate requires a symbol and consistent asset identity")


@dataclass(frozen=True, slots=True)
class ShadowRunInputs:
    panel_data: dict[str, Any]
    watchlist_path: str
    information_cutoff: datetime
    candidates: tuple[ShadowCandidateInput, ...] = ()

    def __post_init__(self) -> None:
        _aware(self.information_cutoff, "information_cutoff")
        if not self.watchlist_path.strip():
            raise ValueError("shadow run requires an explicit watchlist path")
        symbols = [item.symbol for item in self.candidates]
        if len(symbols) != len(set(symbols)):
            raise ValueError("shadow candidate symbols must be unique")


@dataclass(frozen=True, slots=True)
class ShadowCandidateResult:
    symbol: str
    pipeline: ResearchCandidatePipelineResult
    notification: NotificationDecision | None


@dataclass(frozen=True, slots=True)
class ShadowRunReport:
    shadow_run: bool
    information_cutoff: datetime
    scan: PanicScanResult
    market_regime: MarketRegime
    candidates: tuple[ShadowCandidateResult, ...]
    data_gaps: tuple[str, ...]
    versions: tuple[tuple[str, str], ...]
    manual_review_required: bool = True

    def __post_init__(self) -> None:
        _aware(self.information_cutoff, "information_cutoff")
        if not self.shadow_run or not self.manual_review_required:
            raise ValueError("shadow reports require shadow mode and manual review")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe export without raw dataframes or credentials."""
        return {
            "shadow_run": True,
            "information_cutoff": self.information_cutoff.isoformat(),
            "market": {
                "trade_date": self.scan.market_snapshot.trade_date.isoformat(),
                "regime": self.market_regime.value,
                "panic_observation": self.scan.panic.level.value,
                "advance": self.scan.market_snapshot.advance,
                "decline": self.scan.market_snapshot.decline,
                "limit_down": self.scan.market_snapshot.limit_down,
                "median_daily_return": self.scan.market_snapshot.median_daily_return,
            },
            "screened_watchlist": [
                {
                    "symbol": item.symbol,
                    "change_pct": item.change_pct,
                    "relative_to_market": item.relative_to_market,
                    "relative_to_sector": item.relative_to_sector,
                    "is_limit_down": item.is_limit_down,
                    "data_gap": item.data_gap.description or None,
                }
                for item in self.scan.watchlist
            ],
            "research_candidates": [
                {
                    "symbol": item.symbol,
                    "candidate_id": item.pipeline.candidate.candidate_id if item.pipeline.candidate else None,
                    "action_level": (
                        item.pipeline.assessment.action_level.value if item.pipeline.assessment else None
                    ),
                    "confidence": item.pipeline.assessment.confidence if item.pipeline.assessment else None,
                    "quality_status": item.pipeline.quality.status.value,
                    "valuation_status": item.pipeline.valuation.status.value,
                    "attribution_scope": item.pipeline.attribution.scope.value,
                    "scenario_value_range": item.pipeline.scenario_value_range,
                    "supporting_evidence": list(item.pipeline.opportunity_version.supporting_evidence_ids),
                    "counter_evidence": list(item.pipeline.opportunity_version.counter_evidence_ids),
                    "catalysts": list(item.pipeline.catalysts),
                    "invalidation_conditions": list(item.pipeline.invalidation_conditions),
                    "blocked_reasons": list(item.pipeline.blocked_reasons),
                    "data_gaps": list(item.pipeline.data_gaps),
                    "notification": (
                        {
                            "status": item.notification.status.value,
                            "eligible": item.notification.eligible,
                            "reasons": list(item.notification.reasons),
                            "meaningful_state_change": item.notification.meaningful_state_change,
                        }
                        if item.notification else None
                    ),
                }
                for item in self.candidates
            ],
            "data_gaps": list(self.data_gaps),
            "versions": dict(self.versions),
            "manual_review_required": True,
        }


@dataclass(frozen=True, slots=True)
class ShadowRunConfig:
    enabled: bool = False
    manual_notification_confirmation: bool = False
    schedule: TradingDaySchedule = TradingDaySchedule()


class PanicResearchShadowRunner:
    """Manual facade; constructing it never starts a task or performs I/O."""

    def __init__(
        self,
        config: ShadowRunConfig | None = None,
        *,
        orchestration_state: InMemoryOrchestrationState | None = None,
        notification_history: InMemoryNotificationHistory | None = None,
    ) -> None:
        self.config = config or ShadowRunConfig()
        self.orchestration_state = orchestration_state or InMemoryOrchestrationState()
        self.notification_history = notification_history or InMemoryNotificationHistory()
        self.orchestrator = PanicResearchOrchestrator(
            self.orchestration_state,
            schedule=self.config.schedule,
            flags=PanicRuntimeFlags(feature_enabled=self.config.enabled),
        )

    def run(
        self, request: OrchestrationRequest, inputs: ShadowRunInputs
    ) -> OrchestrationResult[ShadowRunReport]:
        if request.data_date != inputs.panel_data.get("data_date"):
            raise ValueError("orchestration and panel data dates must match")
        return self.orchestrator.run(request, lambda: self.evaluate(inputs))

    def evaluate(self, inputs: ShadowRunInputs) -> ShadowRunReport:
        scan = run_panic_scan(panel_data=inputs.panel_data, watchlist_path=inputs.watchlist_path)
        bindings = tuple(
            ResearchBinding(item.symbol, item.asset.asset_id, item.thesis.thesis_version_id)
            for item in inputs.candidates
        )
        adapted = PanicScanResearchAdapter().map(
            scan, information_cutoff=inputs.information_cutoff, bindings=bindings
        )
        research_inputs = {item.symbol: item for item in inputs.candidates}
        results: list[ShadowCandidateResult] = []
        active_market = adapted.market_state.regime in {MarketRegime.PANIC, MarketRegime.SYSTEMIC_STRESS}
        if active_market:
            for mapping in adapted.discovery_leads:
                bound = research_inputs.get(mapping.facts.symbol)
                if bound is None or mapping.lead is None:
                    continue
                pipeline = PanicMispricingResearchPipeline().run(
                    asset=bound.asset,
                    thesis=bound.thesis,
                    exposure=bound.exposure,
                    market_state=adapted.market_state,
                    discovery_lead=mapping.lead,
                    evidence_set=bound.evidence_set,
                    evidence=bound.evidence,
                    quality=bound.quality,
                    valuation=bound.valuation,
                    attribution=bound.attribution,
                    permanence=bound.permanence,
                    research_case=bound.research_case,
                    policy=bound.policy,
                    evaluated_at=inputs.information_cutoff,
                    screening_facts=mapping.facts,
                )
                notification = None
                if pipeline.assessment is not None:
                    prior = self.notification_history.for_candidate(pipeline.assessment.candidate_id)
                    notification = CandidateNotificationPolicy().evaluate(
                        pipeline.assessment,
                        inputs.information_cutoff,
                        prior,
                        manual_confirmed=self.config.manual_notification_confirmation,
                    )
                    self.notification_history.add(notification)
                results.append(ShadowCandidateResult(mapping.facts.symbol, pipeline, notification))

        gaps = _unique(
            [
                *adapted.market_state.data_gaps,
                *(gap.reason for gap in scan.data_gaps),
                *scan.errors,
                *(gap for item in results for gap in item.pipeline.data_gaps),
            ]
        )
        versions = (
            ("panic_rule", scan.rule_version),
            ("watchlist", scan.watchlist_version),
            ("candidate_pipeline", _single_version(results)),
            ("notification_decision", "1.0.0"),
        )
        return ShadowRunReport(
            True, inputs.information_cutoff, scan, adapted.market_state.regime,
            tuple(results), gaps, versions,
        )


def _single_version(results: list[ShadowCandidateResult]) -> str:
    versions = {item.pipeline.policy_version for item in results}
    if not versions:
        return "not_run"
    return next(iter(versions)) if len(versions) == 1 else "mixed"


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
