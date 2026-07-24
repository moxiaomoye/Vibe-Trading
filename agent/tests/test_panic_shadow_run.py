from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pandas as pd

from src.investment_research.application.panic_orchestration import (
    OrchestrationRequest,
    OrchestrationStatus,
)
from src.investment_research.application.panic_research_pipeline import ResearchCase, ResearchPipelinePolicy
from src.investment_research.application.shadow_run import (
    PanicResearchShadowRunner,
    ShadowCandidateInput,
    ShadowRunConfig,
    ShadowRunInputs,
)
from src.investment_research.assets.models import Asset, ThesisExposure
from src.investment_research.contracts import (
    ActionLevel,
    AssetType,
    EvidenceDirection,
    Permanence,
    ThesisStatus,
)
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.mispricing.attribution import (
    AttributionPolicy,
    DateSafeAttributionEngine,
    EventDirection,
    EventType,
    PriceMoveContext,
    ResearchEvent,
)
from src.investment_research.mispricing.models import PermanenceAssessment
from src.investment_research.operations.notification_decision import NotificationDecisionStatus
from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.thesis.models import ThesisVersion
from src.investment_research.valuation import (
    AssumptionStatus,
    CompanyQualityEngine,
    FinancialObservation,
    ScenarioAssumption,
    ScenarioValuationEngine,
    ValuationAssumptions,
    ValuationMethod,
)


TRADE_DATE = date(2026, 7, 22)
NOW = datetime(2026, 7, 22, 10, 31, tzinfo=timezone.utc)
ASSET_ID = "asset-600522"
EVIDENCE_SET_ID = "issuer-evidence-v1"


def _watchlist(tmp_path):
    path = tmp_path / "watchlist.yaml"
    path.write_text(
        'version: "shadow-v1"\nwatchlist:\n  name: "fixture"\n  symbols:\n    - "600522.SH"\n',
        encoding="utf-8",
    )
    return str(path)


def _panel(*, panic=True):
    count = 120
    codes = ["600522"] + [f"000{i:03d}" for i in range(1, count)]
    changes = ([-6.0] * 114 + [1.0] * 6) if panic else ([1.0] * 72 + [-1.0] * 48)
    return {
        "spot_df": pd.DataFrame(
            {
                "代码": codes,
                "名称": ["fixture"] * count,
                "最新价": [94.0] + [10.0] * (count - 1),
                "涨跌幅": changes,
                "昨收": [100.0] + [10.0] * (count - 1),
            }
        ),
        "limit_up_symbols": [],
        "limit_down_symbols": codes if panic else [],
        "data_date": TRADE_DATE,
        "availability_date": TRADE_DATE,
        "now": NOW - timedelta(minutes=1),
        "market_change_pct": -0.05 if panic else 0.002,
        "source": "deterministic-fixture",
    }


def _evidence(evidence_id, direction):
    return Evidence(
        evidence_id, "fixture", f"fixture://{evidence_id}", evidence_id,
        "point-in-time fixture evidence", direction,
        NOW - timedelta(hours=2), NOW - timedelta(hours=1), NOW,
        f"hash-{evidence_id}",
    )


def _candidate(*, severe_gaps=False, company_event=False, structural=False):
    evidence = (
        _evidence("support", EvidenceDirection.SUPPORTING),
        _evidence("counter", EvidenceDirection.COUNTER),
        _evidence("market-price", EvidenceDirection.NEUTRAL),
    )
    evidence_set = EvidenceSet(
        EVIDENCE_SET_ID, "thesis-ai", NOW,
        tuple(item.evidence_id for item in evidence), NOW,
    )
    asset = Asset(ASSET_ID, "600522.SH", "fixture", AssetType.STOCK, "CN", "CNY", NOW)
    thesis = ThesisVersion(
        "thesis-ai-v1", "thesis-ai", 1, ThesisStatus.ACTIVE,
        "AI infrastructure demand remains intact", 0.92, EVIDENCE_SET_ID,
        ("support",), ("counter",), ("capex",), ("demand invalidation",),
        "fixture", NOW - timedelta(days=30), NOW + timedelta(days=30),
    )
    exposure = ThesisExposure(
        "exposure-v1", ASSET_ID, "thesis-ai", thesis.thesis_version_id,
        EVIDENCE_SET_ID, 0.9, 0.8, "direct exposure", NOW - timedelta(days=1),
    )
    observations = () if severe_gaps else (
        FinancialObservation(
            ASSET_ID, date(2023, 12, 31), datetime(2024, 3, 31, tzinfo=timezone.utc),
            "fixture", Decimal("100"), Decimal("10"), Decimal("0.40"), Decimal("0.15"),
            Decimal("11"), Decimal("0.25"),
        ),
        FinancialObservation(
            ASSET_ID, date(2024, 12, 31), datetime(2025, 3, 31, tzinfo=timezone.utc),
            "fixture", Decimal("120"), Decimal("12"), Decimal("0.42"), Decimal("0.16"),
            Decimal("13"), Decimal("0.23"),
        ),
    )
    quality = CompanyQualityEngine().assess(
        asset_id=ASSET_ID, observations=observations, information_cutoff=NOW
    )
    assumptions = None if severe_gaps else ValuationAssumptions(
        ASSET_ID, Decimal("100"), Decimal("5"), 2, ValuationMethod.FORWARD_PE,
        (
            ScenarioAssumption("bear", Decimal("-0.05"), Decimal("14")),
            ScenarioAssumption("base", Decimal("0.15"), Decimal("20")),
            ScenarioAssumption("bull", Decimal("0.25"), Decimal("26")),
        ),
        NOW.date(), NOW, "fixture-v1", ("earnings invalidated",), AssumptionStatus.APPROVED,
        "fixture approval",
    )
    valuation = ScenarioValuationEngine().evaluate(
        asset_id=ASSET_ID, information_cutoff=NOW, assumptions=assumptions
    )
    event = ResearchEvent(
        "company-warning", EventType.EARNINGS_WARNING, "fixture", NOW - timedelta(hours=3),
        NOW - timedelta(hours=2), 1.0, EventDirection.NEGATIVE, 0.9, 0.9,
        ("counter",), (), ("duration unknown",), asset_id=ASSET_ID,
    )
    price_context = PriceMoveContext(
        ASSET_ID, "semiconductor", NOW - timedelta(days=2), NOW,
        -0.10, 0.01 if company_event else -0.09, 0.01 if company_event else -0.08,
        "market-price", "market-price", "market-price",
    )
    attribution = DateSafeAttributionEngine().evaluate(
        context=price_context, events=(event,) if company_event else (), information_cutoff=NOW,
        policy=AttributionPolicy("attribution-v1", 0.02, 0.02, 0.65),
    )
    permanence = PermanenceAssessment(
        "permanence-v1", EVIDENCE_SET_ID,
        Permanence.STRUCTURAL if structural else Permanence.TEMPORARY,
        "fixture permanence review", ("support",), ("counter",) if structural else (), (),
        0.9, NOW,
    )
    research_case = ResearchCase(
        "price may overdiscount temporary weakness", "long-term evidence differs", "market panic",
        ("persistent decline",), ("balance sheet",), ("temporary slowdown",),
        ("support", "market-price"), ("counter",), ("structural slowdown",), ("demand",),
        ("next filing",), ("demand stabilization",), ("structural impairment",),
        "Is demand structurally impaired?", 0.91, NOW + timedelta(days=14),
    )
    return ShadowCandidateInput(
        "600522.SH", asset, thesis, exposure, evidence_set, evidence, quality, valuation,
        attribution, permanence, research_case,
        ResearchPipelinePolicy("pipeline-v1", 0.10, 0.85, 0.5, 0.4, 0.49),
    )


def _inputs(tmp_path, *, panic=True, candidate=None):
    return ShadowRunInputs(
        _panel(panic=panic), _watchlist(tmp_path), NOW,
        (_candidate() if candidate is None else candidate,),
    )


def _runner():
    return PanicResearchShadowRunner(
        ShadowRunConfig(
            enabled=True,
            schedule=TradingDaySchedule(run_after=time(18, 30)),
        )
    )


def _request(run_id="run-1"):
    return OrchestrationRequest(run_id, NOW, TRADE_DATE, NOW - timedelta(minutes=1))


def test_normal_market_produces_no_research_candidate(tmp_path) -> None:
    report = _runner().run(_request(), _inputs(tmp_path, panic=False)).output
    assert report.market_regime.value == "normal"
    assert report.candidates == ()
    assert report.to_dict()["research_candidates"] == []


def test_panic_market_builds_candidate_and_notification_preview(tmp_path) -> None:
    result = _runner().run(_request(), _inputs(tmp_path))
    assert result.status == OrchestrationStatus.SUCCEEDED
    report = result.output
    assert report.shadow_run is True
    assert report.market_regime.value == "panic"
    candidate = report.candidates[0]
    assert candidate.pipeline.assessment.action_level == ActionLevel.ACTION_CANDIDATE
    assert candidate.notification.status == NotificationDecisionStatus.AWAITING_MANUAL_CONFIRMATION
    exported = report.to_dict()
    assert exported["manual_review_required"] is True
    assert exported["versions"]["panic_rule"]


def test_company_specific_structural_event_and_severe_gaps_suppress_action(tmp_path) -> None:
    structural = _runner().run(
        _request(), _inputs(tmp_path, candidate=_candidate(company_event=True, structural=True))
    ).output.candidates[0]
    assert structural.pipeline.attribution.scope.value == "company_specific"
    assert structural.pipeline.assessment.action_level == ActionLevel.WATCH
    assert structural.notification.status == NotificationDecisionStatus.INELIGIBLE

    gaps = _runner().run(
        _request(), _inputs(tmp_path, candidate=_candidate(severe_gaps=True))
    ).output.candidates[0]
    assert gaps.pipeline.assessment.action_level == ActionLevel.WATCH
    assert "quality_unconfigured" in gaps.pipeline.blocked_reasons
    assert "valuation_unconfigured" in gaps.pipeline.blocked_reasons


def test_future_evidence_is_rejected_without_lookahead(tmp_path) -> None:
    candidate = _candidate()
    future = replace(
        candidate.evidence[0], available_at=NOW + timedelta(minutes=1),
        observed_at=NOW + timedelta(minutes=1),
    )
    result = _runner().run(
        _request(), _inputs(tmp_path, candidate=replace(candidate, evidence=(future, *candidate.evidence[1:])))
    )
    assert result.status == OrchestrationStatus.FAILED
    assert "future" in result.error or "unavailable" in result.error


def test_repeated_run_is_idempotent_and_state_change_changes_notification(tmp_path) -> None:
    runner = _runner()
    inputs = _inputs(tmp_path)
    first = runner.run(_request(), inputs)
    repeated = runner.run(_request("run-2"), inputs)
    assert first.status == OrchestrationStatus.SUCCEEDED
    assert repeated.status == OrchestrationStatus.DUPLICATE

    changed = runner.evaluate(_inputs(tmp_path, candidate=_candidate(company_event=True, structural=True)))
    decision = changed.candidates[0].notification
    assert decision.status == NotificationDecisionStatus.INELIGIBLE
    assert decision.meaningful_state_change is True
