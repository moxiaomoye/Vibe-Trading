from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import research_mvp_routes
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
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["code"] == "688001.SH"
    assert "relative_to_market_pct" in body["candidates"][0]["data_gaps"]
    assert service.history(1)[0]["mode"] == "demo"
