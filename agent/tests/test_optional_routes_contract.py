"""W2 — Optional routes full-state contract matrix.

Extends test_optional_routes.py with scenarios not yet covered:
  - unauthenticated / wrong auth
  - duplicate registration
  - independent failure isolation
  - side-effect freedom (trading, database)
  - POST disabled returns structured non-success
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.api.optional_routes import DisabledStub, LoadResult, LoadStatus, try_register_routes


def _clean_modules() -> None:
    for mod in list(sys.modules):
        if "value_hunter_routes" in mod or "investment_research_routes" in mod:
            sys.modules.pop(mod, None)


def _all_paths(app: FastAPI) -> set[str]:
    return {r.path for r in app.routes}


class MockAuth:
    """Simulate authentication dependency outcomes."""

    @staticmethod
    def always_pass() -> None:
        pass

    @staticmethod
    async def always_fail() -> None:
        raise HTTPException(status_code=401, detail="Unauthorized")


class TestAuthFailure:
    """Unauthenticated requests to optional endpoints must be rejected."""

    def test_disabled_endpoint_rejects_unauthenticated(self) -> None:
        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        try_register_routes(
            app,
            feature_name="VH",
            env_var="UNLIKELY_VAR",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=MockAuth.always_fail,
            disabled_stubs=[DisabledStub(path="/value-hunter/status", response={"enabled": False})],
        )

        client = TestClient(app)
        resp = client.get("/value-hunter/status")
        assert resp.status_code == 401

    def test_enabled_endpoint_passes_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        try_register_routes(
            app,
            feature_name="VH",
            env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=MockAuth.always_pass,
        )

        client = TestClient(app)
        resp = client.get("/value-hunter/status")
        assert resp.status_code == 200


class TestDuplicateRegistration:
    """Registering the same optional feature twice is safe."""

    def test_duplicate_register_same_feature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app,
            feature_name="VH",
            env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )
        r2 = try_register_routes(
            app,
            feature_name="VH",
            env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.LOADED
        assert r2.status == LoadStatus.LOADED
        # Routes still accessible
        paths = _all_paths(app)
        assert "/value-hunter/status" in paths


class TestFailureIsolation:
    """One feature failing must not prevent another from loading."""

    def test_import_failure_of_one_does_not_block_other(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", "true")

        original_import = importlib.import_module

        def _failing_import(name: str, *args: object, **kwargs: object) -> object:
            if "value_hunter_routes" in name:
                raise ImportError("simulated VH import failure")
            return original_import(name, *args, **kwargs)

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        with monkeypatch.context() as m:
            m.setattr(importlib, "import_module", _failing_import)
            r1 = try_register_routes(
                app,
                feature_name="VH",
                env_var="VALUE_HUNTER_ROUTES_ENABLED",
                module_path="src.api.value_hunter_routes",
                register_func_name="register_value_hunter_routes",
                require_auth=lambda: None,
            )
            r2 = try_register_routes(
                app,
                feature_name="IR",
                env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
                module_path="src.api.investment_research_routes",
                register_func_name="register_investment_research_routes",
                require_auth=lambda: None,
            )

        assert r1.status == LoadStatus.FAILED
        assert r2.status == LoadStatus.LOADED
        paths = _all_paths(app)
        assert "/live" in paths
        assert "/investment-research/status" in paths


class TestSideEffectFreedom:
    """Route registration must not touch trading, database, or scheduler."""

    def test_no_new_database_after_disabled(self) -> None:
        """Route registration (disabled) must not import new DB modules."""
        before = set(sys.modules)
        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        try_register_routes(
            app,
            feature_name="VH",
            env_var="NEVER_SET_VAR",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )

        new = {m for m in sys.modules if m not in before and ("sqlite" in m or "sqlalchemy" in m)}
        assert new == set(), f"Unexpected DB modules loaded: {new}"

    def test_no_trading_modules_imported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Route registration (enabled) must not import trading SDK modules."""
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        try_register_routes(
            app,
            feature_name="VH",
            env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )

        loaded = {m for m in sys.modules if "trading.connector" in m}
        assert loaded == set(), f"Unexpected trading modules loaded: {loaded}"


class TestDisabledPostReturnsNonSuccess:
    """When disabled, POST run must return structured non-success, not 200 OK."""

    def test_disabled_post_returns_structured_failure(self) -> None:
        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        try_register_routes(
            app,
            feature_name="VH",
            env_var="UNSET_VAR",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
            disabled_stubs=[
                DisabledStub(path="/value-hunter/run", response={"enabled": False, "reason": "feature_not_enabled"}, methods={"POST"}, status_code=503),
            ],
        )

        client = TestClient(app)
        resp = client.post("/value-hunter/run", json={})
        # Must NOT return 200 OK — structured non-success
        assert resp.status_code != 200
        body = resp.json()
        assert body.get("enabled") is False


class TestLiveEndpointPreserved:
    """/live must always return 200 regardless of optional feature state."""

    @pytest.mark.parametrize("vh_val,ir_val", [
        ("true", "true"),
        ("false", "false"),
        ("", ""),
    ])
    def test_live_always_healthy(self, monkeypatch: pytest.MonkeyPatch, vh_val: str, ir_val: str) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", vh_val)
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", ir_val)

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        try_register_routes(
            app,
            feature_name="VH",
            env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=MockAuth.always_pass,
        )
        try_register_routes(
            app,
            feature_name="IR",
            env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=MockAuth.always_pass,
        )

        client = TestClient(app)
        resp = client.get("/live")
        assert resp.status_code == 200
