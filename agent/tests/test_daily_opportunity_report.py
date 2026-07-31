from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.investment_research.operations.daily_opportunity_report import (
    DailyOpportunityReportService,
)
from src.investment_research.operations.report_storage import ReportStorage
from src.value_hunter.models import MarketObservation


TODAY = date(2026, 7, 29)


def _no_research_enrichment(_symbol: str) -> dict:
    return {
        "financials": None,
        "margin": None,
        "fund_flow": None,
        "sectors": [],
        "news": [],
        "data_gaps": [],
        "sources": {},
    }


def _records(*, start: float, daily_change: float) -> list[dict]:
    first = TODAY - timedelta(days=100)
    rows = []
    price = start
    for offset in range(70):
        rows.append({"trade_date": (first + timedelta(days=offset)).isoformat(), "close": price})
        price += daily_change
    return rows


def _fetcher(**kwargs):
    assert kwargs["source"] == "auto"
    return {
        "600522.SH": _records(start=100.0, daily_change=-0.6),
        "588000.SH": _records(start=1.0, daily_change=-0.005),
        "000001.SH": _records(start=3400.0, daily_change=-4.0),
        "512800.SH": _records(start=1.0, daily_change=0.001),
    }


def _market(limit_down_count: int = 1000) -> MarketObservation:
    return MarketObservation(
        as_of=TODAY.isoformat(),
        indices=[],
        advancer_ratio=None,
        above_ma60_ratio=None,
        limit_down_count=limit_down_count,
        turnover_zscore=None,
        source="fixture-market",
        coverage=["limit_down"],
    )


def test_daily_report_combines_all_three_user_panic_rules(tmp_path):
    service = DailyOpportunityReportService(
        market_fetcher=_fetcher,
        market_context_loader=lambda: _market(1000),
        research_enricher=_no_research_enrichment,
        storage=ReportStorage(tmp_path),
        today=lambda: TODAY,
        now=lambda: datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc),
    )

    report = service.run()

    assert report["market"]["shanghai_60d_point_change"] == -240.0
    assert report["market"]["limit_down_count"] == 1000
    assert report["report_version"] == "2.0"
    assert report["market"]["style_rotation"]["bank_proxy"] == "512800.SH"
    assert [item["symbol"] for item in report["assets"]] == ["600522.SH", "588000.SH"]
    assert all(item["action_level"] == "watch" for item in report["assets"])
    assert all(
        item["formal_research"]["decision_source"] == "PanicMispricingResearchPipeline"
        for item in report["assets"]
    )
    assert all(item["formal_research"]["thesis_initialized"] is False for item in report["assets"])
    assert all("evidence_incomplete" in item["formal_research"]["blocked_reasons"] for item in report["assets"])
    assert all(item["formal_research"]["action_level"] == item["action_level"] for item in report["assets"])
    assert all(len(item["panic_triggers"]) == 3 for item in report["assets"])
    assert all(item["technical"]["rsi14"] is not None for item in report["assets"])
    assert all(item["entry_framework"]["status"] == "wait" for item in report["assets"])
    assert "agent_prompt" in report
    assert report["notifications_sent"] is False
    assert report["scheduler_started"] is False
    assert report["trading_executed"] is False
    assert service.latest()["_fingerprint"] == report["_fingerprint"]

    repeated = service.run()
    assert repeated["assets"] == report["assets"]


def test_daily_report_is_still_emitted_without_panic(tmp_path):
    def stable_fetcher(**kwargs):
        return {
            "600522.SH": _records(start=100.0, daily_change=0.1),
            "588000.SH": _records(start=1.0, daily_change=0.001),
            "000001.SH": _records(start=3000.0, daily_change=1.0),
            "512800.SH": _records(start=1.0, daily_change=0.001),
        }

    service = DailyOpportunityReportService(
        market_fetcher=stable_fetcher,
        market_context_loader=lambda: _market(10),
        research_enricher=_no_research_enrichment,
        storage=ReportStorage(tmp_path),
        today=lambda: TODAY,
    )

    report = service.run()

    assert report["market"]["panic"] is False
    assert all(item["action_level"] == "watch" for item in report["assets"])
    assert report["conclusion"] == "今天没有标的触发既定恐慌条件，继续观察。"


def test_missing_market_context_does_not_discard_valid_asset_data(tmp_path):
    def fail_context():
        raise ConnectionError("fixture unavailable")

    service = DailyOpportunityReportService(
        market_fetcher=_fetcher,
        market_context_loader=fail_context,
        research_enricher=_no_research_enrichment,
        storage=ReportStorage(tmp_path),
        today=lambda: TODAY,
    )

    report = service.run()

    assert len(report["assets"]) == 2
    assert report["market"]["limit_down_count"] is None
    assert any("跌停数量不可用" in gap for gap in report["data_gaps"])
