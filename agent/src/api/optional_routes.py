"""Safe, lazy loader for optional feature route modules.

Each optional feature is gated by its environment variable.  When the gate
is closed the module is never imported; when open it is imported lazily at
route-registration time.  Any import or registration failure is logged but
never propagated — the core application continues starting.
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from fastapi import Depends

if TYPE_CHECKING:
    from fastapi import FastAPI

from src.config.accessor import _parse_bool

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Awaitable[object] | object]


class LoadStatus(Enum):
    DISABLED = "disabled"
    LOADED = "loaded"
    FAILED = "failed"


@dataclass
class LoadResult:
    feature_name: str
    status: LoadStatus
    error: str | None = None


@dataclass
class DisabledStub:
    """A minimal route to register when an optional feature is disabled.

    Attributes:
        path: The URL path (e.g. ``/value-hunter/status``).
        response: JSON-serialisable body returned on every request.
        methods: HTTP methods to accept (default ``{"GET"}``).
        status_code: HTTP status code (default 200).
    """
    path: str
    response: Any
    methods: set[str] = field(default_factory=lambda: {"GET"})
    status_code: int = 200


def try_register_routes(
    app: FastAPI,
    *,
    feature_name: str,
    env_var: str,
    module_path: str,
    register_func_name: str,
    require_auth: AuthDep,
    disabled_stubs: list[DisabledStub] | None = None,
) -> LoadResult:
    """Register optional feature routes gated by *env_var*.

    When the env var is unset / falsy the module is never imported.  If
    *disabled_stubs* is provided those minimal routes are registered instead
    so that API consumers receive structured JSON rather than SPA HTML.

    When truthy the module is lazy-imported and its registration function called.
    Any exception during import or registration is caught, logged (with
    traceback), and never propagated — the core Application continues starting.

    Returns:
        A ``LoadResult`` whose ``status`` is one of
        ``DISABLED`` / ``LOADED`` / ``FAILED``.
    """
    if not _parse_bool(os.environ.get(env_var)):
        logger.debug("Optional feature %r disabled (%s not set)", feature_name, env_var)
        for stub in (disabled_stubs or []):
            _register_stub(app, stub, require_auth)
        return LoadResult(feature_name=feature_name, status=LoadStatus.DISABLED)

    try:
        mod = importlib.import_module(module_path)
        register = getattr(mod, register_func_name)
        register(app, require_auth)
        logger.info("Optional feature %r routes registered", feature_name)
        return LoadResult(feature_name=feature_name, status=LoadStatus.LOADED)
    except Exception as exc:
        logger.exception("Failed to register optional feature %r — skipping", feature_name)
        return LoadResult(
            feature_name=feature_name,
            status=LoadStatus.FAILED,
            error=str(exc),
        )


def _register_stub(app: FastAPI, stub: DisabledStub, require_auth: AuthDep) -> None:
    """Register one disabled-stub route on *app*."""
    for method in stub.methods:
        method_lower = method.lower()

        def _handler(_response: Any = stub.response) -> Any:
            return _response

        _handler.__name__ = f"disabled_{stub.path.replace('/', '_').replace('-', '_')}_{method_lower}"

        if method_lower == "get":
            app.get(stub.path, status_code=stub.status_code, dependencies=[Depends(require_auth)])(_handler)
        elif method_lower == "post":
            app.post(stub.path, status_code=stub.status_code, dependencies=[Depends(require_auth)])(_handler)
        elif method_lower in ("put", "patch", "delete"):
            app.api_route(stub.path, methods=[method], status_code=stub.status_code,
                          dependencies=[Depends(require_auth)])(_handler)
