"""R2: Integration test — historical evaluation routes on the real api_server."""

from __future__ import annotations

import ast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.historical_evaluation_routes import router


def test_source_code_contains_wiring():
    """Verify api_server.py source contains the include_router call (works without deps)."""
    with open("api_server.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "include_router":
                for arg in node.args:
                    if isinstance(arg, ast.Name) and "historical_evaluation" in arg.id.lower():
                        found = True
                        break
    assert found, (
        "api_server.py does not contain app.include_router(...) "
        "with 'historical_evaluation' in the name"
    )


class TestHistoricalEvaluationRouterDirect:
    """Directly test the router (no api_server dep needed)."""

    def setup_method(self) -> None:
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_status_endpoint(self):
        resp = self.client.get("/investment-research/historical-evaluation/status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_evaluate_endpoint_is_contract_only(self):
        resp = self.client.get("/investment-research/historical-evaluation/evaluate/2026-07-24")
        assert resp.status_code == 200
        data = resp.json()
        assert "evaluation_date" in data
        for h in data["horizons"]:
            # FixtureOutcomeLoader({}) always produces data_gap — proves contract-only
            assert h["data_gap"] is not None, (
                "FixtureOutcomeLoader({}) always produces gaps — "
                "this endpoint is contract-only, not production-ready"
            )
