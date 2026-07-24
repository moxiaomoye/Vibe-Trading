"""Default-off, authenticated HTTP adapter for M11 panic shadow reports."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

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
from src.investment_research.operations.report_storage import ReportStorage
from src.investment_research.operations.manual_import import (
    MAX_IMPORT_BYTES,
    parse_manual_import_dict,
    row_to_panel_entry,
)
from src.value_hunter.watchlist_loader import DEFAULT_WATCHLIST_PATH


AuthDep = Callable[..., Awaitable[Any] | Any]
MAX_MARKET_ROWS = 10_000
REPORT_OUTPUT_DIR = Path.home() / ".vibe-trading" / "panic-shadow-reports"
_report_storage: ReportStorage | None = None


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
            "explicit_input_only": False,
            "explicit_input_supported": True,
            "provider_run_supported": True,
            "persistent": True,
            "persistence_scope": "successful_provider_runs_only",
            "scheduler_enabled": False,
            "notification_enabled": False,
            "trading_enabled": False,
            "manual_review_required": True,
        }

    @app.get("/investment-research/panic-shadow/latest", dependencies=dependencies)
    def latest_panic_shadow_report():
        report = _storage().load_latest()
        if report is None:
            return _error(404, "shadow_report_not_found", "no stored shadow report is available")
        return report

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
        try:
            result, post_close = _execute_current()
        except CurrentReportDataError as exc:
            return _error(503, "data_unavailable", str(exc), reasons=list(exc.reasons))
        except Exception:
            return _error(
                500,
                "shadow_run_failed",
                "shadow report execution failed; core application remains available",
            )

        if result.status == OrchestrationStatus.SUCCEEDED and result.output is not None:
            report = result.output.to_dict()
            report["shadow_run"] = True
            report["manual_review_required"] = True
            report["data_source"] = post_close.source
            report["input_mode"] = "provider"
            report["provenance"] = _provider_provenance(post_close)
            try:
                _storage().save_report(report, date_dir=post_close.source_date)
            except OSError:
                return _error(
                    500,
                    "shadow_report_storage_failed",
                    "shadow report completed but could not be stored",
                )
            return report
        return _error(
            500 if result.status == OrchestrationStatus.FAILED else 422,
            f"shadow_run_{result.status.value}",
            "shadow report execution failed; core application remains available",
            reasons=list(result.reasons),
        )

    @app.post("/investment-research/panic-shadow/run-manual", dependencies=dependencies)
    def run_manual_shadow_report(payload: dict[str, Any]):
        try:
            result, provenance = _execute_manual(payload)
        except CurrentReportDataError as exc:
            return _error(422, "invalid_manual_import", str(exc), reasons=list(exc.reasons))
        except Exception:
            return _error(
                500,
                "shadow_run_failed",
                "manual shadow report execution failed; core application remains available",
            )

        if result.status == OrchestrationStatus.SUCCEEDED and result.output is not None:
            report = result.output.to_dict()
            report["shadow_run"] = True
            report["manual_review_required"] = True
            report["data_source"] = "manual_import"
            report["input_mode"] = "manual_import"
            report["provenance"] = provenance
            try:
                _storage().save_report(report, date_dir=date.fromisoformat(provenance["source_date"]))
            except OSError:
                return _error(
                    500,
                    "shadow_report_storage_failed",
                    "manual shadow report completed but could not be stored",
                )
            return report
        return _error(
            500 if result.status == OrchestrationStatus.FAILED else 422,
            f"shadow_run_{result.status.value}",
            "manual shadow report did not execute",
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


class CurrentReportDataError(ValueError):
    def __init__(self, message: str, reasons: list[str] | tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.reasons = tuple(reasons)


def _execute_current():
    provider = _current_provider()
    trade_date = _now_utc().astimezone(ZoneInfo("Asia/Shanghai")).date()
    post_close = provider.load(as_of=trade_date)
    reasons = [gap.reason for gap in post_close.data_gaps]
    if post_close.source_date != trade_date:
        raise CurrentReportDataError(
            "provider source date does not match the requested trading date",
            reasons,
        )
    if post_close.availability_date > trade_date:
        raise CurrentReportDataError(
            "provider data was not available on the requested trading date",
            reasons,
        )
    if post_close.spot_df.empty:
        raise CurrentReportDataError("all spot sources are unavailable", reasons)

    information_cutoff = post_close.retrieved_at.astimezone(timezone.utc)
    observed_at = max(_now_utc(), information_cutoff)
    panel_data = post_close.to_panel_data()
    panel_data["now"] = information_cutoff
    return _run_panel(
        panel_data=panel_data,
        information_cutoff=information_cutoff,
        observed_at=observed_at,
        data_date=post_close.source_date,
        data_available_at=information_cutoff,
        run_id=f"shadow-{trade_date.isoformat()}-{information_cutoff.strftime('%H%M%S%f')}",
    ), post_close


def _execute_manual(payload: dict[str, Any]):
    if len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) > MAX_IMPORT_BYTES:
        raise CurrentReportDataError(
            f"manual import payload exceeds {MAX_IMPORT_BYTES} bytes"
        )
    imported = parse_manual_import_dict(payload)
    if imported.errors:
        raise CurrentReportDataError("manual import validation failed", imported.errors)
    if not imported.rows:
        raise CurrentReportDataError("manual import contains no accepted market rows")

    trade_date = _now_utc().astimezone(ZoneInfo("Asia/Shanghai")).date()
    if imported.source_date != trade_date:
        raise CurrentReportDataError(
            "browser manual import only accepts the current Shanghai trading date",
            [f"source_date={imported.source_date.isoformat()}", f"expected={trade_date.isoformat()}"],
        )
    benchmarks = {row.benchmark for row in imported.rows if row.benchmark is not None}
    if len(benchmarks) > 1:
        raise CurrentReportDataError(
            "manual import benchmark values must be consistent across rows"
        )

    from src.value_hunter.post_close_provider import (
        ProviderDataGap,
        _compute_limit_pools_from_spot,
    )

    spot_df = pd.DataFrame(row_to_panel_entry(row) for row in imported.rows)
    limit_up, limit_down, limit_gap = _compute_limit_pools_from_spot(
        spot_df,
        imported.source_date,
    )
    scope_gap = ProviderDataGap(
        "market_scope",
        (
            f"manual import contains {len(imported.rows)} rows; "
            "market breadth reflects the imported universe only"
        ),
        imported.source_date,
        imported.source_date,
    )
    information_cutoff = imported.availability_time.astimezone(timezone.utc)
    observed_at = max(_now_utc(), information_cutoff)
    panel_data = {
        "spot_df": spot_df,
        "limit_up_symbols": limit_up,
        "limit_down_symbols": limit_down,
        "data_date": imported.source_date,
        "availability_date": imported.source_date,
        "now": information_cutoff,
        "market_change_pct": (
            next(iter(benchmarks)) / 100.0 if benchmarks else None
        ),
        "sector_map": {},
        "source": "manual_import",
        "component_sources": {
            "spot": "manual_import",
            "benchmark": "manual_import" if benchmarks else "unavailable",
            "limit_up": "computed_from_spot",
            "limit_down": "computed_from_spot",
            "sector_returns": "unavailable",
        },
        "provider_errors": [],
        "data_gaps": [limit_gap, scope_gap],
    }
    result = _run_panel(
        panel_data=panel_data,
        information_cutoff=information_cutoff,
        observed_at=observed_at,
        data_date=imported.source_date,
        data_available_at=information_cutoff,
        run_id=(
            f"shadow-{imported.source_date.isoformat()}-manual-"
            f"{observed_at.strftime('%H%M%S%f')}"
        ),
    )
    provenance = {
        "source": "manual_import",
        "source_date": imported.source_date.isoformat(),
        "availability_time": imported.availability_time.isoformat(),
        "accepted_count": imported.accepted_count,
        "rejected_count": imported.rejected_count,
        "component_sources": dict(panel_data["component_sources"]),
        "data_gaps": [
            {
                "field": gap.field,
                "reason": gap.reason,
                "source_date": gap.source_date.isoformat() if gap.source_date else None,
                "availability_date": (
                    gap.availability_date.isoformat() if gap.availability_date else None
                ),
            }
            for gap in panel_data["data_gaps"]
        ],
    }
    return result, provenance


def _run_panel(
    *,
    panel_data: dict[str, Any],
    information_cutoff: datetime,
    observed_at: datetime,
    data_date: date,
    data_available_at: datetime,
    run_id: str,
):
    inputs = ShadowRunInputs(
        panel_data=panel_data,
        watchlist_path=str(DEFAULT_WATCHLIST_PATH),
        information_cutoff=information_cutoff,
        candidates=(),
    )
    request = OrchestrationRequest(
        run_id=run_id,
        now=observed_at,
        data_date=data_date,
        data_available_at=data_available_at,
    )
    runner = PanicResearchShadowRunner(ShadowRunConfig(enabled=True))
    return runner.run(request, inputs)


def _current_provider():
    from src.value_hunter.post_close_provider import (
        ComponentFallbackPostCloseProvider,
        SinaBenchmarkAdapter,
    )

    return ComponentFallbackPostCloseProvider(
        benchmark_fallback=SinaBenchmarkAdapter(),
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _provider_provenance(post_close) -> dict[str, Any]:
    def date_value(value: date | None) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "source": post_close.source,
        "source_date": post_close.source_date.isoformat(),
        "availability_date": post_close.availability_date.isoformat(),
        "retrieved_at": post_close.retrieved_at.isoformat(),
        "component_sources": dict(post_close.component_sources),
        "errors": [
            {
                "operation": error.operation,
                "error_type": error.error_type,
                "message": "upstream request failed",
                "attempts": error.attempts,
                "retryable": error.retryable,
            }
            for error in post_close.errors
        ],
        "data_gaps": [
            {
                "field": gap.field,
                "reason": gap.reason,
                "source_date": date_value(gap.source_date),
                "availability_date": date_value(gap.availability_date),
            }
            for gap in post_close.data_gaps
        ],
    }


def _storage() -> ReportStorage:
    global _report_storage
    if _report_storage is None:
        _report_storage = ReportStorage(REPORT_OUTPUT_DIR)
    return _report_storage


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
