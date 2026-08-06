"""Market state reconciliation (RRV-RELIABILITY-CLOSURE-001).

Versioned reconciliation between the legacy market state (Value Hunter
panic score) and the evidence-gated Market Intelligence state. The effective
state is the more severe of the two only when the intelligence coverage gate
passes; otherwise the legacy state stands. The intelligence state can never
downgrade the legacy state, so the top-level ``market_state`` contract key
keeps its legacy meaning and the reconciliation is carried in separate
explicit fields.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .market_intelligence import MarketIntelligence, MarketState
from .data_quality import DataQualityStatus

RECONCILIATION_VERSION = "market-state-reconciliation-v1"

_LEGACY_SEVERITY = {
    "NORMAL": 0,
    "CAUTION": 1,
    "STRESS": 1,
    "PANIC": 2,
    "EXTREME_PANIC": 3,
    "UNKNOWN": 0,
}


class MarketStateReconciliation(BaseModel):
    """Explicit reconciliation record attached to every research report."""

    version: str = RECONCILIATION_VERSION
    legacy_market_state: str
    intelligence_state: str
    effective_market_state: str
    coverage_gate_passed: bool
    coverage_available_dimensions: int
    coverage_has_index_or_breadth: bool
    coverage_has_available_trigger: bool
    upgraded: bool
    reasons: list[str] = Field(default_factory=list)

    def to_report_block(self) -> dict[str, Any]:
        """Deterministic block appended to the report payload."""
        return {
            "legacy_market_state": self.legacy_market_state,
            "effective_market_state": self.effective_market_state,
            "intelligence_state": self.intelligence_state,
            "coverage_gate_passed": self.coverage_gate_passed,
            "coverage": {
                "available_dimensions": self.coverage_available_dimensions,
                "has_index_or_breadth": self.coverage_has_index_or_breadth,
                "has_available_trigger": self.coverage_has_available_trigger,
            },
            "upgraded": self.upgraded,
            "reasons": list(self.reasons),
        }


def coverage_gate(intel: MarketIntelligence) -> dict[str, Any]:
    """Evaluate the evidence gate over the intelligence verdicts.

    Gate rules (frozen, see the closure spec): the intelligence state must be
    decidable (not ``UNKNOWN``), at least two dimensions must be
    ``AVAILABLE``, at least one of ``INDEX``/``BREADTH`` must be available,
    and at least one available dimension must actually be triggered. An
    ``ESTIMATED`` trigger never satisfies the gate on its own.
    """
    verdicts = intel.dimensions
    available = [
        verdict for verdict in verdicts
        if verdict.status is DataQualityStatus.AVAILABLE
    ]
    triggered = [
        verdict for verdict in available if verdict.triggered
    ]
    has_index_or_breadth = any(
        verdict.dimension.value in ("index", "breadth") for verdict in available
    )
    passed = (
        intel.state is not MarketState.UNKNOWN
        and len(available) >= 2
        and has_index_or_breadth
        and bool(triggered)
    )
    return {
        "passed": passed,
        "available": len(available),
        "has_index_or_breadth": has_index_or_breadth,
        "has_available_trigger": bool(triggered),
    }


def reconcile_market_state(
    legacy_state: str,
    intel: MarketIntelligence | None,
) -> MarketStateReconciliation:
    """Reconcile the legacy state with the intelligence evidence.

    The effective state is ``max(legacy, intelligence)`` when the gate passes
    (intelligence may upgrade, never downgrade); otherwise the legacy state is
    kept. ``intel=None`` (no snapshot) leaves the legacy state untouched with
    a visible reason.
    """
    reasons: list[str] = []
    if intel is None:
        return MarketStateReconciliation(
            legacy_market_state=legacy_state,
            intelligence_state="UNKNOWN",
            effective_market_state=legacy_state,
            coverage_gate_passed=False,
            coverage_available_dimensions=0,
            coverage_has_index_or_breadth=False,
            coverage_has_available_trigger=False,
            upgraded=False,
            reasons=["market intelligence unavailable: context carried no snapshot"],
        )
    gate = coverage_gate(intel)
    intel_state = intel.state.value
    legacy_level = _LEGACY_SEVERITY.get(legacy_state, 0)
    intel_level = _LEGACY_SEVERITY.get(intel_state, 0)
    upgraded = bool(gate["passed"]) and intel_level > legacy_level
    effective = intel_state if upgraded else legacy_state
    if upgraded:
        reasons.append(
            f"intelligence state {intel_state} is more severe than legacy "
            f"{legacy_state} and the coverage gate passed"
        )
    elif not gate["passed"]:
        reasons.append("coverage gate not passed: intelligence evidence cannot override legacy state")
    else:
        reasons.append("intelligence state does not exceed legacy state")
    if intel_state == "UNKNOWN":
        reasons.append("intelligence state UNKNOWN: no sufficient evidence at the point in time")
    return MarketStateReconciliation(
        legacy_market_state=legacy_state,
        intelligence_state=intel_state,
        effective_market_state=effective,
        coverage_gate_passed=bool(gate["passed"]),
        coverage_available_dimensions=gate["available"],
        coverage_has_index_or_breadth=gate["has_index_or_breadth"],
        coverage_has_available_trigger=gate["has_available_trigger"],
        upgraded=upgraded,
        reasons=reasons,
    )
