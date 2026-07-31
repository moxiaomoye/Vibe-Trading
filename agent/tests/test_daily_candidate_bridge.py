from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.investment_research.contracts import EvidenceDirection, ThesisStatus
from src.investment_research.evidence.models import Evidence, EvidenceSet
from src.investment_research.operations.daily_candidate_bridge import (
    evaluate_daily_candidate,
)
from src.investment_research.operations.reviewed_context import (
    ReviewedResearchContext,
    ReviewedResearchContextResolution,
)
from src.investment_research.thesis.models import (
    ThesisInitializationAudit,
    ThesisVersion,
)


def _asset_report() -> dict:
    return {
        "symbol": "600522.SH",
        "name": "Zhongtian Technology",
        "asset_type": "stock",
        "effective_trade_date": "2026-07-29",
        "latest_close": 20.0,
        "return_60d_pct": -35.0,
        "panic": True,
        "panic_triggers": [
            {
                "code": "ASSET_PANIC",
                "label": "60-day decline exceeded 30%",
                "observed": -35.0,
                "threshold": -30.0,
            }
        ],
        "fundamentals": {
            "period_end": "2025-12-31",
            "notice_date": "2026-03-31",
            "eps": 1.0,
            "revenue_cny": 100.0,
            "net_profit_cny": 10.0,
            "roe_pct": 12.0,
            "gross_margin_pct": 20.0,
            "debt_ratio_pct": 35.0,
            "source": "fixture-filing",
        },
        "sectors": [{"code": "fixture", "name": "communications", "change_pct": -5.0}],
        "news": [],
        "data_source": "fixture-market",
    }


def _market_report() -> dict:
    return {
        "panic": True,
        "regime": "panic",
        "panic_triggers": [
            {
                "code": "MARKET_CRASH",
                "label": "market-wide panic",
                "observed": 1000,
                "threshold": 1000,
            }
        ],
        "shanghai_20d_return_pct": -8.0,
        "shanghai_60d_return_pct": -20.0,
    }


def _reviewed_resolution() -> ReviewedResearchContextResolution:
    cutoff = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
    support = Evidence(
        "reviewed-support", "exchange", "https://example.test/support",
        "Reviewed support", "Primary supporting fact.", EvidenceDirection.NEUTRAL,
        cutoff, cutoff, cutoff, "hash-support",
    )
    counter = Evidence(
        "reviewed-counter", "exchange", "https://example.test/counter",
        "Reviewed counter", "Primary counter fact.", EvidenceDirection.NEUTRAL,
        cutoff, cutoff, cutoff, "hash-counter",
    )
    evidence_set = EvidenceSet(
        "reviewed-set", "thesis:600522.SH", cutoff,
        (support.evidence_id, counter.evidence_id), cutoff,
    )
    thesis = ThesisVersion(
        "reviewed-version", "thesis:600522.SH", 1, ThesisStatus.ACTIVE,
        "The reviewed issuer Thesis remains intact.", 0.82, evidence_set.evidence_set_id,
        (support.evidence_id,), (counter.evidence_id,), ("next filing",),
        ("structural cash-flow deterioration",), "Approved initialization.", cutoff,
        cutoff + timedelta(days=30),
    )
    audit = ThesisInitializationAudit(
        thesis.thesis_version_id, "chief-analyst", "approval://review/1",
        "review-1", cutoff,
    )
    return ReviewedResearchContextResolution(
        ReviewedResearchContext(thesis, evidence_set, (support, counter), audit)
    )


def test_automatic_inputs_use_formal_pipeline_but_cannot_initialize_thesis():
    result = evaluate_daily_candidate(
        definition={
            "symbol": "600522.SH",
            "name": "Zhongtian Technology",
            "asset_type": "stock",
            "valuation": {"bear_pe": 15.0, "base_pe": 22.0, "bull_pe": 30.0},
        },
        asset_report=_asset_report(),
        market_report=_market_report(),
        report_date=date(2026, 7, 29),
    )

    assert result["decision_source"] == "PanicMispricingResearchPipeline"
    assert result["quality_status"] == "partial"
    assert result["valuation_status"] == "provisional"
    assert result["thesis_status"] == "draft"
    assert result["thesis_initialized"] is False
    assert result["action_level"] == "watch"
    assert "temporary_cause_not_established" in result["blocked_reasons"]


def test_bridge_is_deterministic_for_identical_point_in_time_inputs():
    arguments = {
        "definition": {
            "symbol": "600522.SH",
            "name": "Zhongtian Technology",
            "asset_type": "stock",
            "valuation": {"bear_pe": 15.0, "base_pe": 22.0, "bull_pe": 30.0},
        },
        "asset_report": _asset_report(),
        "market_report": _market_report(),
        "report_date": date(2026, 7, 29),
    }
    assert evaluate_daily_candidate(**arguments) == evaluate_daily_candidate(**arguments)


def test_bridge_uses_reviewed_thesis_and_exact_evidence_set():
    result = evaluate_daily_candidate(
        definition={
            "symbol": "600522.SH",
            "name": "Zhongtian Technology",
            "asset_type": "stock",
            "thesis_id": "thesis:600522.SH",
            "valuation": {"bear_pe": 15.0, "base_pe": 22.0, "bull_pe": 30.0},
        },
        asset_report=_asset_report(),
        market_report=_market_report(),
        report_date=date(2026, 7, 29),
        reviewed_context=_reviewed_resolution(),
    )

    assert result["thesis_initialized"] is True
    assert result["thesis_status"] == "active"
    assert result["thesis_version_id"] == "reviewed-version"
    assert result["thesis_core_claim"] == "The reviewed issuer Thesis remains intact."
    assert [item["evidence_id"] for item in result["supporting_evidence"]] == [
        "reviewed-support"
    ]
    assert [item["direction"] for item in result["counter_evidence"]] == ["counter"]
    assert result["action_level"] == "watch"
    assert "temporary_cause_not_established" in result["blocked_reasons"]
