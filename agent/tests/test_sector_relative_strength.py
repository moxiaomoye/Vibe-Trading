from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.value_hunter.history_replay import run_history_replay
from src.value_hunter.panic_scan import run_panic_scan
from src.value_hunter.post_close_provider import SectorMembership
from src.value_hunter.sector_relative_strength import resolve_sector_relative_input


SYMBOL = "600522.SH"
SCAN_DATE = date(2026, 7, 22)


def _membership(
    *,
    sector="半导体",
    source_date=SCAN_DATE,
    availability_date=SCAN_DATE,
    valid_through=None,
):
    return SectorMembership(
        symbol=SYMBOL,
        sector=sector,
        source_date=source_date,
        availability_date=availability_date,
        valid_through=valid_through,
    )


def _resolve(memberships, returns=None, return_date=SCAN_DATE, return_available=SCAN_DATE):
    return resolve_sector_relative_input(
        symbol=SYMBOL,
        scan_date=SCAN_DATE,
        memberships=memberships,
        sector_returns=returns if returns is not None else {"半导体": -0.03},
        sector_return_date=return_date,
        sector_return_availability_date=return_available,
    )


def test_valid_sector_mapping_and_return():
    result = _resolve([_membership()])
    assert result.sector == "半导体"
    assert result.sector_change_pct == -0.03
    assert result.data_gap is None


def test_symbol_without_sector_is_explicit_gap():
    result = _resolve([])
    assert result.sector_change_pct is None
    assert "归属" in result.data_gap.description


def test_stale_mapping_is_rejected():
    result = _resolve([_membership(source_date=SCAN_DATE - timedelta(days=1))])
    assert result.sector_change_pct is None
    assert "过期" in result.data_gap.description


def test_future_mapping_is_rejected():
    result = _resolve([
        _membership(
            source_date=SCAN_DATE + timedelta(days=1),
            availability_date=SCAN_DATE + timedelta(days=1),
        )
    ])
    assert result.sector_change_pct is None
    assert "尚不可用" in result.data_gap.description


def test_missing_sector_return_is_not_replaced_by_market_return():
    result = _resolve([_membership()], returns={})
    assert result.sector_change_pct is None
    assert "行业收益" in result.data_gap.description


@pytest.mark.parametrize(
    ("return_date", "available_date", "message"),
    [
        (SCAN_DATE - timedelta(days=1), SCAN_DATE - timedelta(days=1), "不是扫描日"),
        (SCAN_DATE, SCAN_DATE + timedelta(days=1), "尚不可用"),
    ],
)
def test_stale_or_future_available_sector_return_rejected(return_date, available_date, message):
    result = _resolve([_membership()], return_date=return_date, return_available=available_date)
    assert result.sector_change_pct is None
    assert message in result.data_gap.description


def test_mapping_changes_through_time_selects_scan_date_version():
    old = _membership(
        sector="电子",
        source_date=SCAN_DATE - timedelta(days=10),
        availability_date=SCAN_DATE - timedelta(days=10),
        valid_through=SCAN_DATE - timedelta(days=1),
    )
    current = _membership(sector="半导体")
    result = _resolve([old, current], returns={"电子": 0.01, "半导体": -0.03})
    assert result.sector == "半导体"
    assert result.sector_change_pct == -0.03


def test_replay_and_live_panel_paths_share_sector_semantics(tmp_path):
    watchlist = tmp_path / "watchlist.yaml"
    watchlist.write_text(
        'version: "test"\nwatchlist:\n  name: "fixture"\n  symbols:\n    - "600522.SH"\n',
        encoding="utf-8",
    )
    panel = {
        "spot_df": pd.DataFrame(
            {
                "代码": ["600522"],
                "名称": ["fixture"],
                "最新价": [95.0],
                "涨跌幅": [-5.0],
                "昨收": [100.0],
            }
        ),
        "limit_up_symbols": [],
        "limit_down_symbols": [],
        "data_date": SCAN_DATE,
        "availability_date": SCAN_DATE,
        "now": datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc),
        "market_change_pct": -0.02,
        "sector_memberships": [_membership()],
        "sector_returns": {"半导体": -0.03},
        "sector_return_date": SCAN_DATE,
        "sector_return_availability_date": SCAN_DATE,
    }
    live = run_panic_scan(panel_data=panel, watchlist_path=str(watchlist))
    replay = run_history_replay(daily_panels={SCAN_DATE: panel}, watchlist_path=watchlist)
    assert live.watchlist[0].relative_to_market == pytest.approx(-0.03)
    assert live.watchlist[0].relative_to_sector == pytest.approx(-0.02)
    assert replay.entries[0].result.watchlist[0].relative_to_sector == pytest.approx(-0.02)
    assert live.watchlist[0].data_gap.description == ""
    assert replay.entries[0].result.watchlist[0].data_gap.description == ""
