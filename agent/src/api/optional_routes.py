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
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Awaitable, Callable

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


def try_register_routes(
    app: FastAPI,
    *,
    feature_name: str,
    env_var: str,
    module_path: str,
    register_func_name: str,
    require_auth: AuthDep,
) -> LoadResult:
    """Register optional feature routes gated by *env_var*.

    When the env var is unset / falsy the module is never imported.
    When truthy the module is lazy-imported and its registration function called.
    Any exception during import or registration is caught, logged (with
    traceback), and never propagated — the core Application continues starting.

    Returns:
        A ``LoadResult`` whose ``status`` is one of
        ``DISABLED`` / ``LOADED`` / ``FAILED``.
    """
    if not _parse_bool(os.environ.get(env_var)):
        logger.debug("Optional feature %r disabled (%s not set)", feature_name, env_var)
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
