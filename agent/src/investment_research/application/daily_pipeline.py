"""Idempotent end-of-day research pipeline; generation is separate from delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from ..assets.models import Asset, ThesisExposure
from ..discovery.models import ResearchLead, ResearchSnapshot
from ..discovery.triage import MispricingDiscoveryTriage
from ..evidence.context import ContextEvidenceBundle
from ..evidence.models import Evidence
from ..intelligence.daily_research import DailyResearchReport, DailyResearchReportBuilder
from ..intelligence.daily_thesis import DailyThesisUpdateService
from ..market.assessment import MarketSnapshot, MarketStateAssessmentEngine
from ..operations.delivery import DailyNotificationPlanner
from ..operations.models import DeliveryChannel, JobRun, JobStatus
from ..operations.scheduling import TradingDaySchedule
from ..repositories.sqlite import SQLiteResearchRepository
from ..repositories.sqlite_discovery import SQLiteDiscoveryRepository
from ..repositories.sqlite_context_evidence import SQLiteContextEvidenceRepository
from ..repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from ..repositories.sqlite_operations import SQLiteOperationsRepository
from ..thesis.models import ThesisVersion


@dataclass(frozen=True, slots=True)
class DiscoveryContext:
    asset: Asset
    thesis: ThesisVersion
    exposure: ThesisExposure
    snapshot: ResearchSnapshot


@dataclass(frozen=True, slots=True)
class DailyResearchInputs:
    information_cutoff: datetime
    market_snapshot: MarketSnapshot | None = None
    market_evidence_bundle: ContextEvidenceBundle | None = None
    market_evidence: tuple[Evidence, ...] = ()
    discovery_contexts: tuple[DiscoveryContext, ...] = ()

    def __post_init__(self) -> None:
        if self.information_cutoff.tzinfo is None or self.information_cutoff.utcoffset() is None:
            raise ValueError("information_cutoff must be timezone-aware")
        if self.market_snapshot is not None:
            if self.market_evidence_bundle is None:
                raise ValueError("a Market Snapshot requires a context evidence bundle")
            if self.market_snapshot.evidence_set_id != self.market_evidence_bundle.evidence_bundle_id:
                raise ValueError("Market Snapshot and context evidence bundle are inconsistent")
            self.market_evidence_bundle.validate_point_in_time(self.market_evidence)


class DailyResearchPipeline:
    job_name = "investment-research-daily"

    def __init__(
        self,
        research: SQLiteResearchRepository,
        intelligence: SQLiteIntelligenceRepository,
        discovery: SQLiteDiscoveryRepository,
        operations: SQLiteOperationsRepository,
        schedule: TradingDaySchedule | None = None,
    ):
        self.research = research
        self.intelligence = intelligence
        self.discovery = discovery
        self.operations = operations
        self.context_evidence = SQLiteContextEvidenceRepository(research.path)
        self.schedule = schedule or TradingDaySchedule()

    def run_if_due(
        self,
        run_id: str,
        now: datetime,
        inputs: DailyResearchInputs,
        mode: str = "shadow",
        channels: tuple[DeliveryChannel, ...] = (),
    ) -> DailyResearchReport | None:
        if not self.schedule.is_due(now):
            return None
        trade_date = self.schedule.local_now(now).date()
        run = JobRun(run_id, self.job_name, trade_date, mode, JobStatus.RUNNING, 1, now, now)
        if not self.operations.acquire_run(run):
            try:
                return self.intelligence.get_daily_research_report(trade_date, mode)
            except KeyError:
                return None
        try:
            thesis_report_id = self._stable_id("thesis-daily", mode, trade_date.isoformat())
            thesis_report = DailyThesisUpdateService(self.research).generate(
                thesis_report_id, inputs.information_cutoff, now, mode, report_date=trade_date
            )
            self.research.save_daily_thesis_report(thesis_report)

            market_state = None
            if inputs.market_snapshot is not None:
                assert inputs.market_evidence_bundle is not None
                self.context_evidence.save_bundle(inputs.market_evidence_bundle, inputs.market_evidence)
                market_state = MarketStateAssessmentEngine().assess(
                    self._stable_id("market-state", mode, trade_date.isoformat()),
                    inputs.market_snapshot,
                    inputs.information_cutoff,
                )
                self.intelligence.save_market_state(market_state)

            leads: list[ResearchLead] = []
            triage = MispricingDiscoveryTriage()
            for context in inputs.discovery_contexts:
                lead = triage.evaluate(context.asset, context.thesis, context.exposure, context.snapshot)
                self.discovery.save_result(context.snapshot, lead)
                leads.append(lead)

            report = DailyResearchReportBuilder().build(
                self._stable_id("research-daily", mode, trade_date.isoformat()),
                inputs.information_cutoff,
                now,
                thesis_report,
                market_state,
                discovery_leads=tuple(leads),
                mode=mode,
                trade_date=trade_date,
            )
            self.intelligence.save_daily_research_report(report)
            DailyNotificationPlanner(self.operations).enqueue(report, channels, now)
            self.operations.finish_run(run_id, JobStatus.SUCCEEDED, now)
            return report
        except Exception as exc:
            self.operations.finish_run(run_id, JobStatus.FAILED, now, str(exc))
            raise

    @staticmethod
    def _stable_id(kind: str, mode: str, value: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"{kind}:{mode}:{value}"))
