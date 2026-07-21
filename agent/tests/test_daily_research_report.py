from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from src.investment_research.candidates.models import ResearchCandidate
from src.investment_research.contracts import MarketRegime
from src.investment_research.discovery.models import DiscoveryDisposition, ResearchLead
from src.investment_research.intelligence.daily_research import DailyResearchMarkdownRenderer, DailyResearchReportBuilder
from src.investment_research.intelligence.daily_thesis import DailyThesisReport
from src.investment_research.market.models import MarketState
from tests.test_alert_eligibility import _assessment
from tests.test_intelligence_repository import _intelligence
from tests.test_mispricing_domain import NOW, _proposal


def _thesis_report() -> DailyThesisReport:
    return DailyThesisReport(
        "thesis-daily",
        NOW.date(),
        NOW,
        NOW + timedelta(minutes=1),
        "shadow",
        (),
        0,
        (),
        "No material Thesis change.",
    )


def _market() -> MarketState:
    return MarketState("market-state-1", MarketRegime.PANIC, "set", ("systemic stress",), (), 0.8, NOW)


def test_zero_candidate_report_is_a_successful_research_result() -> None:
    report = DailyResearchReportBuilder().build(
        "daily",
        NOW,
        NOW + timedelta(minutes=1),
        _thesis_report(),
        None,
    )
    rendered = DailyResearchMarkdownRenderer().render(report)

    assert report.candidates == ()
    assert report.eligible_alert_count == 0
    assert "No new high-quality research opportunity" in report.conclusion
    assert "Zero candidates is a valid research result" in rendered
    assert "Market State unavailable" in rendered
    assert "not a trade instruction" in rendered


def test_action_candidate_below_confidence_gate_is_report_only() -> None:
    candidate = ResearchCandidate("candidate-1", "opportunity", "asset", NOW)
    assessment = replace(_assessment(), confidence=0.82)
    report = DailyResearchReportBuilder().build(
        "daily",
        NOW,
        NOW + timedelta(minutes=1),
        _thesis_report(),
        _market(),
        (_proposal().opportunity_version,),
        ((candidate, assessment),),
    )

    assert report.candidates[0].alert_eligible is False
    assert "confidence" in report.candidates[0].failed_alert_gates
    assert "none passed every fixed alert gate" in report.conclusion


def test_eligible_candidate_is_visible_without_trade_language() -> None:
    candidate = ResearchCandidate("candidate-1", "opportunity", "asset", NOW)
    assessment = _assessment()
    report = DailyResearchReportBuilder().build(
        "daily",
        NOW,
        NOW + timedelta(minutes=1),
        _thesis_report(),
        _market(),
        (_proposal().opportunity_version,),
        ((candidate, assessment),),
    )
    rendered = DailyResearchMarkdownRenderer().render(report)

    assert report.eligible_alert_count == 1
    assert "passed every fixed gate" in report.conclusion
    assert "eligible alert" in rendered
    assert "not a trade instruction" in rendered


def test_daily_report_rejects_future_or_mismatched_context() -> None:
    builder = DailyResearchReportBuilder()
    with pytest.raises(ValueError, match="same information cutoff"):
        builder.build(
            "daily",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1),
            _thesis_report(),
            None,
        )
    candidate = ResearchCandidate("candidate-1", "opportunity", "asset", NOW + timedelta(days=1))
    with pytest.raises(ValueError, match="future candidate"):
        builder.build(
            "daily",
            NOW,
            NOW + timedelta(minutes=1),
            _thesis_report(),
            None,
            candidate_contexts=((candidate, _assessment()),),
        )


def test_daily_research_report_persistence_round_trip(tmp_path) -> None:
    repository, market, candidate, assessment = _intelligence(tmp_path)
    report = DailyResearchReportBuilder().build(
        "daily",
        NOW,
        NOW + timedelta(minutes=1),
        _thesis_report(),
        replace(market, regime=MarketRegime.PANIC),
        (_proposal().opportunity_version,),
        ((candidate, assessment),),
        (
            ResearchLead(
                "lead-1", "asset", "thesis-version", "evidence-set",
                DiscoveryDisposition.ATTRIBUTION_REQUIRED, ("cause unknown",), ("attribution",),
                "Why is the market selling?", NOW,
            ),
        ),
    )

    repository.save_daily_research_report(report)
    restored = repository.get_daily_research_report(NOW.date())

    assert restored.to_dict() == report.to_dict()
    with pytest.raises(KeyError):
        repository.get_daily_research_report((NOW - timedelta(days=1)).date())


def test_discovery_lead_is_reported_without_becoming_a_candidate() -> None:
    lead = ResearchLead(
        "lead-1", "asset", "thesis-version", "evidence-set",
        DiscoveryDisposition.ATTRIBUTION_REQUIRED, ("sell-off cause unproven",), ("attribution",),
        "Why is the market selling?", NOW,
    )
    report = DailyResearchReportBuilder().build(
        "daily", NOW, NOW + timedelta(minutes=1), _thesis_report(), _market(), discovery_leads=(lead,)
    )
    rendered = DailyResearchMarkdownRenderer().render(report)
    assert report.candidates == ()
    assert report.discovery_leads[0].disposition == DiscoveryDisposition.ATTRIBUTION_REQUIRED
    assert "none is yet a Research Candidate" in report.conclusion
    assert "Why is the market selling?" in rendered
