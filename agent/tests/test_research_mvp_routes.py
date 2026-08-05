from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api import research_mvp_routes
from src.investment_research.application.research_mvp import build_historical_evaluation
from src.investment_research.application.research_mvp import prepare_feishu_delivery
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository
from src.value_hunter.config import ValueHunterConfig
from src.value_hunter.providers import DemoProvider
from src.value_hunter.service import ValueHunterService
from src.value_hunter.store import ValueHunterStore


def _service(tmp_path) -> ValueHunterService:
    config = ValueHunterConfig(
        enabled=False, provider="demo", schedule="18:10", timezone="Asia/Shanghai",
        market_alert_score=70, candidate_alert_score=75, max_candidates=5,
        database_path=tmp_path / "research-mvp.sqlite3", watchlist_path=None,
        feishu_webhook_url="", smtp_host="", smtp_port=465, smtp_username="",
        smtp_password="", smtp_from="", email_to="", notify_on_demo=False,
    )
    return ValueHunterService(config, DemoProvider(), ValueHunterStore(config.database_path))


def test_research_run_reuses_value_hunter_and_returns_unified_contract(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(research_mvp_routes, "get_research_scan_service", lambda: service)
    app = FastAPI()
    research_mvp_routes.register_research_mvp_routes(app, lambda: None)

    response = TestClient(app).post("/investment-research/research-run")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "trade_date", "market_state", "panic_sensitivity", "market_summary",
        "candidates", "data_gaps",
    }
    assert body["trade_date"] == "2024-02-05"
    assert body["market_state"] == "EXTREME_PANIC"
    assert body["panic_sensitivity"]["value"] == 50
    assert body["panic_sensitivity"]["required_confirmations"] == 2
    assert body["panic_sensitivity"]["trigger_count"] == 3
    assert body["market_summary"]["limit_down"] == 170
    assert "turnover_amount" in body["market_summary"]
    assert len(body["market_summary"]["watchlist_scan"]) == 4
    assert sum(item["selected"] for item in body["market_summary"]["watchlist_scan"]) == 3
    assert "market_summary.turnover_amount" in body["data_gaps"]
    assert len(body["candidates"]) == 3
    assert body["candidates"][0]["code"] == "688001.SH"
    assert "market_data_source" in body["candidates"][0]["data_gaps"]
    assert set(body["candidates"][0]["research_plan"]) == {
        "observation_conditions", "risk_conditions", "validation_conditions"
    }
    assert set(body["candidates"][0]["entry_reasons"]) == {"market", "company", "valuation"}
    assert body["candidates"][0]["catalysts"]
    assert body["candidates"][0]["forward_validation"] == {
        "t5": None, "t20": None, "t60": None,
    }
    assert service.history(1)[0]["mode"] == "demo"
    stored_profile = service.history(1)[0]["research_context"]["panic_sensitivity"]
    assert stored_profile["value"] == 50
    assert stored_profile["trigger_count"] == 3


def test_research_run_applies_requested_panic_sensitivity(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(research_mvp_routes, "get_research_scan_service", lambda: service)
    app = FastAPI()
    research_mvp_routes.register_research_mvp_routes(app, lambda: None)

    response = TestClient(app).post(
        "/investment-research/research-run",
        json={"panic_sensitivity": 100},
    )

    assert response.status_code == 200
    profile = response.json()["panic_sensitivity"]
    assert profile["label"] == "严谨"
    assert profile["required_confirmations"] == 3
    assert profile["min_limit_down_count"] == 80


def test_research_run_rejects_out_of_range_sensitivity(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        research_mvp_routes,
        "get_research_scan_service",
        lambda: _service(tmp_path),
    )
    app = FastAPI()
    research_mvp_routes.register_research_mvp_routes(app, lambda: None)

    response = TestClient(app).post(
        "/investment-research/research-run",
        json={"panic_sensitivity": 101},
    )

    assert response.status_code == 422


def test_historical_evaluation_uses_stored_snapshot_and_trading_session_horizons(tmp_path) -> None:
    service = _service(tmp_path)
    service.run(notify=False)

    def prices(**kwargs):
        assert kwargs["start_date"] == "2024-02-05"
        rows = [
            {"date": f"2024-02-{day:02d}", "close": 100 + index}
            for index, day in enumerate(range(5, 29))
        ] + [
            {"date": f"2024-03-{day:02d}", "close": 124 + index}
            for index, day in enumerate(range(1, 32))
        ] + [
            {"date": f"2024-04-{day:02d}", "close": 155 + index}
            for index, day in enumerate(range(1, 12))
        ]
        return {symbol: rows for symbol in kwargs["codes"]}

    result = build_historical_evaluation(service, __import__("datetime").date(2024, 2, 5), prices)

    assert result["market_state"] == "EXTREME_PANIC"
    assert result["panic_sensitivity"] is None
    assert "panic_sensitivity_snapshot" in result["data_gaps"]
    assert result["candidates"][0]["t5"] == 5.0
    assert result["candidates"][0]["t20"] == 20.0
    assert result["candidates"][0]["t60"] == 60.0
    assert result["candidates"][0]["t20_max_drawdown"] == 0.0
    assert result["candidates"][0]["t20_excess"] == 0.0
    assert result["candidates"][0]["t20_outcome"] == "不确定"


def test_historical_evaluation_rebuilds_missing_snapshot_from_published_data(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    from src.value_hunter.models import CandidateObservation, IndexObservation, MarketObservation

    class StubHistoricalProvider:
        name = "akshare-historical"
        as_of = __import__("datetime").date(2025, 4, 7)

        def load_market(self):
            return MarketObservation(
                as_of="2025-04-07",
                indices=[IndexObservation(
                    "000300.SH", "沪深300", 3589.44, -7.05, -15.7, True, True,
                )],
                advancer_ratio=0.0, above_ma60_ratio=0.0, limit_down_count=None,
                turnover_zscore=None, source="stub-historical",
                coverage=["indices", "watchlist_breadth"],
                warnings=["历史回溯：跌停数量为Data Gap"],
            )

        def load_candidates(self):
            return [CandidateObservation(
                "601991.SH", "大唐发电", "电力", "火电与新能源",
                roe_5y_median_pct=8.0, operating_cashflow_to_profit=0.5,
                pe_history_percentile=0.0, revenue_growth_pct=5.0,
                profit_growth_pct=3.0, drawdown_252_pct=-30.0,
                daily_return_pct=-5.0, return_20d_pct=-10.0, return_60d_pct=-15.0,
                volume_ratio_20d=2.0, relative_to_market_pct=-2.0,
                catalyst_evidence=["测试催化剂"], source_fields=["stub"],
            )]

    monkeypatch.setattr(
        "src.value_hunter.providers.build_provider",
        lambda *args, **kwargs: StubHistoricalProvider(),
    )

    def prices(**kwargs):
        return {
            symbol: [
                {"date": f"2025-04-{day:02d}", "close": 100 + index}
                for index, day in enumerate(range(7, 28))
            ]
            for symbol in kwargs["codes"]
        }

    result = build_historical_evaluation(
        service, __import__("datetime").date(2025, 4, 7), prices
    )

    assert result["rebuilt"] is True
    assert result["market_state"] == "PANIC"
    assert result["panic_sensitivity"]["trigger_count"] >= 1
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["t5"] == 5.0
    assert result["candidates"][0]["t20"] == 20.0
    assert result["candidates"][0]["t60"] is None
    assert result["candidates"][0]["selection_reasons"]
    stored = service.history(200)
    assert any(
        item["market"]["observation"]["as_of"] == "2025-04-07" for item in stored
    )
    assert stored[0]["mode"] == "akshare-historical"


def test_feishu_preview_defaults_to_no_send_and_confirmation_queues_once(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "outbox.sqlite3")
    report = {
        "trade_date": "2026-07-24", "market_state": "PANIC", "market_summary": {},
        "candidates": [{"score": 82, "research_status": "A - 深入研究"}],
    }

    preview = prepare_feishu_delivery(report, repository)
    assert preview["status"] == "preview"
    assert preview["send"] is False
    assert preview["scheduler"] is False
    assert preview["eligible"] is True

    queued = prepare_feishu_delivery(report, repository, send=True, confirmed=True)
    duplicate = prepare_feishu_delivery(report, repository, send=True, confirmed=True)
    assert queued["status"] == "queued"
    assert duplicate["status"] == "already_queued"
    assert repository.get_message(queued["message_id"]).body == preview["preview"]


def test_feishu_confirmation_rejects_non_panic_or_low_quality_report(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "outbox.sqlite3")
    report = {
        "trade_date": "2026-07-24", "market_state": "NORMAL", "market_summary": {},
        "candidates": [{"score": 90, "research_status": "A - 深入研究"}],
    }

    preview = prepare_feishu_delivery(report, repository)

    assert preview["eligible"] is False
    with pytest.raises(ValueError, match="PANIC"):
        prepare_feishu_delivery(report, repository, send=True, confirmed=True)


def test_feishu_confirmation_dispatches_the_confirmed_outbox_message(tmp_path, monkeypatch) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "outbox.sqlite3")
    report = {
        "trade_date": "2026-07-24", "market_state": "PANIC", "market_summary": {},
        "candidates": [{"score": 82, "research_status": "A - 深入研究"}],
    }
    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(research_mvp_routes, "get_research_outbox_repository", lambda: repository)
    monkeypatch.setattr(
        research_mvp_routes,
        "get_research_feishu_webhook_url",
        lambda: "https://open.feishu.cn/open-apis/bot/v2/hook/fixture",
    )

    def dispatch(_repository, message_id, webhook_url):
        dispatched.append((message_id, webhook_url))
        return {"status": "delivered"}

    monkeypatch.setattr(research_mvp_routes, "dispatch_feishu_message", dispatch)
    app = FastAPI()
    research_mvp_routes.register_research_mvp_routes(app, lambda: None)

    response = TestClient(app).post(
        "/investment-research/feishu-preview",
        json={"report": report, "send": True, "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "delivered"
    assert dispatched == [
        (
            response.json()["message_id"],
            "https://open.feishu.cn/open-apis/bot/v2/hook/fixture",
        )
    ]
