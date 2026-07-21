"""Full daily research product assembled from saved, versioned research objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ..candidates.models import ActionAssessment, ResearchCandidate
from ..contracts import ActionLevel, ConfidenceBand, MarketRegime, OpportunityStatus, ResearchPriority, confidence_band
from ..discovery.models import DiscoveryDisposition, ResearchLead
from ..market.models import MarketState
from ..mispricing.models import MispricingOpportunityVersion
from .alert_eligibility import AlertEligibilityPolicy
from .daily_thesis import DailyThesisReport


@dataclass(frozen=True, slots=True)
class OpportunityDailyChange:
    opportunity_id: str
    opportunity_version_id: str
    status: OpportunityStatus
    change_kind: str
    summary: str
    evidence_set_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "opportunity_version_id": self.opportunity_version_id,
            "status": self.status.value,
            "change_kind": self.change_kind,
            "summary": self.summary,
            "evidence_set_id": self.evidence_set_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OpportunityDailyChange":
        return cls(
            payload["opportunity_id"],
            payload["opportunity_version_id"],
            OpportunityStatus(payload["status"]),
            payload["change_kind"],
            payload["summary"],
            payload["evidence_set_id"],
        )


@dataclass(frozen=True, slots=True)
class CandidateDailyBrief:
    candidate_id: str
    asset_id: str
    opportunity_version_id: str
    assessment_id: str
    action_level: ActionLevel
    research_priority: ResearchPriority
    confidence_band: ConfidenceBand
    first_rejection_question: str
    next_review_at: datetime
    alert_eligible: bool
    failed_alert_gates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "asset_id": self.asset_id,
            "opportunity_version_id": self.opportunity_version_id,
            "assessment_id": self.assessment_id,
            "action_level": self.action_level.value,
            "research_priority": self.research_priority.value,
            "confidence_band": self.confidence_band.value,
            "first_rejection_question": self.first_rejection_question,
            "next_review_at": self.next_review_at.isoformat(),
            "alert_eligible": self.alert_eligible,
            "failed_alert_gates": list(self.failed_alert_gates),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateDailyBrief":
        return cls(
            payload["candidate_id"],
            payload["asset_id"],
            payload["opportunity_version_id"],
            payload["assessment_id"],
            ActionLevel(payload["action_level"]),
            ResearchPriority(payload["research_priority"]),
            ConfidenceBand(payload["confidence_band"]),
            payload["first_rejection_question"],
            datetime.fromisoformat(payload["next_review_at"]),
            payload["alert_eligible"],
            tuple(payload["failed_alert_gates"]),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryDailyBrief:
    lead_id: str
    asset_id: str
    thesis_version_id: str
    disposition: DiscoveryDisposition
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    first_rejection_question: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "asset_id": self.asset_id,
            "thesis_version_id": self.thesis_version_id,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "missing_evidence": list(self.missing_evidence),
            "first_rejection_question": self.first_rejection_question,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DiscoveryDailyBrief":
        return cls(
            payload["lead_id"], payload["asset_id"], payload["thesis_version_id"],
            DiscoveryDisposition(payload["disposition"]), tuple(payload["reasons"]),
            tuple(payload["missing_evidence"]), payload["first_rejection_question"],
        )


@dataclass(frozen=True, slots=True)
class DailyResearchReport:
    report_id: str
    trade_date: date
    information_cutoff: datetime
    generated_at: datetime
    mode: str
    market_state: MarketState | None
    thesis_report: DailyThesisReport
    opportunity_changes: tuple[OpportunityDailyChange, ...]
    candidates: tuple[CandidateDailyBrief, ...]
    discovery_leads: tuple[DiscoveryDailyBrief, ...]
    warnings: tuple[str, ...]
    conclusion: str

    def __post_init__(self) -> None:
        for value in (self.information_cutoff, self.generated_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("daily research timestamps must be timezone-aware")
        if not self.report_id or not self.mode:
            raise ValueError("daily research report identity and mode are required")

    @property
    def eligible_alert_count(self) -> int:
        return sum(candidate.alert_eligible for candidate in self.candidates)

    def to_dict(self) -> dict[str, Any]:
        market = None
        if self.market_state is not None:
            market = {
                "market_state_id": self.market_state.market_state_id,
                "regime": self.market_state.regime.value,
                "evidence_set_id": self.market_state.evidence_set_id,
                "drivers": list(self.market_state.drivers),
                "data_gaps": list(self.market_state.data_gaps),
                "confidence": self.market_state.confidence,
                "as_of": self.market_state.as_of.isoformat(),
            }
        return {
            "report_id": self.report_id,
            "trade_date": self.trade_date.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "mode": self.mode,
            "market_state": market,
            "thesis_report": self.thesis_report.to_dict(),
            "opportunity_changes": [item.to_dict() for item in self.opportunity_changes],
            "candidates": [item.to_dict() for item in self.candidates],
            "discovery_leads": [item.to_dict() for item in self.discovery_leads],
            "eligible_alert_count": self.eligible_alert_count,
            "warnings": list(self.warnings),
            "conclusion": self.conclusion,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DailyResearchReport":
        market_payload = payload["market_state"]
        market = None
        if market_payload is not None:
            market = MarketState(
                market_payload["market_state_id"],
                MarketRegime(market_payload["regime"]),
                market_payload["evidence_set_id"],
                tuple(market_payload["drivers"]),
                tuple(market_payload["data_gaps"]),
                market_payload["confidence"],
                datetime.fromisoformat(market_payload["as_of"]),
            )
        return cls(
            report_id=payload["report_id"],
            trade_date=date.fromisoformat(payload["trade_date"]),
            information_cutoff=datetime.fromisoformat(payload["information_cutoff"]),
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            mode=payload["mode"],
            market_state=market,
            thesis_report=DailyThesisReport.from_dict(payload["thesis_report"]),
            opportunity_changes=tuple(OpportunityDailyChange.from_dict(item) for item in payload["opportunity_changes"]),
            candidates=tuple(CandidateDailyBrief.from_dict(item) for item in payload["candidates"]),
            discovery_leads=tuple(DiscoveryDailyBrief.from_dict(item) for item in payload.get("discovery_leads", [])),
            warnings=tuple(payload["warnings"]),
            conclusion=payload["conclusion"],
        )


class DailyResearchReportBuilder:
    def __init__(self, alert_policy: AlertEligibilityPolicy | None = None):
        self.alert_policy = alert_policy or AlertEligibilityPolicy()

    def build(
        self,
        report_id: str,
        information_cutoff: datetime,
        generated_at: datetime,
        thesis_report: DailyThesisReport,
        market_state: MarketState | None,
        opportunity_versions: tuple[MispricingOpportunityVersion, ...] = (),
        candidate_contexts: tuple[tuple[ResearchCandidate, ActionAssessment], ...] = (),
        discovery_leads: tuple[ResearchLead, ...] = (),
        mode: str = "shadow",
        trade_date: date | None = None,
    ) -> DailyResearchReport:
        if thesis_report.information_cutoff != information_cutoff:
            raise ValueError("thesis and daily research reports must use the same information cutoff")
        if market_state is not None and market_state.as_of > information_cutoff:
            raise ValueError("daily research report cannot include a future market state")
        changes = tuple(self._opportunity_change(version) for version in opportunity_versions)
        briefs = tuple(
            self._candidate_brief(candidate, assessment, market_state, information_cutoff, generated_at)
            for candidate, assessment in candidate_contexts
        )
        discovery_briefs = tuple(
            DiscoveryDailyBrief(
                lead.lead_id, lead.asset_id, lead.thesis_version_id, lead.disposition,
                lead.reasons, lead.missing_evidence, lead.first_rejection_question,
            )
            for lead in discovery_leads
            if lead.as_of <= information_cutoff and lead.disposition != DiscoveryDisposition.REJECTED
        )
        if any(lead.as_of > information_cutoff for lead in discovery_leads):
            raise ValueError("daily research report cannot include future discovery leads")
        warnings = list(thesis_report.warnings)
        if market_state is None:
            warnings.append("Market State unavailable; market-context conclusions are withheld.")
        elif market_state.data_gaps:
            warnings.append(f"Market State has {len(market_state.data_gaps)} declared data gap(s).")
        eligible_count = sum(item.alert_eligible for item in briefs)
        action_candidate_count = sum(item.action_level == ActionLevel.ACTION_CANDIDATE for item in briefs)
        if eligible_count:
            conclusion = f"{eligible_count} high-quality research opportunity alert(s) passed every fixed gate."
        elif action_candidate_count:
            conclusion = "Action Candidate assessments exist, but none passed every fixed alert gate. Continue research and waiting."
        elif discovery_briefs:
            conclusion = (
                f"{len(discovery_briefs)} discovery lead(s) require further evidence or attribution; "
                "none is yet a Research Candidate. Continue research and waiting."
            )
        else:
            conclusion = "No new high-quality research opportunity was found. Continue waiting and observing."
        resolved_trade_date = trade_date or information_cutoff.date()
        if thesis_report.report_date != resolved_trade_date:
            raise ValueError("thesis and daily research reports must use the same trade date")
        return DailyResearchReport(
            report_id,
            resolved_trade_date,
            information_cutoff,
            generated_at,
            mode,
            market_state,
            thesis_report,
            changes,
            briefs,
            discovery_briefs,
            tuple(warnings),
            conclusion,
        )

    @staticmethod
    def _opportunity_change(version: MispricingOpportunityVersion) -> OpportunityDailyChange:
        change_kind = "new" if version.version_number == 1 else version.status.value
        return OpportunityDailyChange(
            version.opportunity_id,
            version.opportunity_version_id,
            version.status,
            change_kind,
            version.change_summary,
            version.evidence_set_id,
        )

    def _candidate_brief(
        self,
        candidate: ResearchCandidate,
        assessment: ActionAssessment,
        market_state: MarketState | None,
        information_cutoff: datetime,
        generated_at: datetime,
    ) -> CandidateDailyBrief:
        if candidate.candidate_id != assessment.candidate_id:
            raise ValueError("candidate and assessment identities do not match")
        if candidate.created_at > information_cutoff or assessment.effective_from > information_cutoff:
            raise ValueError("daily research report cannot include future candidate information")
        decision = self.alert_policy.evaluate(assessment, generated_at)
        failed_gates = list(decision.failed_gates)
        if market_state is None:
            failed_gates.append("market_state_unavailable")
        elif assessment.market_state_id != market_state.market_state_id or assessment.market_regime_snapshot != market_state.regime:
            raise ValueError("assessment market snapshot does not match the daily Market State")
        return CandidateDailyBrief(
            candidate.candidate_id,
            candidate.asset_id,
            assessment.opportunity_version_id,
            assessment.assessment_id,
            assessment.action_level,
            assessment.research_priority,
            confidence_band(assessment.confidence),
            assessment.first_rejection_question,
            assessment.next_review_at,
            not failed_gates,
            tuple(failed_gates),
        )


class DailyResearchMarkdownRenderer:
    def render(self, report: DailyResearchReport) -> str:
        regime = report.market_state.regime.value if report.market_state else "unavailable"
        lines = [
            "# AI Investment Research Daily",
            "",
            f"Trade date: {report.trade_date.isoformat()}",
            f"Data cutoff: {report.information_cutoff.isoformat()}",
            f"Mode: {report.mode}",
            "",
            "## Market State",
            "",
            f"- Regime: {regime}",
            "",
            "## Research Candidates",
            "",
        ]
        if not report.candidates:
            lines.append("- None. Zero candidates is a valid research result.")
        for candidate in report.candidates:
            alert_state = "eligible alert" if candidate.alert_eligible else f"report only ({', '.join(candidate.failed_alert_gates)})"
            lines.append(
                f"- `{candidate.candidate_id}`: {candidate.action_level.value}, "
                f"priority {candidate.research_priority.value}, {alert_state}"
            )
        lines.extend(("", "## Discovery Leads", ""))
        if not report.discovery_leads:
            lines.append("- None.")
        for lead in report.discovery_leads:
            lines.append(
                f"- `{lead.asset_id}`: {lead.disposition.value}; first rejection question: "
                f"{lead.first_rejection_question}"
            )
        lines.extend(("", "## Today's Conclusion", "", report.conclusion))
        if report.warnings:
            lines.extend(("", "## Data-quality warnings", ""))
            lines.extend(f"- {warning}" for warning in report.warnings)
        lines.extend(("", "_Research output, not a trade instruction._"))
        return "\n".join(lines)
