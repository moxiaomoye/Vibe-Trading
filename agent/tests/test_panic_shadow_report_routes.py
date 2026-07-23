from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import panic_shadow_report_routes as shadow_routes
from src.api.security import require_auth


TRADE_DATE = date(2026, 7, 22)
OBSERVED_AT = datetime(2026, 7, 22, 10, 31, tzinfo=timezone.utc)
API_PATH = "/investment-research/panic-shadow/run"
STATUS_PATH = "/investment-research/panic-shadow/status"


def _payload() -> dict:
    rows = []
    for index in range(120):
        symbol = f"{index + 1:06d}"
        rows.append(
            {
                "symbol": symbol,
                "name": f"fixture-{index}",
                "close": 9.4,
                "change_pct": -6.0,
                "previous_close": 10.0,
            }
        )
    return {
        "run_id": "http-shadow-fixture",
        "data_date": TRADE_DATE.isoformat(),
        "observed_at": OBSERVED_AT.isoformat(),
        "information_cutoff": (OBSERVED_AT - timedelta(minutes=1)).isoformat(),
        "data_available_at": (OBSERVED_AT - timedelta(minutes=2)).isoformat(),
        "market_return": -0.06,
        "rows": rows,
        "limit_down_symbols": [row["symbol"] for row in rows[:80]],
    }


def _direct_client(auth=require_auth) -> TestClient:
    app = FastAPI()
    app.get("/live")(lambda: {"status": "ok"})
    shadow_routes.register_panic_shadow_report_routes(app, auth)
    return TestClient(app)


def _paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes}


def test_shadow_routes_are_absent_by_default_and_module_is_lazy(monkeypatch) -> None:
    monkeypatch.delenv("PANIC_SHADOW_REPORT_API_ENABLED", raising=False)
    sys.modules.pop("src.api.panic_shadow_report_routes", None)

    from src.api.investment_research_routes import register_investment_research_routes

    app = FastAPI()
    register_investment_research_routes(app, lambda: None)

    assert STATUS_PATH not in _paths(app)
    assert API_PATH not in _paths(app)
    assert "src.api.panic_shadow_report_routes" not in sys.modules


def test_shadow_routes_exist_only_when_child_feature_is_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PANIC_SHADOW_REPORT_API_ENABLED", "true")

    from src.api.investment_research_routes import register_investment_research_routes

    app = FastAPI()
    register_investment_research_routes(app, lambda: None)
    client = TestClient(app)

    assert STATUS_PATH in _paths(app)
    assert API_PATH in _paths(app)
    assert client.get(STATUS_PATH).json() == {
        "enabled": True,
        "mode": "shadow",
        "read_only": True,
        "explicit_input_only": True,
        "persistent": False,
        "scheduler_enabled": False,
        "notification_enabled": False,
        "trading_enabled": False,
        "manual_review_required": True,
    }


def test_shadow_routes_reuse_existing_bearer_auth(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_KEY", "fixture-key")
    client = _direct_client()

    denied = client.get(STATUS_PATH)
    allowed = client.get(
        STATUS_PATH,
        headers={"Authorization": "Bearer fixture-key"},
    )

    assert denied.status_code == 401
    assert denied.json()["detail"] == "Invalid or missing API key"
    assert allowed.status_code == 200


def test_fixture_returns_json_safe_m11_report_and_is_deterministic() -> None:
    client = _direct_client(lambda: None)
    payload = _payload()

    first = client.post(API_PATH, json=payload)
    second = client.post(API_PATH, json=payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    report = first.json()
    assert report["shadow_run"] is True
    assert report["manual_review_required"] is True
    assert report["information_cutoff"] == payload["information_cutoff"]
    assert report["market"]["trade_date"] == TRADE_DATE.isoformat()
    assert report["market"]["decline"] == 120
    assert report["market"]["limit_down"] == 80
    assert report["research_candidates"] == []
    assert report["versions"]["panic_rule"]
    assert report["versions"]["candidate_pipeline"] == "not_run"


def test_invalid_point_in_time_input_returns_structured_error() -> None:
    client = _direct_client(lambda: None)
    payload = _payload()
    payload["data_date"] = (TRADE_DATE - timedelta(days=1)).isoformat()

    response = client.post(API_PATH, json=payload)

    assert response.status_code == 422
    assert response.json()["shadow_run"] is True
    assert response.json()["error"] == {
        "code": "shadow_run_stale_data",
        "message": "shadow report did not execute",
        "reasons": ["data_date_does_not_match_trade_date"],
    }


def test_isolated_execution_failure_does_not_affect_live(monkeypatch) -> None:
    client = _direct_client(lambda: None)

    def fail(_payload):
        raise RuntimeError("fixture failure must stay isolated")

    monkeypatch.setattr(shadow_routes, "_execute", fail)
    failed = client.post(API_PATH, json=_payload())
    live = client.get("/live")

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "shadow_run_failed"
    assert "fixture failure" not in failed.json()["error"]["message"]
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}


def test_dry_run_does_not_call_side_effect_boundaries(monkeypatch) -> None:
    from src.investment_research.operations import delivery
    from src.investment_research.repositories import sqlite
    from src.trading import service as trading_service
    from src.value_hunter import scheduler

    def forbidden(*_args, **_kwargs):
        raise AssertionError("side-effect boundary was called")

    monkeypatch.setattr(delivery.FeishuWebhookTransport, "send", forbidden)
    monkeypatch.setattr(delivery.SMTPTransport, "send", forbidden)
    monkeypatch.setattr(sqlite.SQLiteResearchRepository, "__init__", forbidden)
    monkeypatch.setattr(scheduler.ValueHunterScheduler, "start", forbidden)
    monkeypatch.setattr(trading_service, "place_order", forbidden)

    response = _direct_client(lambda: None).post(API_PATH, json=_payload())

    assert response.status_code == 200
    assert response.json()["shadow_run"] is True
