from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.candidates.models import ActionAssessment, ResearchCandidate
from src.investment_research.contracts import (
    ActionLevel,
    AssessmentVerdict,
    MarketRegime,
    OpportunityStatus,
    Permanence,
    ResearchPriority,
    ThesisStatus,
)
from src.investment_research.intelligence.alert_eligibility import (
    AlertEligibilityDecision,
    AlertEligibilityPolicy,
    OpportunityAlert,
)
from src.investment_research.market.models import MarketState


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _assessment() -> ActionAssessment:
    return ActionAssessment(
        assessment_id="assessment-1",
        candidate_id="candidate-1",
        version_number=1,
        opportunity_version_id="opportunity-v1",
        thesis_version_id="thesis-v1",
        evidence_set_id="evidence-set-1",
        market_state_id="market-state-1",
        action_level=ActionLevel.ACTION_CANDIDATE,
        research_priority=ResearchPriority.IMMEDIATE,
        thesis_integrity=AssessmentVerdict.STRONG,
        mispricing_strength=AssessmentVerdict.STRONG,
        fundamental_integrity=AssessmentVerdict.STRONG,
        evidence_completeness=AssessmentVerdict.ADEQUATE,
        market_context_fit=AssessmentVerdict.STRONG,
        asset_expression_quality=AssessmentVerdict.ADEQUATE,
        thesis_status_snapshot=ThesisStatus.ACTIVE,
        opportunity_status_snapshot=OpportunityStatus.OPEN,
        permanence_snapshot=Permanence.TEMPORARY,
        market_regime_snapshot=MarketRegime.PANIC,
        evidence_complete=True,
        mispricing_significant=True,
        confidence=0.88,
        rationale="All research gates are supported by saved evidence.",
        strongest_counter_case="The apparent temporary pressure may reveal structural weakness.",
        unknowns=("timing of convergence",),
        first_rejection_question="Has long-term demand actually deteriorated?",
        effective_from=NOW,
        next_review_at=NOW + timedelta(days=7),
    )


def test_all_fixed_gates_are_required_to_create_alert() -> None:
    policy = AlertEligibilityPolicy()
    assessment = _assessment()

    decision = policy.evaluate(assessment, NOW)
    alert = policy.create_alert("alert-1", assessment, NOW)

    assert decision.eligible is True
    assert decision.failed_gates == ()
    assert alert.assessment_id == assessment.assessment_id
    assert alert.disclaimer == "Research alert, not a trade instruction."


@pytest.mark.parametrize(
    ("changes", "failed_gate"),
    [
        ({"action_level": ActionLevel.RESEARCH}, "action_level"),
        ({"confidence": 0.82}, "confidence"),
        ({"thesis_status_snapshot": ThesisStatus.WEAKENING}, "thesis_status"),
        ({"evidence_complete": False}, "evidence_completeness"),
        ({"market_regime_snapshot": MarketRegime.NORMAL}, "market_regime"),
        ({"mispricing_significant": False}, "mispricing_significance"),
        ({"opportunity_status_snapshot": OpportunityStatus.WEAKENING}, "opportunity_status"),
        ({"permanence_snapshot": Permanence.UNCERTAIN}, "permanence"),
    ],
)
def test_each_failed_gate_keeps_assessment_report_only(changes: dict, failed_gate: str) -> None:
    assessment = replace(_assessment(), **changes)
    policy = AlertEligibilityPolicy()

    decision = policy.evaluate(assessment, NOW)

    assert decision.eligible is False
    assert failed_gate in decision.failed_gates
    with pytest.raises(ValueError, match="report-only"):
        policy.create_alert("alert", assessment, NOW)


def test_candidate_assessment_and_market_state_validate_research_contract() -> None:
    candidate = ResearchCandidate("candidate", "opportunity", "asset", NOW)
    market = MarketState("market", MarketRegime.PANIC, "set", ("systemic deleveraging",), (), 0.8, NOW)
    assert candidate.asset_id == "asset"
    assert market.regime == MarketRegime.PANIC

    with pytest.raises(ValueError, match="candidate identity"):
        replace(candidate, candidate_id="")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(candidate, created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="drivers"):
        replace(market, drivers=())
    with pytest.raises(ValueError, match="data gaps"):
        replace(market, regime=MarketRegime.UNKNOWN, drivers=(), data_gaps=())


def test_assessment_and_alert_invariants() -> None:
    assessment = _assessment()
    with pytest.raises(ValueError, match="version references"):
        replace(assessment, evidence_set_id="")
    with pytest.raises(ValueError, match="positive"):
        replace(assessment, version_number=0)
    with pytest.raises(ValueError, match="cannot precede"):
        replace(assessment, next_review_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="strongest counter"):
        replace(assessment, strongest_counter_case="")
    with pytest.raises(ValueError, match="rejection question"):
        replace(assessment, first_rejection_question="")
    with pytest.raises(ValueError, match="failed gates"):
        AlertEligibilityDecision("assessment", True, ("confidence",), NOW)
    with pytest.raises(ValueError, match="research references"):
        OpportunityAlert("", "candidate", "assessment", "opportunity", "set", NOW)
    with pytest.raises(ValueError, match="between 0 and 1"):
        AlertEligibilityPolicy(minimum_confidence=1.1)
    with pytest.raises(ValueError, match="at least one"):
        AlertEligibilityPolicy(eligible_regimes=())

