"""Application-level wiring for isolated, default-off feature routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from src.api.optional_routes import DisabledStub, try_register_routes

if TYPE_CHECKING:
    from fastapi import FastAPI


AuthDep = Callable[..., Awaitable[Any] | Any]
_DISABLED = {"enabled": False, "status": "disabled", "reason": "feature_not_enabled"}


def register_optional_feature_routes(app: FastAPI, require_auth: AuthDep) -> None:
    """Register optional feature routes without importing disabled modules."""
    try_register_routes(
        app,
        feature_name="Value Hunter",
        env_var="VALUE_HUNTER_ROUTES_ENABLED",
        module_path="src.api.value_hunter_routes",
        register_func_name="register_value_hunter_routes",
        require_auth=require_auth,
        disabled_stubs=[
            _stub("/value-hunter/status", "value_hunter"),
            _stub("/value-hunter/history", "value_hunter"),
            _stub("/value-hunter/run", "value_hunter", methods={"POST"}, status_code=404),
        ],
    )
    try_register_routes(
        app,
        feature_name="Investment Research",
        env_var="INVESTMENT_RESEARCH_ROUTES_ENABLED",
        module_path="src.api.investment_research_routes",
        register_func_name="register_investment_research_routes",
        require_auth=require_auth,
        disabled_stubs=_investment_research_stubs(),
    )


def _stub(
    path: str,
    feature: str,
    *,
    methods: set[str] | None = None,
    status_code: int = 200,
) -> DisabledStub:
    response = {**_DISABLED, "feature": feature}
    return DisabledStub(
        path,
        response,
        methods=methods or {"GET"},
        status_code=status_code,
    )


def _investment_research_stubs() -> list[DisabledStub]:
    research_paths = [
        "/investment-research/status",
        "/investment-research/theses",
        "/investment-research/theses/{thesis_id}",
        "/investment-research/theses/{thesis_id}/versions",
        "/investment-research/theses/{thesis_id}/initialization",
        "/investment-research/evidence-inbox",
        "/investment-research/evidence-associations",
        "/investment-research/evidence-readiness",
        "/investment-research/reviews",
        "/investment-research/daily/{report_date}",
        "/investment-research/daily-research/{report_date}",
        "/investment-research/discovery-leads",
    ]
    stubs = [_stub(path, "investment_research") for path in research_paths]
    stubs.extend(
        [
            _stub("/investment-research/panic-shadow/status", "panic_shadow"),
            _stub(
                "/investment-research/panic-shadow/run",
                "panic_shadow",
                methods={"POST"},
                status_code=404,
            ),
            _stub(
                "/investment-research/panic-shadow/run-current",
                "panic_shadow",
                methods={"POST"},
                status_code=404,
            ),
            _stub(
                "/investment-research/panic-shadow/run-manual",
                "panic_shadow",
                methods={"POST"},
                status_code=404,
            ),
            _stub(
                "/investment-research/panic-shadow/latest",
                "panic_shadow",
                status_code=404,
            ),
            _stub(
                "/investment-research/historical-evaluation/status",
                "historical_evaluation",
            ),
            _stub(
                "/investment-research/historical-evaluation/evaluate-auto",
                "historical_evaluation",
                methods={"POST"},
                status_code=404,
            ),
            _stub(
                "/investment-research/historical-evaluation/evaluate-manual",
                "historical_evaluation",
                methods={"POST"},
                status_code=404,
            ),
        ]
    )
    return stubs
