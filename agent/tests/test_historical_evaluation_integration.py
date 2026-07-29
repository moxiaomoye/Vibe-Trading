"""Formal optional-route wiring checks for historical evaluation."""

from __future__ import annotations

import os
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.optional_feature_routes import register_optional_feature_routes


def _paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes}


def test_formal_optional_registration_is_default_off(monkeypatch) -> None:
    monkeypatch.delenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", raising=False)
    monkeypatch.delenv("PANIC_SHADOW_REPORT_API_ENABLED", raising=False)
    app = FastAPI()
    register_optional_feature_routes(app, lambda: None)
    response = TestClient(app).get(
        "/investment-research/historical-evaluation/status"
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_formal_optional_registration_exposes_authenticated_routes(monkeypatch) -> None:
    monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", "true")
    monkeypatch.setenv("PANIC_SHADOW_REPORT_API_ENABLED", "true")
    app = FastAPI()
    app.get("/live")(lambda: {"status": "ok"})
    register_optional_feature_routes(app, lambda: None)

    assert "/investment-research/historical-evaluation/status" in _paths(app)
    assert "/investment-research/historical-evaluation/evaluate-auto" in _paths(app)
    assert "/investment-research/historical-evaluation/evaluate-manual" in _paths(app)
    response = TestClient(app).get(
        "/investment-research/historical-evaluation/status"
    )
    assert response.status_code == 200
    assert response.json()["manual_import_supported"] is True
    assert TestClient(app).get("/live").status_code == 200


def test_real_api_server_exposes_route_when_switches_are_enabled() -> None:
    environment = {
        **os.environ,
        "INVESTMENT_RESEARCH_ROUTES_ENABLED": "true",
        "PANIC_SHADOW_REPORT_API_ENABLED": "true",
        "API_AUTH_KEY": "historical-evaluation-test-key",
    }
    script = """
from fastapi.testclient import TestClient
import api_server
client = TestClient(api_server.app)
headers = {"Authorization": "Bearer historical-evaluation-test-key"}
response = client.get(
    "/investment-research/historical-evaluation/status",
    headers=headers,
)
assert response.status_code == 200, response.text
assert response.json()["manual_import_supported"] is True
assert client.get("/live").status_code == 200
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
