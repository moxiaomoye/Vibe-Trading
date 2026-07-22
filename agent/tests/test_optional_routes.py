"""Tests for the optional feature route loader (optional_routes.py).

Scenarios covered:
1. Both switches OFF  → no imports, no optional routes, core routes survive
2. Value Hunter ON    → VH routes present, IR absent
3. Investment Research ON → IR routes present, VH absent
4. VH import failure  → core app still works, /live present, result is FAILED
5. IR registration failure → core app survives, result is FAILED
6. Both ON            → both feature routes present
7. Old var ignored    → VALUE_HUNTER_ENABLED does NOT enable the new loader
"""

from __future__ import annotations

import importlib
import logging
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.optional_routes import LoadStatus


def _route_paths(app: FastAPI) -> set[str]:
    return {r.path for r in app.routes}


def _clean_modules() -> None:
    for mod in list(sys.modules):
        if "value_hunter_routes" in mod or "investment_research_routes" in mod:
            sys.modules.pop(mod, None)


class TestBothDisabled:
    """Both feature flags are unset / falsy — no optional module is loaded."""

    @pytest.mark.parametrize("vh_val,ir_val", [
        pytest.param("", "", id="both-empty"),
        pytest.param("0", "false", id="both-falsy"),
        pytest.param("false", "no", id="both-explicit-false"),
    ])
    def test_optional_modules_not_imported(
        self, monkeypatch: pytest.MonkeyPatch, vh_val: str, ir_val: str
    ) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", vh_val)
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", ir_val)

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app, feature_name="Value Hunter", env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )
        r2 = try_register_routes(
            app, feature_name="Investment Research", env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.DISABLED
        assert r2.status == LoadStatus.DISABLED
        assert r1.feature_name == "Value Hunter"
        assert r2.feature_name == "Investment Research"

        paths = _route_paths(app)
        assert "/live" in paths
        assert "/value-hunter/status" not in paths
        assert "/investment-research/status" not in paths
        assert "src.api.value_hunter_routes" not in sys.modules
        assert "src.api.investment_research_routes" not in sys.modules

    def test_core_routes_still_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.delenv("VALUE_HUNTER_ROUTES_ENABLED", raising=False)
        monkeypatch.delenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", raising=False)

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app, feature_name="VH", env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )
        r2 = try_register_routes(
            app, feature_name="IR", env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.DISABLED
        assert r2.status == LoadStatus.DISABLED

        client = TestClient(app)
        resp = client.get("/live")
        assert resp.status_code == 200

        resp = client.get("/value-hunter/status")
        assert resp.status_code == 404


class TestValueHunterEnabled:
    """Only Value Hunter is enabled."""

    def test_value_hunter_routes_registered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", "0")

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app, feature_name="Value Hunter", env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )
        r2 = try_register_routes(
            app, feature_name="Investment Research", env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.LOADED
        assert r2.status == LoadStatus.DISABLED

        paths = _route_paths(app)
        assert "/value-hunter/status" in paths
        assert "/investment-research/status" not in paths
        assert "src.api.investment_research_routes" not in sys.modules


class TestInvestmentResearchEnabled:
    """Only Investment Research is enabled."""

    def test_investment_research_routes_registered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "false")
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", "1")

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app, feature_name="Value Hunter", env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )
        r2 = try_register_routes(
            app, feature_name="Investment Research", env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.DISABLED
        assert r2.status == LoadStatus.LOADED

        paths = _route_paths(app)
        assert "/value-hunter/status" not in paths
        assert "/investment-research/status" in paths
        assert "src.api.value_hunter_routes" not in sys.modules


class TestImportFailure:
    """When an optional module fails to import, the core app survives."""

    def test_value_hunter_import_failure(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        original_import = importlib.import_module

        def _failing_import(name: str, *args: object, **kwargs: object) -> object:
            if "value_hunter_routes" in name:
                raise ImportError("simulated failure")
            return original_import(name, *args, **kwargs)

        caplog.set_level(logging.WARNING)

        with monkeypatch.context() as m:
            m.setattr(importlib, "import_module", _failing_import)
            result = try_register_routes(
                app, feature_name="Value Hunter", env_var="VALUE_HUNTER_ROUTES_ENABLED",
                module_path="src.api.value_hunter_routes",
                register_func_name="register_value_hunter_routes",
                require_auth=lambda: None,
            )

        assert result.status == LoadStatus.FAILED
        assert result.feature_name == "Value Hunter"
        assert "Failed to register optional feature" in caplog.text

        client = TestClient(app)
        resp = client.get("/live")
        assert resp.status_code == 200

    def test_investment_research_registration_failure(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _clean_modules()
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", "true")

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        original_import = importlib.import_module

        def _bad_import(name: str, *args: object, **kwargs: object) -> object:
            if "investment_research_routes" not in name:
                return original_import(name, *args, **kwargs)
            mod = original_import(name, *args, **kwargs)

            def _register(app: object, require_auth: object) -> None:
                msg = "simulated registration failure"
                raise RuntimeError(msg)

            mod.register_investment_research_routes = _register
            return mod

        caplog.set_level(logging.WARNING)

        with monkeypatch.context() as m:
            m.setattr(importlib, "import_module", _bad_import)
            result = try_register_routes(
                app, feature_name="Investment Research",
                env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
                module_path="src.api.investment_research_routes",
                register_func_name="register_investment_research_routes",
                require_auth=lambda: None,
            )

        assert result.status == LoadStatus.FAILED
        assert result.feature_name == "Investment Research"
        assert "Failed to register optional feature" in caplog.text

        client = TestClient(app)
        resp = client.get("/live")
        assert resp.status_code == 200


class TestBothEnabled:
    """Both feature flags are truthy — both sets of routes are registered."""

    def test_both_features_registered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ROUTES_ENABLED", "true")
        monkeypatch.setenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", "yes")

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app, feature_name="Value Hunter", env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )
        r2 = try_register_routes(
            app, feature_name="Investment Research",
            env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
            module_path="src.api.investment_research_routes",
            register_func_name="register_investment_research_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.LOADED
        assert r2.status == LoadStatus.LOADED

        paths = _route_paths(app)
        assert "/value-hunter/status" in paths
        assert "/investment-research/status" in paths


class TestOldVarsIgnored:
    """Old env var VALUES_HUNTER_ENABLED must NOT enable the new route loader."""

    def test_old_value_hunter_var_does_not_enable_routes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clean_modules()
        monkeypatch.setenv("VALUE_HUNTER_ENABLED", "true")
        monkeypatch.delenv("VALUE_HUNTER_ROUTES_ENABLED", raising=False)
        monkeypatch.delenv("INVESTMENT_RESEARCH_ROUTES_ENABLED", raising=False)

        from src.api.optional_routes import try_register_routes

        app = FastAPI()
        app.get("/live")(lambda: {"status": "ok"})

        r1 = try_register_routes(
            app, feature_name="Value Hunter", env_var="VALUE_HUNTER_ROUTES_ENABLED",
            module_path="src.api.value_hunter_routes",
            register_func_name="register_value_hunter_routes",
            require_auth=lambda: None,
        )

        assert r1.status == LoadStatus.DISABLED
        assert r1.feature_name == "Value Hunter"

        paths = _route_paths(app)
        assert "/live" in paths
        assert "/value-hunter/status" not in paths
        assert "src.api.value_hunter_routes" not in sys.modules
