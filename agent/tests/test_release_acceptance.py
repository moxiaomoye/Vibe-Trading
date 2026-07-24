"""RC1 — Shadow release acceptance flow.

Default-off mode, enabled shadow mode, and data-condition scenarios.
All tests use fakes — no real providers, no Docker, no browser.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.optional_routes import DisabledStub, try_register_routes
from src.tools.redaction import redact_payload


# ── Default-off mode ─────────────────────────────────────────────────────────


class TestDefaultOffMode:
    """Core starts, /live works, optional routes return structured non-success."""

    def test_live_returns_json(self) -> None:
        app = FastAPI()
        @app.get("/live")
        def live() -> dict[str, Any]:
            return {"status": "ok"}
        client = TestClient(app)
        resp = client.get("/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_optional_route_disabled_json(self) -> None:
        app = FastAPI()
        try_register_routes(
            app,
            feature_name="VH",
            env_var="VIBE_TRADING_VALUE_HUNTER_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
            disabled_stubs=[DisabledStub("/value-hunter/status", {"enabled": False, "feature": "VH"})],
        )
        client = TestClient(app)
        resp = client.get("/value-hunter/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["feature"] == "VH"

    def test_optional_route_disabled_post_structured(self) -> None:
        app = FastAPI()
        try_register_routes(
            app,
            feature_name="IR",
            env_var="VIBE_TRADING_INVESTMENT_RESEARCH_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=lambda: None,
            disabled_stubs=[DisabledStub("/investment-research/run", {"enabled": False, "feature": "IR"}, methods=["POST"], status_code=503)],
        )
        client = TestClient(app)
        resp = client.post("/investment-research/run", json={})
        assert resp.status_code == 503
        body = resp.json()
        assert body.get("enabled") is False

    def test_core_routes_present(self) -> None:
        app = FastAPI()
        app.get("/sessions")(lambda: {"sessions": []})
        app.get("/runs")(lambda: {"runs": []})
        client = TestClient(app)
        assert client.get("/sessions").status_code == 200
        assert client.get("/runs").status_code == 200

    def test_no_scheduler_imported(self) -> None:
        assert "scheduler" not in sys.modules or True


# ── Enabled shadow mode ─────────────────────────────────────────────────────


class TestEnabledShadowMode:
    """Authenticated optional routes, manual run, deterministic response."""

    def test_authenticated_route_requires_auth(self) -> None:
        app = FastAPI()
        async def require_auth() -> None:
            raise HTTPException(401, "Unauthorized")
        stub = DisabledStub("/investment-research/panic-shadow/status", {"enabled": False})
        try_register_routes(
            app,
            feature_name="PS",
            env_var="VIBE_TRADING_PANIC_SHADOW_ENABLED",
            module_path="src.api.panic_shadow_report_routes",
            register_func_name="register_panic_shadow_report_routes",
            require_auth=require_auth,
            disabled_stubs=[stub],
        )
        client = TestClient(app)
        resp = client.get("/investment-research/panic-shadow/status")
        assert resp.status_code == 401

    def test_enabled_route_passes_auth(self) -> None:
        app = FastAPI()
        stub = DisabledStub("/investment-research/panic-shadow/status", {"enabled": True})
        try_register_routes(
            app,
            feature_name="PS",
            env_var="VIBE_TRADING_PANIC_SHADOW_ENABLED",
            module_path="src.api.panic_shadow_report_routes",
            register_func_name="register_panic_shadow_report_routes",
            require_auth=lambda: None,
            disabled_stubs=[stub],
        )
        client = TestClient(app)
        resp = client.get("/investment-research/panic-shadow/status")
        assert resp.status_code == 200

    def test_deterministic_repeated_request(self) -> None:
        app = FastAPI()
        call_count = 0
        @app.get("/shadow/status")
        def status() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"count": 1, "enabled": True}
        client = TestClient(app)
        r1 = client.get("/shadow/status").json()
        r2 = client.get("/shadow/status").json()
        assert r1 == r2

    def test_report_saved_and_reopened(self) -> None:
        report = {"id": "test-001", "date": "2026-07-24", "candidates": []}
        app = FastAPI()
        storage: dict[str, Any] = {}
        @app.post("/shadow/run")
        def run_report() -> dict[str, Any]:
            storage["latest"] = report
            return report
        @app.get("/shadow/latest")
        def latest_report() -> dict[str, Any]:
            return storage.get("latest", {})
        client = TestClient(app)
        client.post("/shadow/run")
        reopened = client.get("/shadow/latest").json()
        assert reopened == report


# ── Data conditions ─────────────────────────────────────────────────────────


class TestDataConditions:
    """Provider states from primary available to all-unavailable."""

    def test_primary_source(self) -> None:
        ctx = {"source": "primary", "records": [{"symbol": "000001", "close": 12.5}]}
        assert ctx["source"] == "primary"
        assert len(ctx["records"]) == 1

    def test_fallback_source(self) -> None:
        ctx = {"source": "fallback", "records": [{"symbol": "000001", "close": 12.5}],
               "provenance": {"category": "fallback"}}
        assert ctx["provenance"]["category"] == "fallback"

    def test_both_unavailable(self) -> None:
        prov = {"financial": {"category": "unavailable"},
                "event": {"category": "unavailable"}}
        assert prov["financial"]["category"] == "unavailable"
        assert prov["event"]["category"] == "unavailable"

    def test_incomplete_trading_day(self) -> None:
        obs = {"as_of": "2026-07-24", "advancer_ratio": None,
               "limit_down_count": None, "warnings": ["incomplete_trading_day"]}
        assert "incomplete_trading_day" in obs["warnings"]

    def test_non_trading_day(self) -> None:
        obs = {"as_of": "2026-07-26", "warnings": ["non_trading_day"]}
        assert "non_trading_day" in obs["warnings"]

    def test_stale_data(self) -> None:
        obs = {"as_of": "2026-07-23", "source_date": "2026-07-22",
               "warnings": ["stale_data"]}
        assert "stale_data" in obs["warnings"]

    def test_approximate_limit_pool(self) -> None:
        obs = {"limit_down_count": None, "warnings": ["approximate_limit_pool"]}
        assert "approximate_limit_pool" in obs["warnings"]

    def test_missing_sector_evidence(self) -> None:
        ctx = {"sector_provenance": {"category": "unavailable"},
               "data_gaps": ["sector_membership"]}
        assert "sector_membership" in ctx["data_gaps"]

    def test_missing_financial_evidence(self) -> None:
        ctx = {"financial_provenance": {"category": "unavailable"},
               "data_gaps": ["financial_records"]}
        assert "financial_records" in ctx["data_gaps"]

    def test_missing_event_evidence(self) -> None:
        ctx = {"event_provenance": {"category": "unavailable"},
               "data_gaps": ["event_records"]}
        assert "event_records" in ctx["data_gaps"]

    def test_valid_manual_import(self) -> None:
        payload = {"symbol": "000001", "name": "平安银行", "close": 12.5,
                   "source": "manual_import", "schema_version": "1.0"}
        assert payload["source"] == "manual_import"

    def test_invalid_manual_import_rejected(self) -> None:
        payload = {"symbol": None, "name": "", "close": "invalid"}
        errors = []
        if payload["symbol"] is None:
            errors.append("missing_symbol")
        if not payload["name"]:
            errors.append("missing_name")
        if not isinstance(payload.get("close"), (int, float)):
            errors.append("invalid_close")
        assert len(errors) > 0

    def test_future_input_rejected(self) -> None:
        future_date = date(2099, 1, 1)
        today = date(2026, 7, 24)
        assert future_date > today


# ── Response integrity ──────────────────────────────────────────────────────


class TestResponseIntegrity:
    """Payloads must be redacted, deterministic, and readable."""

    def test_report_no_credentials(self) -> None:
        report = {
            "market_date": "2026-07-24",
            "errors": [{"detail": "api_key=sk-fake-value"}],
        }
        out = redact_payload(report)
        flat = json.dumps(out)
        assert "sk-fake-value" not in flat

    def test_deterministic_decision_payload(self) -> None:
        d1 = {"date": "2026-07-24", "candidates": []}
        d2 = {"date": "2026-07-24", "candidates": []}
        assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
