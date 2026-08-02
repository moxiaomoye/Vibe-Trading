"""Unified HTTP entry point for Research MVP V1."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from src.investment_research.application.research_mvp import (
    build_historical_evaluation,
    build_research_run,
    prepare_feishu_delivery,
)
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository
from src.investment_research.operations.delivery import FeishuWebhookTransport, OutboxDispatcher
from src.investment_research.operations.models import DeliveryChannel
from src.market_data import fetch_market_data


AuthDep = Callable[..., Awaitable[Any] | Any]


class HistoricalEvaluationRequest(BaseModel):
    trade_date: date


class ResearchRunRequest(BaseModel):
    panic_sensitivity: int = Field(default=50, ge=0, le=100)


class FeishuPreviewRequest(BaseModel):
    report: dict[str, Any]
    send: bool = False
    confirmed: bool = False


def get_research_scan_service() -> Any:
    from src.api.value_hunter_routes import get_value_hunter_service

    return get_value_hunter_service()


def get_research_outbox_repository() -> SQLiteOperationsRepository:
    from src.api.investment_research_routes import get_investment_research_repository

    return SQLiteOperationsRepository(get_investment_research_repository().path)


def get_research_feishu_webhook_url() -> str:
    """Use the dedicated research URL, falling back to the existing Value Hunter robot."""
    from src.config.accessor import get_env_config

    dedicated = get_env_config().research_delivery.feishu_webhook_url.strip()
    if dedicated:
        return dedicated
    return str(getattr(get_research_scan_service().config, "feishu_webhook_url", "")).strip()


def dispatch_feishu_message(
    repository: SQLiteOperationsRepository,
    message_id: str,
    webhook_url: str,
) -> dict[str, Any]:
    if not webhook_url:
        return {"status": "configuration_missing", "delivery_error": "飞书 Webhook 尚未配置"}
    dispatcher = OutboxDispatcher(
        repository,
        {DeliveryChannel.FEISHU: FeishuWebhookTransport(webhook_url)},
    )
    dispatcher.dispatch_message(message_id, datetime.now(timezone.utc))
    message = repository.get_message(message_id)
    result: dict[str, Any] = {"status": message.status.value}
    if message.last_error:
        result["delivery_error"] = message.last_error
    return result


def register_research_mvp_routes(app: FastAPI, require_auth: AuthDep) -> None:
    @app.post("/investment-research/research-run", dependencies=[Depends(require_auth)])
    async def investment_research_run(
        request: ResearchRunRequest | None = None,
    ) -> dict[str, Any]:
        sensitivity = request.panic_sensitivity if request else 50
        return await asyncio.to_thread(
            build_research_run,
            get_research_scan_service(),
            sensitivity,
        )

    @app.post("/investment-research/historical-evaluation", dependencies=[Depends(require_auth)])
    async def investment_research_historical_evaluation(request: HistoricalEvaluationRequest) -> dict[str, Any]:
        return await asyncio.to_thread(
            build_historical_evaluation,
            get_research_scan_service(),
            request.trade_date,
            fetch_market_data,
        )

    @app.post("/investment-research/feishu-preview", dependencies=[Depends(require_auth)])
    async def investment_research_feishu_preview(request: FeishuPreviewRequest) -> dict[str, Any]:
        try:
            repository = get_research_outbox_repository()
            result = prepare_feishu_delivery(
                request.report,
                repository,
                send=request.send,
                confirmed=request.confirmed,
            )
            if request.send and request.confirmed and result.get("message_id"):
                delivery = await asyncio.to_thread(
                    dispatch_feishu_message,
                    repository,
                    result["message_id"],
                    get_research_feishu_webhook_url(),
                )
                result.update(delivery)
            return result
        except ValueError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=str(exc)) from exc
