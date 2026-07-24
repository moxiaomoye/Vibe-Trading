"""RC7 — Smoke validation: provider, manual-import, and fixture paths."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from src.investment_research.application.panic_orchestration import OrchestrationRequest
from src.investment_research.application.shadow_run import (
    PanicResearchShadowRunner,
    ShadowRunConfig,
    ShadowRunInputs,
)
from src.investment_research.operations.manual_import import parse_manual_import_dict
from src.value_hunter.watchlist_loader import DEFAULT_WATCHLIST_PATH


def _make_runner() -> PanicResearchShadowRunner:
    return PanicResearchShadowRunner(ShadowRunConfig(enabled=True))


def _make_request(data_date: date | None = None) -> OrchestrationRequest:
    now = datetime.now(timezone.utc)
    return OrchestrationRequest(
        run_id="smoke-test",
        now=now,
        data_date=data_date or date.today(),
        data_available_at=now,
    )


def _make_inputs(panel_data: dict[str, Any]) -> ShadowRunInputs:
    return ShadowRunInputs(
        panel_data=panel_data,
        watchlist_path=str(DEFAULT_WATCHLIST_PATH),
        information_cutoff=datetime.now(timezone.utc) + timedelta(hours=1),
        candidates=(),
    )


class TestFixtureSmoke:
    """Smoke test with fixture/minimal data — no external dependencies."""

    def test_fixture_smoke(self) -> None:
        import pandas as pd
        spot_df = pd.DataFrame({
            "代码": ["000001.SZ", "000002.SZ"],
            "名称": ["平安银行", "万科A"],
            "最新价": [12.5, 8.0],
            "涨跌幅": [1.5, -2.3],
            "昨收": [12.3, 8.2],
        })
        panel_data = {
            "spot_df": spot_df,
            "limit_up_symbols": set(),
            "limit_down_symbols": set(),
            "data_date": date.today(),
            "availability_date": date.today(),
            "now": datetime.now(timezone.utc),
            "market_change_pct": None,
            "source": "fixture",
            "component_sources": {"spot": "fixture"},
            "provider_errors": [],
            "data_gaps": [],
            "sector_map": {},
            "sector_memberships": [],
            "sector_returns": {},
        }
        runner = _make_runner()
        result = runner.run(_make_request(), _make_inputs(panel_data))
        assert result.status.value == "succeeded"
        assert result.output is not None
        report = result.output.to_dict()
        assert "market" in report


class TestManualImportSmoke:
    """Smoke test using the manual-import JSON format."""

    def _sample_manual_data(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": date.today().isoformat(),
            "availability_time": datetime.now(timezone.utc).isoformat(),
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5, "previous_close": 12.3, "change_percent": 1.63},
                {"symbol": "000002", "name": "万科A", "close": 8.0, "previous_close": 8.1, "change_percent": -1.23},
            ],
        }

    def test_manual_import_smoke(self) -> None:
        import pandas as pd
        data = self._sample_manual_data()
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 2
        assert not result.errors

        spot_rows = []
        for row in result.rows:
            spot_rows.append({
                "代码": row.symbol,
                "名称": row.name,
                "最新价": row.close,
                "昨收": row.previous_close,
                "涨跌幅": row.change_percent,
            })
        spot_df = pd.DataFrame(spot_rows)

        panel_data = {
            "spot_df": spot_df,
            "limit_up_symbols": set(),
            "limit_down_symbols": set(),
            "data_date": result.source_date,
            "availability_date": result.source_date,
            "now": result.availability_time,
            "market_change_pct": None,
            "source": "manual_import",
            "component_sources": {"spot": "manual_import"},
            "provider_errors": [],
            "data_gaps": [],
            "sector_map": {},
            "sector_memberships": [],
            "sector_returns": {},
        }
        runner = _make_runner()
        run_result = runner.run(
            _make_request(data_date=result.source_date),
            _make_inputs(panel_data),
        )
        assert run_result.status.value == "succeeded"
        assert run_result.output is not None
        report = run_result.output.to_dict()
        assert "market" in report


@pytest.mark.skip(reason="Read-only real provider smoke — requires akshare and network")
class TestProviderSmoke:
    """Smoke test calling a real market data provider (read-only)."""

    def test_provider_smoke(self) -> None:
        import akshare as ak
        import pandas as pd

        try:
            spot = ak.stock_zh_a_spot()
            source = "sina"
        except Exception:
            try:
                spot = ak.stock_zh_a_spot_em()
                source = "eastmoney"
            except Exception:
                pytest.skip("No real provider available")

        if spot is None or spot.empty:
            pytest.skip("Spot data is empty")

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
            "data_date": date.today(),
            "availability_date": date.today(),
            "now": datetime.now(timezone.utc),
            "market_change_pct": None,
            "source": source,
            "component_sources": {"spot": source, "benchmark": "unavailable"},
            "provider_errors": [],
            "data_gaps": [],
            "sector_map": {},
            "sector_memberships": [],
            "sector_returns": {},
        }
        runner = _make_runner()
        result = runner.run(_make_request(), _make_inputs(panel_data))
        assert result.status.value == "succeeded"
        assert result.output is not None
        report = result.output.to_dict()
        assert "market" in report
