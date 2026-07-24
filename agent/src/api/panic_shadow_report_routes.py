"""Default-off, authenticated HTTP adapter for M11 panic shadow reports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Awaitable, Callable

import pandas as pd
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from src.investment_research.application.panic_orchestration import (
    OrchestrationRequest,
    OrchestrationStatus,
)
from src.investment_research.application.shadow_run import (
    PanicResearchShadowRunner,
    ShadowRunConfig,
    ShadowRunInputs,
)
from src.value_hunter.watchlist_loader import DEFAULT_WATCHLIST_PATH


AuthDep = Callable[..., Awaitable[Any] | Any]
MAX_MARKET_ROWS = 10_000


class ShadowMarketRow(BaseModel):
    """One explicit, point-in-time market observation."""

    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=128)
    close: float = Field(ge=0)
    change_pct: float = Field(ge=-100, le=10_000)
    previous_close: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class ShadowReportRunRequest(BaseModel):
    """Explicit dry-run input; no Provider, persistence or execution settings."""

    run_id: str = Field(min_length=1, max_length=128)
    data_date: date
    observed_at: datetime
    information_cutoff: datetime
    data_available_at: datetime
    market_return: float | None = Field(default=None, ge=-1, le=100)
    rows: list[ShadowMarketRow] = Field(min_length=1, max_length=MAX_MARKET_ROWS)
    limit_up_symbols: list[str] = Field(default_factory=list, max_length=MAX_MARKET_ROWS)
    limit_down_symbols: list[str] = Field(default_factory=list, max_length=MAX_MARKET_ROWS)

    @field_validator("observed_at", "information_cutoff", "data_available_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value

    @field_validator("run_id")
    @classmethod
    def normalize_run_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("run_id must not be blank")
        return normalized

    @field_validator("limit_up_symbols", "limit_down_symbols")
    @classmethod
    def normalize_symbol_list(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("limit symbols must not be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("limit symbols must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_point_in_time_order(self) -> "ShadowReportRunRequest":
        if self.data_available_at > self.observed_at:
            raise ValueError("data_available_at must not be after observed_at")
        if self.data_available_at > self.information_cutoff:
            raise ValueError("data_available_at must not be after information_cutoff")
        if self.information_cutoff > self.observed_at:
            raise ValueError("information_cutoff must not be after observed_at")
        symbols = [row.symbol for row in self.rows]
        if len(symbols) != len(set(symbols)):
            raise ValueError("market row symbols must be unique")
        return self


def register_panic_shadow_report_routes(app: FastAPI, require_auth: AuthDep) -> None:
    """Register the isolated HTTP adapter; callers own the default-off gate."""

    dependencies = [Depends(require_auth)]

    @app.get("/investment-research/panic-shadow/status", dependencies=dependencies)
    def panic_shadow_status() -> dict[str, Any]:
        return {
            "enabled": True,
            "mode": "shadow",
            "read_only": True,
            "explicit_input_only": True,
            "persistent": False,
            "scheduler_enabled": False,
            "notification_enabled": False,
            "trading_enabled": False,
            "manual_review_required": True,
        }

    @app.post("/investment-research/panic-shadow/run", dependencies=dependencies)
    def run_panic_shadow_report(payload: ShadowReportRunRequest):
        try:
            result = _execute(payload)
        except (TypeError, ValueError) as exc:
            return _error(422, "invalid_shadow_input", str(exc))
        except Exception:
            return _error(
                500,
                "shadow_run_failed",
                "shadow report execution failed; core application remains available",
            )

        if result.status == OrchestrationStatus.SUCCEEDED and result.output is not None:
            return result.output.to_dict()
        status_code = 500 if result.status == OrchestrationStatus.FAILED else 422
        message = (
            "shadow report execution failed; core application remains available"
            if result.status == OrchestrationStatus.FAILED
            else "shadow report did not execute"
        )
        return _error(
            status_code,
            f"shadow_run_{result.status.value}",
            message,
            reasons=list(result.reasons),
        )

    @app.post("/investment-research/panic-shadow/run-current", dependencies=dependencies)
    def run_current_shadow_report():
        import akshare as ak
        from datetime import timedelta

        observed_at = datetime.now()
        trade_date = date.today()
        information_cutoff = observed_at + timedelta(hours=1)

        try:
            spot = ak.stock_zh_a_spot()
            source = "sina"
        except Exception:
            try:
                spot = ak.stock_zh_a_spot_em()
                source = "eastmoney"
            except Exception:
                return _error(503, "data_unavailable", "All spot sources unavailable")

        if spot is None or spot.empty:
            return _error(503, "data_unavailable", "Spot data is empty")

        spot_df = spot.copy()
        code_col = "代码"
        if code_col in spot_df.columns:
            raw = spot_df[code_col].astype(str).str.strip()
            spot_df[code_col] = raw.str.replace(r"^sh(\d{6})$", r"\1.SH", regex=True)
            spot_df[code_col] = spot_df[code_col].str.replace(r"^sz(\d{6})$", r"\1.SZ", regex=True)
            spot_df[code_col] = spot_df[code_col].str.replace(r"^bj(\d{6})$", r"\1.BJ", regex=True)

        limit_up: set[str] = set()
        limit_down: set[str] = set()
        if code_col in spot_df.columns and "涨跌幅" in spot_df.columns:
            up_mask = spot_df["涨跌幅"].astype(float) >= 9.8
            down_mask = spot_df["涨跌幅"].astype(float) <= -9.8
            limit_up = set(spot_df.loc[up_mask, code_col].astype(str).str.strip())
            limit_down = set(spot_df.loc[down_mask, code_col].astype(str).str.strip())

        panel_data = {
            "spot_df": spot_df,
            "limit_up_symbols": limit_up,
            "limit_down_symbols": limit_down,
            "data_date": trade_date,
            "availability_date": trade_date,
            "now": information_cutoff,
            "market_change_pct": None,
            "source": source,
            "component_sources": {"spot": source, "benchmark": "unavailable"},
            "provider_errors": [],
            "data_gaps": [],
        }
        from src.value_hunter.post_close_provider import _compute_limit_pools_from_spot
        try:
            pools = _compute_limit_pools_from_spot(spot_df, trade_date)
            if pools and isinstance(pools, dict):
                panel_data["limit_up_symbols"] = set(pools.get("limit_up_symbols", []))
                panel_data["limit_down_symbols"] = set(pools.get("limit_down_symbols", []))
                panel_data["market_change_pct"] = pools.get("market_change_pct")
        except Exception:
            pass

        run_id = f"shadow-{trade_date.isoformat()}-current-{observed_at.strftime('%H%M%S')}"
        inputs = ShadowRunInputs(
            panel_data=panel_data,
            watchlist_path=str(DEFAULT_WATCHLIST_PATH),
            information_cutoff=information_cutoff,
            candidates=(),
        )
        request = OrchestrationRequest(
            run_id=run_id,
            now=observed_at,
            data_date=trade_date,
            data_available_at=observed_at,
        )
        runner = PanicResearchShadowRunner(ShadowRunConfig(enabled=True))
        result = runner.run(request, inputs)

        if result.status == OrchestrationStatus.SUCCEEDED and result.output is not None:
            report = result.output.to_dict()
            report["shadow_run"] = True
            report["manual_review_required"] = True
            report["data_source"] = source
            report["input_mode"] = "provider"
            return report
        return _error(
            500 if result.status == OrchestrationStatus.FAILED else 422,
            f"shadow_run_{result.status.value}",
            "shadow report execution failed; core application remains available",
            reasons=list(result.reasons),
        )


def _execute(payload: ShadowReportRunRequest):
    panel_data = {
        "spot_df": pd.DataFrame(
            {
                "代码": [row.symbol for row in payload.rows],
                "名称": [row.name for row in payload.rows],
                "最新价": [row.close for row in payload.rows],
                "涨跌幅": [row.change_pct for row in payload.rows],
                "昨收": [row.previous_close for row in payload.rows],
            }
        ),
        "limit_up_symbols": list(payload.limit_up_symbols),
        "limit_down_symbols": list(payload.limit_down_symbols),
        "data_date": payload.data_date,
        "availability_date": payload.data_date,
        "now": payload.information_cutoff,
        "market_change_pct": payload.market_return,
        "source": "http-explicit-fixture",
    }
    inputs = ShadowRunInputs(
        panel_data=panel_data,
        watchlist_path=str(DEFAULT_WATCHLIST_PATH),
        information_cutoff=payload.information_cutoff,
        candidates=(),
    )
    request = OrchestrationRequest(
        run_id=payload.run_id,
        now=payload.observed_at,
        data_date=payload.data_date,
        data_available_at=payload.data_available_at,
    )
    runner = PanicResearchShadowRunner(ShadowRunConfig(enabled=True))
    return runner.run(request, inputs)


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    reasons: list[str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "shadow_run": True,
            "error": {
                "code": code,
                "message": message,
                "reasons": reasons or [],
            },
        },
    )
