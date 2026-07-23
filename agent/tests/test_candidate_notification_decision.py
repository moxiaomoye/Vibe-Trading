from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.candidates.models import ActionAssessment
from src.investment_research.contracts import (
    ActionLevel,
    AssessmentVerdict,
    MarketRegime,
    OpportunityStatus,
    Permanence,
    ResearchPriority,
    ThesisStatus,
)
from src.investment_research.operations.notification_decision import (
    CandidateNotificationPolicy,
    InMemoryNotificationHistory,
    NotificationDecisionStatus,
    RetryState,
    RetryStatus,
    candidate_fingerprint,
    meaningful_state_signature,
)


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _assessment(**changes) -> ActionAssessment:
    values = dict(
        assessment_id="assessment-1", candidate_id="candidate-1", version_number=1,
        opportunity_version_id="opportunity-v1", thesis_version_id="thesis-v1",
        evidence_set_id="evidence-v1", market_state_id="market-v1",
        action_level=ActionLevel.ACTION_CANDIDATE, research_priority=ResearchPriority.IMMEDIATE,
        thesis_integrity=AssessmentVerdict.STRONG, mispricing_strength=AssessmentVerdict.STRONG,
        fundamental_integrity=AssessmentVerdict.STRONG, evidence_completeness=AssessmentVerdict.STRONG,
        market_context_fit=AssessmentVerdict.STRONG, asset_expression_quality=AssessmentVerdict.STRONG,
        thesis_status_snapshot=ThesisStatus.ACTIVE, opportunity_status_snapshot=OpportunityStatus.OPEN,
        permanence_snapshot=Permanence.TEMPORARY, market_regime_snapshot=MarketRegime.PANIC,
        evidence_complete=True, mispricing_significant=True, confidence=0.9,
        rationale="Evidence supports a temporary dislocation.",
        strongest_counter_case="Demand may be structurally weaker.", unknowns=("duration",),
        first_rejection_question="Has long-term demand deteriorated?", effective_from=NOW,
        next_review_at=NOW + timedelta(days=7),
    )
    values.update(changes)
    return ActionAssessment(**values)


def test_stable_fingerprint_ignores_volatile_assessment_identity_and_time() -> None:
    first = _assessment()
    second = replace(first, assessment_id="assessment-2", effective_from=NOW + timedelta(hours=1),
                     next_review_at=NOW + timedelta(days=8))
    assert candidate_fingerprint(first) == candidate_fingerprint(second)
    assert meaningful_state_signature(first) == meaningful_state_signature(second)


def test_ineligible_duplicate_and_cooldown_are_distinct() -> None:
    policy = CandidateNotificationPolicy(cooldown=timedelta(days=7))
    ineligible = policy.evaluate(replace(_assessment(), action_level=ActionLevel.RESEARCH), NOW)
    assert ineligible.status == NotificationDecisionStatus.INELIGIBLE

    history = InMemoryNotificationHistory()
    first = policy.evaluate(_assessment(), NOW, manual_confirmed=True)
    history.add(first)
    duplicate = policy.evaluate(_assessment(assessment_id="assessment-2"), NOW + timedelta(days=1),
                                history.for_candidate("candidate-1"), manual_confirmed=True)
    assert duplicate.status == NotificationDecisionStatus.DUPLICATE

    refreshed = _assessment(assessment_id="assessment-3", evidence_set_id="evidence-v2")
    cooldown = policy.evaluate(refreshed, NOW + timedelta(days=1), history.for_candidate("candidate-1"),
                               manual_confirmed=True)
    assert cooldown.status == NotificationDecisionStatus.COOLDOWN


def test_meaningful_state_change_bypasses_cooldown_but_requires_confirmation() -> None:
    policy = CandidateNotificationPolicy()
    history = InMemoryNotificationHistory()
    first = policy.evaluate(_assessment(), NOW, manual_confirmed=True)
    history.add(first)
    changed = replace(
        _assessment(assessment_id="assessment-2", evidence_set_id="evidence-v2"),
        opportunity_status_snapshot=OpportunityStatus.STRENGTHENING,
    )
    decision = policy.evaluate(changed, NOW + timedelta(days=1), history.for_candidate("candidate-1"))
    assert decision.meaningful_state_change is True
    assert decision.status == NotificationDecisionStatus.AWAITING_MANUAL_CONFIRMATION
    confirmed = policy.evaluate(
        changed, NOW + timedelta(days=1), history.for_candidate("candidate-1"), manual_confirmed=True
    )
    assert confirmed.status == NotificationDecisionStatus.DRY_RUN_READY
    assert confirmed.shadow_run is True


def test_real_delivery_mode_and_cross_candidate_history_are_rejected() -> None:
    policy = CandidateNotificationPolicy()
    with pytest.raises(ValueError, match="real notification"):
        policy.evaluate(_assessment(), NOW, shadow_run=False)
    other = policy.evaluate(_assessment(candidate_id="candidate-2"), NOW)
    history = InMemoryNotificationHistory()
    history.add(other)
    with pytest.raises(ValueError, match="history"):
        policy.evaluate(_assessment(), NOW, history.for_candidate("candidate-2"))


def test_retry_state_is_bounded_and_terminal() -> None:
    state = RetryState("fingerprint", max_attempts=2)
    state = state.record_failure("fixture failure")
    assert state.status == RetryStatus.RETRYABLE
    state = state.record_failure("fixture failure again")
    assert state.status == RetryStatus.EXHAUSTED
    assert state.attempt_count == 2
    with pytest.raises(ValueError, match="terminal"):
        state.record_failure("third failure")

    success = RetryState("another").record_success()
    assert success.status == RetryStatus.SUCCEEDED
    assert success.attempt_count == 1
