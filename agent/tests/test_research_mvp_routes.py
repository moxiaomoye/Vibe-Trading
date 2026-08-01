from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    assert set(body) == {"trade_date", "market_state", "market_summary", "candidates", "data_gaps"}
    assert body["trade_date"] == "2024-02-05"
    assert body["market_state"] == "EXTREME_PANIC"
    assert body["market_summary"]["limit_down"] == 170
    assert "turnover_amount" in body["market_summary"]
    assert "market_summary.turnover_amount" in body["data_gaps"]
    assert len(body["candidates"]) == 3
    assert body["candidates"][0]["code"] == "688001.SH"
    assert "market_data_source" in body["candidates"][0]["data_gaps"]
    assert set(body["candidates"][0]["research_plan"]) == {
        "observation_conditions", "risk_conditions", "validation_conditions"
    }
    assert service.history(1)[0]["mode"] == "demo"


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
    assert result["candidates"][0]["t5"] == 5.0
    assert result["candidates"][0]["t20"] == 20.0
    assert result["candidates"][0]["t60"] == 60.0


def test_historical_evaluation_reports_missing_point_in_time_snapshot(tmp_path) -> None:
    result = build_historical_evaluation(
        _service(tmp_path), __import__("datetime").date(2025, 4, 7), lambda **_: {}
    )
    assert result["market_state"] is None
    assert result["candidates"] == []
    assert "point-in-time" in result["data_gaps"][0]


def test_feishu_preview_defaults_to_no_send_and_confirmation_queues_once(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "outbox.sqlite3")
    report = {"trade_date": "2026-07-24", "market_state": "PANIC", "market_summary": {}, "candidates": []}

    preview = prepare_feishu_delivery(report, repository)
    assert preview["status"] == "preview"
    assert preview["send"] is False
    assert preview["scheduler"] is False

    queued = prepare_feishu_delivery(report, repository, send=True, confirmed=True)
    duplicate = prepare_feishu_delivery(report, repository, send=True, confirmed=True)
    assert queued["status"] == "queued"
    assert duplicate["status"] == "already_queued"
    assert repository.get_message(queued["message_id"]).body == preview["preview"]
