from __future__ import annotations

from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import value_hunter_routes
from src.value_hunter.config import ValueHunterConfig
from src.value_hunter.providers import DemoProvider
from src.value_hunter.service import ValueHunterService
from src.value_hunter.store import ValueHunterStore


def _service(tmp_path):
    cfg = ValueHunterConfig(
        enabled=False, provider="demo", schedule="18:10", timezone="Asia/Shanghai",
        market_alert_score=70, candidate_alert_score=75, max_candidates=5,
        database_path=tmp_path / "api.sqlite3", watchlist_path=None,
        feishu_webhook_url="", smtp_host="", smtp_port=465, smtp_username="",
        smtp_password="", smtp_from="", email_to="", notify_on_demo=False,
    )
    return ValueHunterService(cfg, DemoProvider(), ValueHunterStore(cfg.database_path))


def test_value_hunter_api_end_to_end(tmp_path, monkeypatch):
    service = _service(tmp_path)
    monkeypatch.setattr(value_hunter_routes, "_service", service)
    app = FastAPI()
    value_hunter_routes.register_value_hunter_routes(app, lambda: None)
    client = TestClient(app)

    initial = client.get("/value-hunter/status")
    assert initial.status_code == 200
    assert initial.json()["latest"] is None

    run = client.post("/value-hunter/run?notify=false")
    assert run.status_code == 200
    assert run.json()["market"]["level"] == "股灾"
    assert len(run.json()["candidates"]) == 2

    history = client.get("/value-hunter/history?limit=1")
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["run_id"] == run.json()["run_id"]


def test_history_limit_is_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(value_hunter_routes, "_service", _service(tmp_path))
    app = FastAPI()
    value_hunter_routes.register_value_hunter_routes(app, lambda: None)
    response = TestClient(app).get("/value-hunter/history?limit=0")
    assert response.status_code == 422
