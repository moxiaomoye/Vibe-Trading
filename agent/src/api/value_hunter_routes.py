"""HTTP routes for Value Hunter."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, Query

from src.value_hunter import ValueHunterConfig, ValueHunterService
from src.value_hunter.scheduler import ValueHunterScheduler

_service: ValueHunterService | None = None
_scheduler: ValueHunterScheduler | None = None


def get_value_hunter_service() -> ValueHunterService:
    global _service
    if _service is None:
        _service = ValueHunterService()
    return _service


def start_value_hunter() -> None:
    global _scheduler
    config = ValueHunterConfig.from_env()
    if not config.enabled:
        return
    service = get_value_hunter_service()
    _scheduler = _scheduler or ValueHunterScheduler(service)
    _scheduler.start()


async def stop_value_hunter() -> None:
    if _scheduler is not None:
        await _scheduler.stop()


AuthDep = Callable[..., Awaitable[Any] | Any]


def register_value_hunter_routes(app: FastAPI, require_auth: AuthDep) -> None:
    @app.get("/value-hunter/status", dependencies=[Depends(require_auth)])
    async def value_hunter_status() -> dict:
        return get_value_hunter_service().status()

    @app.get("/value-hunter/history", dependencies=[Depends(require_auth)])
    async def value_hunter_history(limit: int = Query(30, ge=1, le=200)) -> list[dict]:
        return get_value_hunter_service().history(limit)

    @app.post("/value-hunter/run", dependencies=[Depends(require_auth)])
    async def value_hunter_run(notify: bool = False) -> dict:
        result = await asyncio.to_thread(get_value_hunter_service().run, notify=notify)
        return result.to_dict()
