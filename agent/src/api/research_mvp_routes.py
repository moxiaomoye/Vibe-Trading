"""Unified HTTP entry point for Research MVP V1."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from datetime import date

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from src.investment_research.application.research_mvp import build_historical_evaluation, build_research_run
from src.market_data import fetch_market_data


AuthDep = Callable[..., Awaitable[Any] | Any]


class HistoricalEvaluationRequest(BaseModel):
    trade_date: date


def get_research_scan_service() -> Any:
    from src.api.value_hunter_routes import get_value_hunter_service

    return get_value_hunter_service()


def register_research_mvp_routes(app: FastAPI, require_auth: AuthDep) -> None:
    @app.post("/investment-research/research-run", dependencies=[Depends(require_auth)])
    async def investment_research_run() -> dict[str, Any]:
        return await asyncio.to_thread(build_research_run, get_research_scan_service())

    @app.post("/investment-research/historical-evaluation", dependencies=[Depends(require_auth)])
    async def investment_research_historical_evaluation(request: HistoricalEvaluationRequest) -> dict[str, Any]:
        return await asyncio.to_thread(
            build_historical_evaluation,
            get_research_scan_service(),
            request.trade_date,
            fetch_market_data,
        )
