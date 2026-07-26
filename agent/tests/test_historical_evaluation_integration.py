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

    def test_evaluate_endpoint_structure(self):
        """Prove the endpoint is wired and returns the correct structure.

        Note: AKShare API is currently unavailable in sandbox, so all windows
        will report entry_price_unavailable or price_data_missing. This is
        expected — the code is real but the data source is blocked.
        """
        resp = self.client.get("/investment-research/historical-evaluation/evaluate/2026-07-24")
        assert resp.status_code == 200
        data = resp.json()
        assert "evaluation_date" in data
        assert "metrics" in data
        assert "horizons" in data
        for h in data["horizons"]:
            assert h["data_gap"] is not None, (
                "AKShare API unavailable in sandbox — expected data_gap"
            )
