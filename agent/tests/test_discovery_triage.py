from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.assets.models import Asset, ThesisExposure
from src.investment_research.contracts import AssetType, ThesisStatus
from src.investment_research.discovery.models import DiscoveryDisposition, FundamentalIntegrity, ResearchSnapshot
from src.investment_research.discovery.triage import MispricingDiscoveryTriage
from src.investment_research.thesis.models import ThesisVersion


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _asset() -> Asset:
    return Asset("asset-1", "ETF-1", "AI Infrastructure ETF", AssetType.ETF, "CN", "CNY", NOW)


def _thesis(status: ThesisStatus = ThesisStatus.ACTIVE) -> ThesisVersion:
    return ThesisVersion(
        "thesis-version-1", "thesis-ai", 1, status, "AI infrastructure demand remains durable.", 0.8,
        "evidence-set-1", ("support-1",), ("counter-1",), ("capex",), ("capex contraction",),
        "initial", NOW, NOW + timedelta(days=30),
    )


def _exposure() -> ThesisExposure:
    return ThesisExposure(
        "exposure-1", "asset-1", "thesis-ai", "thesis-version-1", "exposure-evidence", 0.8, 0.7,
        "Holdings have direct AI infrastructure exposure.", NOW,
    )


def _snapshot() -> ResearchSnapshot:
    return ResearchSnapshot(
        "snapshot-1", "asset-1", "thesis-version-1", "snapshot-evidence", NOW,
        -0.35, -0.15, 0.2, FundamentalIntegrity.INTACT,
        ("fundamental-1",), ("attribution-1",), ("counter-1",),
    )


def test_complete_lead_reaches_opportunity_review_not_a_recommendation() -> None:
    lead = MispricingDiscoveryTriage().evaluate(_asset(), _thesis(), _exposure(), _snapshot())
    assert lead.disposition == DiscoveryDisposition.OPPORTUNITY_REVIEW
    assert "temporary mispricing" in lead.first_rejection_question


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (replace(_snapshot(), attribution_evidence_ids=()), DiscoveryDisposition.ATTRIBUTION_REQUIRED),
        (replace(_snapshot(), counter_evidence_ids=()), DiscoveryDisposition.EVIDENCE_GAP),
        (
            replace(_snapshot(), fundamental_integrity=FundamentalIntegrity.UNKNOWN, fundamental_evidence_ids=()),
            DiscoveryDisposition.EVIDENCE_GAP,
        ),
        (replace(_snapshot(), drawdown_from_reference=-0.05, sector_excess_return=-0.02), DiscoveryDisposition.REJECTED),
        (replace(_snapshot(), fundamental_integrity=FundamentalIntegrity.DETERIORATING), DiscoveryDisposition.REJECTED),
        (replace(_snapshot(), severe_risk_flags=("regulatory_investigation",)), DiscoveryDisposition.REJECTED),
    ],
)
def test_discovery_gates_explain_why_a_lead_does_not_advance(snapshot, expected: DiscoveryDisposition) -> None:
    lead = MispricingDiscoveryTriage().evaluate(_asset(), _thesis(), _exposure(), snapshot)
    assert lead.disposition == expected
    assert lead.reasons


def test_invalidated_thesis_and_unproven_exposure_are_rejected() -> None:
    triage = MispricingDiscoveryTriage()
    assert triage.evaluate(_asset(), _thesis(ThesisStatus.INVALIDATED), _exposure(), _snapshot()).disposition == DiscoveryDisposition.REJECTED
    weak_exposure = replace(_exposure(), exposure_strength=0.3)
    assert triage.evaluate(_asset(), _thesis(), weak_exposure, _snapshot()).disposition == DiscoveryDisposition.REJECTED


def test_discovery_is_point_in_time_and_identity_consistent() -> None:
    triage = MispricingDiscoveryTriage()
    with pytest.raises(ValueError, match="asset"):
        triage.evaluate(replace(_asset(), asset_id="other"), _thesis(), _exposure(), _snapshot())
    with pytest.raises(ValueError, match="thesis-version"):
        triage.evaluate(_asset(), replace(_thesis(), thesis_version_id="other"), _exposure(), _snapshot())
    with pytest.raises(ValueError, match="future"):
        triage.evaluate(_asset(), _thesis(), replace(_exposure(), as_of=NOW + timedelta(minutes=1)), _snapshot())


def test_lead_identity_is_deterministic_for_idempotent_daily_discovery() -> None:
    triage = MispricingDiscoveryTriage()
    first = triage.evaluate(_asset(), _thesis(), _exposure(), _snapshot())
    second = triage.evaluate(_asset(), _thesis(), _exposure(), _snapshot())
    assert first.lead_id == second.lead_id
