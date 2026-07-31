"""Pure, dry-run notification decisions for research candidates.

This module deliberately has no transport or persistence dependency.  It decides
whether a candidate deserves an alert preview; delivery remains a separate,
explicitly enabled concern.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from ..candidates.models import ActionAssessment
from ..contracts import ActionLevel, confidence_band
from ..intelligence.alert_eligibility import AlertEligibilityPolicy


class NotificationDecisionStatus(StrEnum):
    INELIGIBLE = "ineligible"
    DUPLICATE = "duplicate"
    COOLDOWN = "cooldown"
    AWAITING_MANUAL_CONFIRMATION = "awaiting_manual_confirmation"
    DRY_RUN_READY = "dry_run_ready"


class RetryStatus(StrEnum):
    PENDING = "pending"
    RETRYABLE = "retryable"
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class NotificationHistoryRecord:
    fingerprint: str
    state_signature: str
    candidate_id: str
    decided_at: datetime
    status: NotificationDecisionStatus

    def __post_init__(self) -> None:
        _aware(self.decided_at, "decided_at")
        if not all((self.fingerprint, self.state_signature, self.candidate_id)):
            raise ValueError("notification history identity is required")


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    candidate_id: str
    assessment_id: str
    fingerprint: str
    state_signature: str
    status: NotificationDecisionStatus
    eligible: bool
    meaningful_state_change: bool
    reasons: tuple[str, ...]
    evaluated_at: datetime
    manual_confirmation_required: bool = True
    shadow_run: bool = True

    def __post_init__(self) -> None:
        _aware(self.evaluated_at, "evaluated_at")
        if not all((self.candidate_id, self.assessment_id, self.fingerprint, self.state_signature)):
            raise ValueError("notification decision identity is required")
        if not self.reasons:
            raise ValueError("notification decision reasons are required")
        if not self.shadow_run:
            raise ValueError("this decision engine is restricted to shadow runs")


@dataclass(frozen=True, slots=True)
class RetryState:
    fingerprint: str
    status: RetryStatus = RetryStatus.PENDING
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: str | None = None

    def __post_init__(self) -> None:
        if not self.fingerprint or self.max_attempts < 1 or self.attempt_count < 0:
            raise ValueError("retry identity and positive limits are required")
        if self.attempt_count > self.max_attempts:
            raise ValueError("attempt count cannot exceed maximum attempts")
        if self.status in {RetryStatus.RETRYABLE, RetryStatus.EXHAUSTED} and not (self.last_error or "").strip():
            raise ValueError("failed retry states require an error")

    def record_failure(self, error: str) -> RetryState:
        if self.status in {RetryStatus.SUCCEEDED, RetryStatus.EXHAUSTED}:
            raise ValueError("terminal retry state cannot transition")
        if not error.strip():
            raise ValueError("retry failure requires an error")
        attempts = self.attempt_count + 1
        status = RetryStatus.EXHAUSTED if attempts >= self.max_attempts else RetryStatus.RETRYABLE
        return replace(self, status=status, attempt_count=attempts, last_error=error)

    def record_success(self) -> RetryState:
        if self.status in {RetryStatus.SUCCEEDED, RetryStatus.EXHAUSTED}:
            raise ValueError("terminal retry state cannot transition")
        return replace(self, status=RetryStatus.SUCCEEDED, attempt_count=self.attempt_count + 1, last_error=None)


class InMemoryNotificationHistory:
    """Deterministic test/shadow adapter; intentionally not durable."""

    def __init__(self) -> None:
        self._records: list[NotificationHistoryRecord] = []

    def add(self, decision: NotificationDecision) -> None:
        self._records.append(
            NotificationHistoryRecord(
                fingerprint=decision.fingerprint,
                state_signature=decision.state_signature,
                candidate_id=decision.candidate_id,
                decided_at=decision.evaluated_at,
                status=decision.status,
            )
        )

    def for_candidate(self, candidate_id: str) -> tuple[NotificationHistoryRecord, ...]:
        return tuple(record for record in self._records if record.candidate_id == candidate_id)


@dataclass(frozen=True, slots=True)
class CandidateNotificationPolicy:
    cooldown: timedelta = timedelta(days=7)
    eligibility: AlertEligibilityPolicy = AlertEligibilityPolicy()

    def __post_init__(self) -> None:
        if self.cooldown < timedelta(0):
            raise ValueError("notification cooldown cannot be negative")

    def evaluate(
        self,
        assessment: ActionAssessment,
        evaluated_at: datetime,
        history: tuple[NotificationHistoryRecord, ...] = (),
        *,
        manual_confirmed: bool = False,
        shadow_run: bool = True,
    ) -> NotificationDecision:
        _aware(evaluated_at, "evaluated_at")
        if not shadow_run:
            raise ValueError("real notification decisions are not enabled")
        if any(record.candidate_id != assessment.candidate_id for record in history):
            raise ValueError("history must belong to the assessed candidate")

        fingerprint = candidate_fingerprint(assessment)
        signature = meaningful_state_signature(assessment)
        prior = tuple(sorted(history, key=lambda item: item.decided_at))
        exact_duplicate = any(item.fingerprint == fingerprint for item in prior)
        latest = prior[-1] if prior else None
        changed = latest is not None and latest.state_signature != signature
        eligibility = self.eligibility.evaluate(assessment, evaluated_at)

        if not eligibility.eligible:
            return self._decision(
                assessment, fingerprint, signature, NotificationDecisionStatus.INELIGIBLE,
                False, changed, eligibility.failed_gates, evaluated_at,
            )
        if exact_duplicate:
            return self._decision(
                assessment, fingerprint, signature, NotificationDecisionStatus.DUPLICATE,
                True, False, ("stable_fingerprint_already_seen",), evaluated_at,
            )
        if latest and evaluated_at < latest.decided_at + self.cooldown and not changed:
            return self._decision(
                assessment, fingerprint, signature, NotificationDecisionStatus.COOLDOWN,
                True, False, ("candidate_cooldown_active",), evaluated_at,
            )
        if not manual_confirmed:
            return self._decision(
                assessment, fingerprint, signature, NotificationDecisionStatus.AWAITING_MANUAL_CONFIRMATION,
                True, changed, ("manual_confirmation_required",), evaluated_at,
            )
        return self._decision(
            assessment, fingerprint, signature, NotificationDecisionStatus.DRY_RUN_READY,
            True, changed, ("eligible_shadow_preview",), evaluated_at,
        )

    @staticmethod
    def _decision(assessment, fingerprint, signature, status, eligible, changed, reasons, evaluated_at):
        return NotificationDecision(
            candidate_id=assessment.candidate_id,
            assessment_id=assessment.assessment_id,
            fingerprint=fingerprint,
            state_signature=signature,
            status=status,
            eligible=eligible,
            meaningful_state_change=changed,
            reasons=tuple(reasons),
            evaluated_at=evaluated_at,
        )


def candidate_fingerprint(assessment: ActionAssessment) -> str:
    """Fingerprint exact research inputs while excluding volatile timestamps."""
    return _digest(
        {
            "candidate_id": assessment.candidate_id,
            "opportunity_version_id": assessment.opportunity_version_id,
            "thesis_version_id": assessment.thesis_version_id,
            "evidence_set_id": assessment.evidence_set_id,
            "market_state_id": assessment.market_state_id,
            "state": _state_payload(assessment),
        }
    )


def meaningful_state_signature(assessment: ActionAssessment) -> str:
    """Fingerprint user-meaningful state, independent of evidence/version churn."""
    return _digest(_state_payload(assessment))


def _state_payload(assessment: ActionAssessment) -> dict[str, object]:
    return {
        "action_level": assessment.action_level.value,
        "research_priority": assessment.research_priority.value,
        "confidence_band": confidence_band(assessment.confidence).value,
        "thesis_status": assessment.thesis_status_snapshot.value,
        "opportunity_status": assessment.opportunity_status_snapshot.value,
        "permanence": assessment.permanence_snapshot.value,
        "market_regime": assessment.market_regime_snapshot.value,
        "evidence_complete": assessment.evidence_complete,
        "mispricing_significant": assessment.mispricing_significant,
    }


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
